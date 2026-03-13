<script setup>
defineProps({
  name: {
    type: String,
    required: true,
  },
  class: {
    type: String,
    default: '',
  },
})
</script>

<template>
  <span class="material-symbols-outlined" :class="$props.class">{{ name }}</span>
</template>
