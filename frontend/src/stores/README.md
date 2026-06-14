# Pinia 状态仓库

跨路由共享状态（first_revision 决策 6）。单个画布内的细粒度操作仍由 `composables/` 处理。

| 状态仓库 | 职责 | 引入阶段 |
| --- | --- | --- |
| `useLibraryStore` | 项目列表 CRUD | 第 2 阶段 |
| `useProjectStore` | 当前项目元数据（名称、描述、三个 graph_id、最新 seed） | 第 2 阶段 |
| `useGraphStore` | 当前打开的子图（节点、边、选中状态） | 第 3 阶段 |
| `useChatStore` | 当前会话消息流、暂存列表和 SSE 状态 | 第 4 阶段 |
