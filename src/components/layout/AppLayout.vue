<script setup lang="ts">
import { RouterView } from 'vue-router'
import Sidebar from './Sidebar.vue'
</script>

<template>
  <div class="app-shell">
    <Sidebar />
    <main class="app-main">
      <RouterView />
    </main>
  </div>
</template>
