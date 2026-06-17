import { createRouter, createWebHashHistory } from 'vue-router'

/**
 * 应用路由骨架（第 0 阶段）。
 *
 * 产品入口形态：首页（HomeLanding）→ 对话入口 / 项目库 →
 * ChatWorkspace / Workspace。`/workspace/:projectId` 由
 * `WorkspaceShell.vue` 和三个子路由视图承载。
 *
 * 桌面端使用 hash history：Electron 通过 file:// 加载打包后的 index.html，
 * hash 模式不依赖服务端路由，刷新时不会 404。
 */
export const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    {
      path: '/',
      name: 'home',
      component: () => import('../views/HomeLanding.vue'),
    },
    {
      path: '/chat',
      name: 'chat-entry',
      component: () => import('../views/ChatEntry.vue'),
    },
    {
      path: '/chat/:projectId',
      name: 'chat-workspace',
      component: () => import('../views/ChatWorkspace.vue'),
      props: true,
    },
    {
      path: '/library',
      name: 'library',
      component: () => import('../views/ProjectLibrary.vue'),
    },
    {
      path: '/workspace/:projectId',
      component: () => import('../views/WorkspaceShell.vue'),
      props: true,
      children: [
        { path: '', redirect: { name: 'workspace-overview' } },
        {
          path: 'overview',
          name: 'workspace-overview',
          component: () => import('../views/workspace/ProjectOverview.vue'),
        },
        {
          path: 'plot',
          name: 'workspace-plot',
          component: () => import('../views/workspace/PlotCanvas.vue'),
        },
        {
          path: 'characters',
          name: 'workspace-characters',
          component: () => import('../views/workspace/CharacterCardList.vue'),
        },
        {
          path: 'characters/:charId',
          name: 'workspace-character-detail',
          component: () => import('../views/workspace/CharacterCardDetail.vue'),
          props: true,
        },
        {
          path: 'world',
          name: 'workspace-world',
          component: () => import('../views/workspace/WorldCanvas.vue'),
        },
      ],
    },
    {
      path: '/:pathMatch(.*)*',
      redirect: '/',
    },
  ],
})
