/** Legacy project list group id, kept for mock/compatibility code; the left-hand main entry has been switched to the node toolbar. */
export type ProjectGroupId = 'ideas' | 'characters' | 'worldbuilding' | 'plot' | 'research' | 'structure'

/** Working mode of the right-hand Agent panel. */
export type AgentMode = 'inspiration' | 'research' | 'structure'

export const AGENT_MODE_LABELS: Record<AgentMode | 'auto', { label: string; hint: string }> = {
  auto: { label: 'Auto', hint: 'Agent picks research / inspiration / structure from your message' },
  research: { label: '资料', hint: 'Look up characters, world, and story already in the project' },
  inspiration: { label: 'Inspire', hint: 'Brainstorm ideas and follow-up questions; may auto-capture new concepts' },
  structure: { label: '结构', hint: 'Propose new nodes and relations for you to confirm' },
}

/** The node summary shape shared by the sidebar, the current node card and the Agent panel. */
export interface ProjectItem {
  id: string
  title: string
  kind: string
  summary: string
  meta: string
}

/** The left-hand project panel organizes node items by business type. */
export interface ProjectGroup {
  id: ProjectGroupId
  title: string
  items: ProjectItem[]
}

/** Suggestion cards in the right-hand Agent panel, currently from mock data. */
export interface AgentSuggestion {
  id: string
  title: string
  body: string
}

/** The bottom status bar aggregates the three runtime states: save, index and model. */
export interface WorkspaceStatus {
  saveState: string
  indexState: string
  modelState: string
}
