"""LangChain 工具工厂。

Research / Structure / Simulation agents 会在循环中按需调用这些工具收集证据，
把“决定查询什么”的能力交还给 LLM，同时减少把整个项目知识库直接塞进 prompt
带来的噪声。

工具按“查询形态”分为两类：
- relevance：search_nodes 按语义命中 top-K，适合“与 X 相关的内容”
- enumeration：list_nodes 按 node_type 列出完整清单，适合“项目里有哪些 X”
两者混用会漏信息：用 search_nodes 回答枚举问题，必然会漏掉相关性分数较低的节点。

所有工具都通过闭包绑定 project_id，因此 LLM 可见的 schema 只包含业务参数；
agent 节点只需调用 ``make_project_tools(state.project_id)``，即可获得作用域限定在
当前项目上的只读工具集合。
"""

from __future__ import annotations

import json

from langchain_core.tools import BaseTool, tool

from app.db.database import SessionLocal
from app.db.models import EdgeORM, NodeORM
from app.rag.retrieval import build_project_vector_context
from app.services.graph_mappers import (
    db_fields_to_api,
    db_parent_id_to_api,
    db_sort_order_to_api,
)
from app.services.graph_repository import read_project_node, read_project_nodes
from app.services.web_search_client import (
    WebSearchError,
    WebSearchUnavailable,
    search_web,
)


_NODE_TYPE_FILTER = {
    "character", "worldbuilding", "plot",
    "idea", "research", "structure",
}


def _node_content_preview(node: NodeORM, limit: int = 120) -> str:
    text = (node.content or "").strip()
    fields = db_fields_to_api(node.meta)
    if fields:
        field_text = "; ".join(f"{k}: {v}" for k, v in list(fields.items())[:4])
        text = f"{text} | {field_text}".strip(" |")
    return text[:limit]


def _node_tool_payload(node: NodeORM, *, preview: bool = False) -> dict[str, object]:
    """把节点整理成工具返回 payload；世界观节点额外带树状层级字段。"""
    tags = node.meta.get("tags", []) if isinstance(node.meta, dict) else []
    payload: dict[str, object] = {
        "id": node.id,
        "title": node.title,
        "type": node.node_type,
    }
    if preview:
        payload["content_preview"] = _node_content_preview(node, 160)
    else:
        payload["content"] = node.content
        payload["tags"] = tags
        payload["fields"] = db_fields_to_api(node.meta)
    if node.node_type == "worldbuilding":
        payload["parent_id"] = db_parent_id_to_api(node.meta)
        payload["sort_order"] = db_sort_order_to_api(node.meta)
    return payload


def make_project_tools(project_id: str, *, include_web_search: bool = True) -> list[BaseTool]:
    """生成绑定到指定项目的只读工具集。

    内部维护回合级 search_cache，因此 LLM 在同一个 ReAct 循环中用相近查询反复调用
    search_nodes 时会命中已有结果，避免重复调用 chroma。

    缓存键按“词集合”归一化（按空白切分 -> 排序 -> 重新拼接成字符串），因此无论
    LLM 调换词序（"Elara mentor" / "mentor Elara"）还是调整 top_k，都会命中同一份
    缓存；如果不归一化，ReAct 中的 LLM 很容易通过改写关键词绕过缓存并反复敲 chroma。
    """
    search_cache: dict[str, str] = {}

    def _cache_key(query: str) -> str:
        # 与词序无关 + 去重 + 忽略大小写；top_k 不进键，取最大 top_k 服务所有调用方。
        tokens = sorted(set(query.strip().lower().split()))
        return " ".join(tokens)

    @tool
    def search_nodes(query: str, top_k: int = 5) -> str:
        """从当前项目知识库中语义检索相关节点（相关性查询）。

        适合“与 X 相关 / 类似 Y / 提到 Z 的内容”等按相关性排序的问题。如果用户问的是
        “项目里有哪些 X”这类枚举问题，应改用 list_nodes。

        不适合按标题精确找节点；如果用户给出明确标题，优先用 find_node_by_title。
        不适合查看世界观树层级；世界观层级应使用 list_world_tree / get_world_subtree。

        在本回合内，相近关键词组合（与词序无关）一旦被调用过，再发送同一组词会直接
        命中缓存，不再调用 chroma；也不要故意通过调换词序或改变 top_k 绕过缓存重试，
        那不会带来新信息。

        参数：
            query: 搜索关键词或自然语言描述。
            top_k: 最多返回的节点数量；建议 3-8。

        返回：
            JSON 字符串列表，每项包含 id / title / type / content_preview / score。
            检索器出错时返回 "[ERROR] ..." 字符串，使 LLM 立即收束而不是换关键词重试。
        """
        key = _cache_key(query)
        cached = search_cache.get(key)
        if cached is not None:
            return cached

        bounded_top_k = max(1, min(int(top_k), 10))
        nodes = read_project_nodes(project_id)
        items, store, err = build_project_vector_context(
            project_id, nodes, query, bounded_top_k
        )

        if store == "chroma_unavailable":
            error_payload = (
                f"[ERROR] 检索器暂时不可用：{err}。本轮请直接基于已有上下文回答，"
                f"不要通过调用 search_nodes / list_nodes 重试。"
            )
            search_cache[key] = error_payload
            return error_payload

        result = json.dumps(
            [
                {
                    "id": item.id,
                    "title": item.title,
                    "type": item.type,
                    "content_preview": item.content[:160],
                    "score": round(item.score, 3),
                }
                for item in items
            ],
            ensure_ascii=False,
        )
        search_cache[key] = result
        return result

    @tool
    def list_nodes(node_type: str = "", limit: int = 100) -> str:
        """枚举当前项目中的所有节点，不做语义检索，可选按 node_type 过滤。

        适合需要覆盖完整清单的枚举问题，例如“项目里有哪些角色 / 已写了哪些设定 /
        现在有哪些剧情节点”；不要用 search_nodes 回答这类问题，否则与查询词相关性较低的
        节点会被漏掉。

        不适合查“与某个关键词最相关”的少量节点；相关性查询应使用 search_nodes。
        不适合读取节点完整正文；拿到 id 后应继续用 get_node 或 get_nodes。

        参数：
            node_type: 可选过滤器，六选一：character / worldbuilding / plot / idea /
                research / structure；空字符串或非白名单值表示不过滤。
            limit: 最多返回的节点数，默认 100；大型项目中 LLM 可降到 30-50。

        返回：
            JSON 字符串列表，每项包含 id / title / type / content_preview。
            worldbuilding 节点额外包含 parent_id / sort_order。
        """
        nodes = read_project_nodes(project_id)
        if node_type in _NODE_TYPE_FILTER:
            nodes = [n for n in nodes if n.node_type == node_type]
        capped = max(1, min(limit, 200))
        nodes = nodes[:capped]
        return json.dumps(
            [
                {
                    "id": n.id,
                    "title": n.title,
                    "type": n.node_type,
                    "content_preview": _node_content_preview(n),
                    "parent_id": db_parent_id_to_api(n.meta) if n.node_type == "worldbuilding" else None,
                    "sort_order": db_sort_order_to_api(n.meta) if n.node_type == "worldbuilding" else None,
                }
                for n in nodes
            ],
            ensure_ascii=False,
        )

    @tool
    def find_node_by_title(title: str, node_type: str = "", limit: int = 8) -> str:
        """按标题精确/近似查找当前项目节点，不走向量检索。

        适合用户说“把 X 放到 Y 下面 / 修改名为 Z 的节点”时先解析真实 node_id。
        会优先返回标题完全相同的节点，再返回包含关系的候选；可选按 node_type 过滤。

        参数：
            title: 要查找的节点标题或标题片段。
            node_type: 可选过滤器，六选一：character / worldbuilding / plot / idea /
                research / structure；空字符串表示不过滤。
            limit: 最多返回候选数，默认 8。

        返回：
            JSON 字符串列表，每项包含 id / title / type / content_preview；worldbuilding
            额外包含 parent_id / sort_order。
        """
        needle = title.strip().lower()
        if not needle:
            return "[]"
        nodes = read_project_nodes(project_id)
        if node_type in _NODE_TYPE_FILTER:
            nodes = [n for n in nodes if n.node_type == node_type]

        exact = [n for n in nodes if n.title.strip().lower() == needle]
        fuzzy = [
            n for n in nodes
            if n not in exact and needle in n.title.strip().lower()
        ]
        capped = max(1, min(int(limit), 20))
        return json.dumps(
            [_node_tool_payload(n, preview=True) for n in [*exact, *fuzzy][:capped]],
            ensure_ascii=False,
        )

    @tool
    def get_node(node_id: str) -> str:
        """读取指定节点的完整内容，用于在命中候选后确认细节。

        适合 search_nodes / list_nodes / find_node_by_title 返回候选后，继续读取某个节点的
        完整正文、标签和自由字段；也适合 update_node 前确认当前内容，避免覆盖错节点。

        不适合一次读取很多节点；批量场景应改用 get_nodes，减少工具调用轮次。

        参数：
            node_id: 真实节点 ID，必须来自 search_nodes / list_nodes /
                find_node_by_title / list_neighbors / list_world_tree 等工具返回值。

        返回：
            JSON 字符串对象，包含 id / title / type / content / tags / fields。
            worldbuilding 节点额外包含 parent_id / sort_order。未找到时返回 "{}"。
        """
        node = read_project_node(project_id, node_id)
        if node is None:
            return "{}"
        return json.dumps(_node_tool_payload(node), ensure_ascii=False)

    @tool
    def get_nodes(node_ids: list[str]) -> str:
        """批量读取多个节点的完整内容。

        适合“总结这些节点 / 翻译一组剧情节点 / 对比多个设定 / 需要一次读多个候选”的场景。
        它与 get_node 返回字段一致，但一次最多读取 12 个节点，能减少 ReAct 循环中反复调用
        get_node 的开销。

        不适合枚举“项目里有哪些 X”；枚举应先用 list_nodes，再把需要展开的 id 交给本工具。

        参数：
            node_ids: 真实节点 ID 列表，必须来自其他工具返回值；超过 12 个会截取前 12 个。

        返回：
            JSON 字符串列表，每项包含 id / title / type / content / tags / fields。
            worldbuilding 节点额外包含 parent_id / sort_order。无匹配时返回 []。
        """
        bounded_ids = [str(node_id) for node_id in node_ids[:12]]
        if not bounded_ids:
            return "[]"
        nodes_by_id = {node.id: node for node in read_project_nodes(project_id)}
        return json.dumps(
            [
                _node_tool_payload(nodes_by_id[node_id])
                for node_id in bounded_ids
                if node_id in nodes_by_id
            ],
            ensure_ascii=False,
        )

    @tool
    def list_world_tree(limit: int = 120) -> str:
        """列出当前项目的世界观笔记树。

        适合处理“世界观有哪些模块 / 某个设定应该放到哪里 / 把 X 放到 Y 下面 /
        新建一个世界观子笔记”等层级问题。创建或移动 worldbuilding 节点前，应优先调用
        本工具查看真实父节点 ID 和现有层级。

        不适合查询剧情节点或角色关系；剧情/角色请用 list_nodes、search_nodes、
        list_neighbors 或 multi_hop_neighbors。

        参数：
            limit: 最多返回多少条世界观笔记，默认 120，硬上限 300。

        返回：
            JSON 字符串列表，按树顺序展开。每项包含 id / title / parent_id /
            depth / sort_order / content_preview。depth=0 表示根笔记。
        """
        nodes = [n for n in read_project_nodes(project_id) if n.node_type == "worldbuilding"]
        node_by_id = {node.id: node for node in nodes}
        children_by_parent: dict[str | None, list[NodeORM]] = {}
        for node in nodes:
            parent_id = db_parent_id_to_api(node.meta)
            if parent_id and parent_id not in node_by_id:
                parent_id = None
            children_by_parent.setdefault(parent_id, []).append(node)

        for siblings in children_by_parent.values():
            siblings.sort(key=lambda n: (db_sort_order_to_api(n.meta), n.title))

        rows: list[dict[str, object]] = []
        capped = max(1, min(int(limit), 300))

        def visit(node: NodeORM, depth: int) -> None:
            if len(rows) >= capped:
                return
            rows.append({
                "id": node.id,
                "title": node.title,
                "parent_id": db_parent_id_to_api(node.meta),
                "depth": depth,
                "sort_order": db_sort_order_to_api(node.meta),
                "content_preview": _node_content_preview(node),
            })
            for child in children_by_parent.get(node.id, []):
                visit(child, depth + 1)

        for root in children_by_parent.get(None, []):
            visit(root, 0)

        return json.dumps(rows, ensure_ascii=False)

    @tool
    def get_world_subtree(node_id: str, depth: int = 3) -> str:
        """读取某个世界观笔记及其下级笔记。

        适合“某个模块下面已有些什么 / 把新设定放到这个模块下面前先检查内容 /
        总结某个世界观分支”等场景。它比 list_world_tree 更聚焦，会返回根节点完整正文，
        子节点返回较短预览。

        不适合按标题找节点；如果只有标题没有 node_id，应先用 find_node_by_title 或
        list_world_tree 找到真实 node_id。

        参数：
            node_id: 世界观节点 ID，必须来自 list_world_tree / find_node_by_title /
                list_nodes 等工具返回值。
            depth: 向下展开的层数，1-5；默认 3。

        返回：
            JSON 字符串列表，按子树顺序展开。每项包含 id / title / parent_id /
            depth / sort_order / content。根节点 content 为完整正文，子节点为预览。
        """
        nodes = [n for n in read_project_nodes(project_id) if n.node_type == "worldbuilding"]
        node_by_id = {node.id: node for node in nodes}
        root = node_by_id.get(node_id)
        if root is None:
            return "[]"

        children_by_parent: dict[str | None, list[NodeORM]] = {}
        for node in nodes:
            parent_id = db_parent_id_to_api(node.meta)
            children_by_parent.setdefault(parent_id, []).append(node)
        for siblings in children_by_parent.values():
            siblings.sort(key=lambda n: (db_sort_order_to_api(n.meta), n.title))

        bounded_depth = max(1, min(int(depth), 5))
        rows: list[dict[str, object]] = []

        def visit(node: NodeORM, current_depth: int) -> None:
            rows.append({
                "id": node.id,
                "title": node.title,
                "parent_id": db_parent_id_to_api(node.meta),
                "depth": current_depth,
                "sort_order": db_sort_order_to_api(node.meta),
                "content": node.content if current_depth == 0 else _node_content_preview(node, 180),
            })
            if current_depth >= bounded_depth:
                return
            for child in children_by_parent.get(node.id, []):
                visit(child, current_depth + 1)

        visit(root, 0)
        return json.dumps(rows, ensure_ascii=False)

    @tool
    def list_neighbors(node_id: str) -> str:
        """列出画布上与某节点直接相连的一跳邻居。

        适合回答“这个节点直接连着谁 / 这个剧情节点引用了哪些节点 / 谁和 X 有直接关系”
        这类一跳关系问题。返回 direction 表示相对 node_id 是 outgoing 还是 incoming。

        不适合多跳链式问题，例如“X 的导师的家族 / A 和 B 通过什么间接连接”；这类应改用
        multi_hop_neighbors。也不适合世界观树层级，世界观父子关系请用 list_world_tree /
        get_world_subtree。

        参数：
            node_id: 真实节点 ID，必须来自 search_nodes / list_nodes /
                find_node_by_title / get_node 等工具返回值。

        返回：
            JSON 字符串列表，每项包含 id / title / type / direction / relation。
            没有直接邻居时返回 []。
        """
        with SessionLocal() as db:
            edges = (
                db.query(EdgeORM)
                .filter(
                    EdgeORM.project_id == project_id,
                    (EdgeORM.source == node_id) | (EdgeORM.target == node_id),
                )
                .all()
            )
            if not edges:
                return "[]"

            neighbor_meta: dict[str, dict[str, str]] = {}
            for edge in edges:
                if edge.source == node_id:
                    other_id, direction = edge.target, "outgoing"
                else:
                    other_id, direction = edge.source, "incoming"
                neighbor_meta[other_id] = {
                    "direction": direction,
                    "relation": edge.label or edge.relation_type,
                }

            nodes = (
                db.query(NodeORM)
                .filter(NodeORM.id.in_(neighbor_meta.keys()))
                .all()
            )
            payload = [
                {
                    "id": node.id,
                    "title": node.title,
                    "type": node.node_type,
                    "direction": neighbor_meta[node.id]["direction"],
                    "relation": neighbor_meta[node.id]["relation"],
                }
                for node in nodes
            ]
        return json.dumps(payload, ensure_ascii=False)

    @tool
    def multi_hop_neighbors(
        node_id: str, depth: int = 2, max_nodes: int = 20
    ) -> str:
        """以 node_id 为中心展开 N 跳可达节点，并回溯最短关系路径。

        适合链式关系问答，例如“X 的导师的家族 / 哪些节点间接连接 A 和 B /
        这个剧情节点往外三跳会触及哪些设定”。返回 distance 和 path，方便回答“怎么连上”的问题。

        不适合单纯的一跳邻居查询；一跳问题用 list_neighbors 更省 token。
        不适合世界观树父子层级；世界观层级请用 list_world_tree / get_world_subtree。

        实现会运行一次 BFS，在内存中完成并返回；本回合内不缓存（画布关系变化频繁，
        缓存收益抵不过失效成本）。

        参数：
            node_id: 起始节点 ID，必须来自其他工具返回值。
            depth: BFS 跳数，1-3（默认 2）；超过 3 会自动截断，避免结果爆炸。
            max_nodes: 返回节点上限，默认 20，硬上限 50；超出时按距离升序保留更近节点。

        返回：
            JSON 字符串列表，每项包含 id / title / type / content_preview / distance / path；
            path 形如 "start -> [relation] -> middle -> [relation] -> end"。起始节点
            本身不包含在结果中；起点不存在或不属于本项目时返回 "[]"。
        """
        bounded_depth = max(1, min(int(depth), 3))
        bounded_max = max(1, min(int(max_nodes), 50))

        with SessionLocal() as db:
            origin = db.get(NodeORM, node_id)
            if origin is None or origin.project_id != project_id:
                return "[]"
            edges = (
                db.query(EdgeORM)
                .filter(EdgeORM.project_id == project_id)
                .all()
            )
            nodes_by_id = {
                n.id: n
                for n in db.query(NodeORM)
                .filter(NodeORM.project_id == project_id)
                .all()
            }

        # 双向邻接表；关系优先使用 label，缺失时回退到 relation_type。
        adjacency: dict[str, list[tuple[str, str]]] = {}
        for edge in edges:
            relation = edge.label or edge.relation_type or "related"
            adjacency.setdefault(edge.source, []).append((edge.target, relation))
            adjacency.setdefault(edge.target, []).append((edge.source, relation))

        # BFS：visited[id] = (distance, prev_id, relation_to_prev)。
        visited: dict[str, tuple[int, str | None, str | None]] = {
            node_id: (0, None, None)
        }
        frontier: list[str] = [node_id]
        while frontier:
            current = frontier.pop(0)
            current_dist = visited[current][0]
            if current_dist >= bounded_depth:
                continue
            for neighbor_id, relation in adjacency.get(current, []):
                if neighbor_id in visited:
                    continue
                visited[neighbor_id] = (current_dist + 1, current, relation)
                frontier.append(neighbor_id)

        def _trace_path(end_id: str) -> str:
            """从终点回溯到起点，组装 "start -> [relation] -> ... -> end" 字符串。"""
            chain: list[str] = []
            cursor: str | None = end_id
            while cursor is not None:
                node = nodes_by_id.get(cursor)
                chain.append(node.title if node else cursor)
                _, prev, relation = visited[cursor]
                if prev is not None and relation:
                    chain.append(f"[{relation}]")
                cursor = prev
            return " -> ".join(reversed(chain))

        result_ids = sorted(
            (vid for vid in visited if vid != node_id and vid in nodes_by_id),
            key=lambda vid: visited[vid][0],
        )[:bounded_max]

        payload = [
            {
                "id": vid,
                "title": nodes_by_id[vid].title,
                "type": nodes_by_id[vid].node_type,
                "content_preview": (nodes_by_id[vid].content or "")[:120],
                "distance": visited[vid][0],
                "path": _trace_path(vid),
            }
            for vid in result_ids
        ]

        return json.dumps(payload, ensure_ascii=False)

    @tool
    def web_search(query: str, top_k: int = 5) -> str:
        """搜索互联网外部事实；仅用于项目知识库无法回答的“真实世界参考”问题。

        适合：
        - 真实世界考据（中世纪盔甲样式 / 真实历史事件 / 物理常识 / 武器名称）
        - 实时信息（天气 / 新闻 / 当前日期附近的事实）
        - 第三方知识（外部模型 / 框架 / 库的规格）

        不要用于：
        - 项目内剧情 / 角色 / 设定问题，应使用 search_nodes / list_nodes
        - 询问 agent 自身（你用什么模型 / 你叫什么），这是系统信息，互联网无法回答

        本回合内，相同关键词组合（与词序无关）会命中缓存；不要故意改写关键词重新查询，
        那不会带来新信息。

        参数：
            query: 搜索关键词或自然语言问题。
            top_k: 最多返回的结果数，建议 3-6。

        返回：
            JSON 字符串，包含 answer（Tavily 综合出的短回答）和 hits 列表（每项含
            title / url / snippet / score）。网络不可用时返回 "[ERROR] ..." 字符串，
            使 LLM 立即收束。
        """
        key = _cache_key(query)
        cached = search_cache.get(f"web::{key}")
        if cached is not None:
            return cached

        try:
            response = search_web(query, top_k)
        except WebSearchUnavailable as exc:
            error_payload = (
                f"[ERROR] {exc}。本轮请基于已有上下文和项目知识库回答；"
                f"不要调用 web_search 重试。"
            )
            search_cache[f"web::{key}"] = error_payload
            return error_payload
        except WebSearchError as exc:
            error_payload = f"[ERROR] web_search 调用失败：{exc}"
            search_cache[f"web::{key}"] = error_payload
            return error_payload

        result = json.dumps(
            {
                "answer": response.answer,
                "hits": [
                    {
                        "title": hit.title,
                        "url": hit.url,
                        "snippet": hit.snippet,
                        "score": round(hit.score, 3),
                    }
                    for hit in response.hits
                ],
            },
            ensure_ascii=False,
        )
        search_cache[f"web::{key}"] = result
        return result

    tool_list = [
        search_nodes,
        list_nodes,
        find_node_by_title,
        get_node,
        get_nodes,
        list_world_tree,
        get_world_subtree,
        list_neighbors,
        multi_hop_neighbors,
    ]
    if include_web_search:
        tool_list.append(web_search)
    return tool_list
