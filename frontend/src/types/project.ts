/**
 * 项目 / 子图 / seed 相关类型（first_revision 第 1 阶段）。
 *
 * 字段命名与后端 DTO（snake_case）保持一致，避免在 API 边界额外做一层转换。
 */

/** 子图分区。 */
export type GraphSection = 'plot' | 'character' | 'world'

/** 项目 seed（决策 3）。 */
export interface ProjectSeed {
  id: string
  project_id: string
  version: number
  seed_json: string
  source: 'chat_end' | 'user_edit'
  created_at?: string | null
}

/** 子图元数据。 */
export interface GraphInfo {
  id: string
  project_id: string
  section: GraphSection
}

/** 项目库卡片所需的概览信息。 */
export interface ProjectSummary {
  id: string
  name: string
  description: string
  /** 可选封面图，格式为 base64 data URL。 */
  cover_image: string
  created_at?: string | null
  updated_at?: string | null
}

/** 项目详情：包含三个子图 ID 和最新 seed。 */
export interface ProjectDetail {
  id: string
  name: string
  description: string
  /** 可选封面图，格式为 base64 data URL。 */
  cover_image: string
  plot_graph_id: string | null
  character_graph_id: string | null
  world_graph_id: string | null
  latest_seed: ProjectSeed | null
  created_at?: string | null
  updated_at?: string | null
}

/** 创建项目请求体。 */
export interface ProjectCreatePayload {
  name: string
  description?: string
}
