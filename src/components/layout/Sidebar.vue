<script setup lang="ts">
import { RouterLink, useRoute } from 'vue-router'

const route = useRoute()

const navItems = [
  { path: '/events', label: 'Coupled Event Detection', desc: 'Historical samples & tracks' },
  { path: '/risk', label: 'Risk Assessment', desc: 'Iburi × Jebi case study' },
]
</script>

<template>
  <aside class="sidebar">
    <div class="sidebar-top">
      <div class="sidebar-brand">
        <span class="brand-mark" aria-hidden="true">
          <span class="brand-mark-inner" />
        </span>
        <div>
          <p class="brand-title">EQTyCatRisk</p>
          <p class="brand-sub">EQ–Typhoon Catastrophe Risk</p>
        </div>
      </div>

      <nav class="sidebar-nav" aria-label="Main navigation">
        <RouterLink
          v-for="item in navItems"
          :key="item.path"
          :to="item.path"
          class="nav-item"
          :class="{ active: route.path === item.path }"
        >
          <span class="nav-copy">
            <span class="nav-label">{{ item.label }}</span>
            <span class="nav-desc">{{ item.desc }}</span>
          </span>
        </RouterLink>
      </nav>
    </div>

    <p class="sidebar-foot">Study period 1946–2026 · Local CSV driven</p>
  </aside>
</template>
