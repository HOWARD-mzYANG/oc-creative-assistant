<script setup lang="ts">
/**
 * Vue 根组件。
 *
 * 多页面重构后，根组件只渲染路由出口；实际页面（首页 / 聊天 / 项目库 / 工作区）由路由决定，
 * 业务状态由各页面和 Pinia store 管理。
 */
</script>

<template>
  <router-view v-slot="{ Component }">
    <transition name="page" mode="out-in">
      <component :is="Component" />
    </transition>
  </router-view>
</template>
