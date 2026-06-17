你的任务：在已经生成好的回复正文和原始结构化 agent 输出基础上，抽取两个元数据字段：

1. **cited_node_ids**：写回复时实际引用过的上下文节点 ID（即检索上下文提供的节点）。如果没有使用任何节点，返回空列表。
   - 来源：原始输出中的 referenced_node_ids 与 branches[*].affected_node_ids 的去重并集，这些都是检索上下文提供过的节点。
   - 只保留真正影响回复或在回复中被提到的 ID；丢弃与回复无关的 ID。
   - 绝不要编造原始输出中不存在的 ID。

2. **staging_summary**：一行短摘要。
   - 只有原始输出中的 proposed_changes 非空时才填写：“我已经把 N 项加入画布了，不想要的卡片可以丢弃。”
   - 否则留空字符串

不要编造任何节点 ID，也不要重复 reply_text 的正文内容。

---

## 输出示例（few-shot）

**已生成回复**: 好的，我准备把 Erin 和她的导师用“mentorship”关系连起来。
**原始输出**: proposed_changes contains 1 create_edge (char-airin -> char-mentor, mentorship);
referenced_node_ids = ["char-airin", "char-mentor"]

**理想元数据**:

```json
{
  "cited_node_ids": ["char-airin", "char-mentor"],
  "staging_summary": "我已经把 1 项加入画布了，不想要的卡片可以丢弃。"
}
```
