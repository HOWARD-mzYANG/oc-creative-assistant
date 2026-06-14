/**
 * Project / sub-graph / seed related types (first_revision, phase 1).
 *
 * Field naming is aligned with the backend DTO (snake_case) to avoid an extra conversion layer at the API boundary.
 */

/** sub-graph section. */
export type GraphSection = 'plot' | 'character' | 'world'

/** Project seed (decision 3). */
export interface ProjectSeed {
  id: string
  project_id: string
  version: number
  seed_json: string
  source: 'chat_end' | 'user_edit'
  created_at?: string | null
}

/** sub-graph metadata. */
export interface GraphInfo {
  id: string
  project_id: string
  section: GraphSection
}

/** 概览 information needed for project library cards. */
export interface ProjectSummary {
  id: string
  name: string
  description: string
  /** Optional cover image as a base64 data URL. */
  cover_image: string
  created_at?: string | null
  updated_at?: string | null
}

/** Project detail: includes the three sub-graph ids and the latest seed. */
export interface ProjectDetail {
  id: string
  name: string
  description: string
  /** Optional cover image as a base64 data URL. */
  cover_image: string
  plot_graph_id: string | null
  character_graph_id: string | null
  world_graph_id: string | null
  latest_seed: ProjectSeed | null
  created_at?: string | null
  updated_at?: string | null
}

/** Create project request body. */
export interface ProjectCreatePayload {
  name: string
  description?: string
}
