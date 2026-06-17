import { createApp } from 'vue'
import { createPinia } from 'pinia'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import './style.css'
import App from './App.vue'
import { router } from './router'

/**
 * 前端应用入口。
 *
 * 多页面重构后，根组件只挂载 <router-view>；跨路由共享状态通过 Pinia 管理，单个画布内的细粒度操作
 * 仍由各 composable 负责（见 first_revision 决策 6）。
 */
const scrollHideTimers = new WeakMap<EventTarget, ReturnType<typeof setTimeout>>()

document.addEventListener(
  'scroll',
  (event) => {
    const target = event.target
    if (!(target instanceof Element)) return

    target.classList.add('is-scrolling')

    const existing = scrollHideTimers.get(target)
    if (existing) clearTimeout(existing)

    scrollHideTimers.set(
      target,
      setTimeout(() => {
        target.classList.remove('is-scrolling')
        scrollHideTimers.delete(target)
      }, 700),
    )
  },
  true,
)

createApp(App).use(createPinia()).use(router).mount('#app')
