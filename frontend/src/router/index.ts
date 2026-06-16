import { createRouter, createWebHashHistory } from 'vue-router'

/**
 * Application routing skeleton (stage 0).
 *
 * Target product shape: home (HomeLanding) → chat entry / library →
 * ChatWorkspace / Workspace. `/workspace/:projectId` is served by
 * `WorkspaceShell.vue` plus its three sub-route views.
 *
 * Desktop uses hash history: Electron loads the bundled index.html via file://,
 * and hash mode doesn't depend on server-side routing, so a refresh won't 404.
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
        {
          path: 'role-model',
          name: 'workspace-role-model',
          component: () => import('../views/workspace/RoleModelStudio.vue'),
        },
      ],
    },
    {
      path: '/:pathMatch(.*)*',
      redirect: '/',
    },
  ],
})
