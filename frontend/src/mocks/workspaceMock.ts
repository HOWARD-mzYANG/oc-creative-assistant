import { mockGraphNodes } from './graph'
import type { AgentMode, AgentSuggestion, ProjectGroup, WorkspaceStatus } from '../types/workspace'
import { buildProjectGroupsFromNodes } from '../utils/nodeFactory'

/** PoC 默认项目名，与后端默认项目名保持一致；用于独立前端演示和旧入口视图。 */
export const mockProjectName = '霍格沃茨：最后围城'

/** 旧版左侧栏分组数据；真实图谱现在从后端加载。 */
export const mockProjectGroups: ProjectGroup[] = buildProjectGroupsFromNodes(mockGraphNodes)

/** 尚未接入真实 LLM 的 UI 状态使用的占位智能体建议。 */
export const mockAgentSuggestions: Record<AgentMode, AgentSuggestion[]> = {
  inspiration: [
    {
      id: 'idea-memory-cost',
      title: '强化记忆代价',
      body: '可以让记忆献祭既诱人又带有道德危险：城堡只有在守卫者拒绝让一个学生独自承担全部代价时，才真正得以幸存。',
    },
    {
      id: 'idea-shield-visual',
      title: '让护盾可视化',
      body: '古老护盾可以映照守卫者的情绪状态：猜疑扩散时出现银色裂纹，昔日敌人选择保护同一群人时则泛起更温暖的光。',
    },
    {
      id: 'idea-draco-vow',
      title: '把德拉科的誓言变成转折点',
      body: '让德拉科说出口的誓言同时决定天文塔密道和古老护盾的状态，使“信任”成为战场行动，而不只是主题。',
    },
  ],
  research: [
    {
      id: 'research-siege-lines',
      title: '厘清围城层级',
      body: '区分外层围城防线、中层防御和礼堂内层防御，让每个情节决策都有明确的战术后果。',
    },
    {
      id: 'research-passage-rules',
      title: '定义密道规则',
      body: '天文塔密道可以围绕誓言、追踪咒和“谁算被保护者”设置严格规则，为赫敏和德拉科提供具体约束。',
    },
  ],
  structure: [
    {
      id: 'structure-siege-chain',
      title: '整理围城事件链',
      body: '清晰的情节链可以从首次攻击开始，推进到护盾裂开、德拉科警告、密道誓言，再到伏地魔利用重新出现的猜疑。',
    },
    {
      id: 'structure-character-pressure',
      title: '建立信任关系网',
      body: '哈利、赫敏、德拉科、麦格、斯内普和伏地魔都可以从不同方向施压同一个核心问题：守卫者能否在直接攻击下继续信任彼此。',
    },
  ],
}

/** 工作区状态占位；保存状态会在 AppShell 中被真实后端状态覆盖。 */
export const mockWorkspaceStatus: WorkspaceStatus = {
  saveState: '霍格沃茨围城草稿已保存',
  indexState: '护盾与密道记忆索引等待构建',
  modelState: '模型：本地故事占位',
}
