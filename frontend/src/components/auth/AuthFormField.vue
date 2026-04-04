<script setup>
const model = defineModel({
  type: String,
  default: '',
})

defineProps({
  id: {
    type: String,
    required: true,
  },
  label: {
    type: String,
    required: true,
  },
  type: {
    type: String,
    default: 'text',
  },
  placeholder: {
    type: String,
    default: '',
  },
  autocomplete: {
    type: String,
    default: undefined,
  },
  inputmode: {
    type: String,
    default: undefined,
  },
  required: {
    type: Boolean,
    default: false,
  },
  disabled: {
    type: Boolean,
    default: false,
  },
})
</script>

<template>
  <div class="space-y-2">
    <label :for="id" class="block text-[11px] font-black uppercase tracking-[0.18em]">{{ label }}</label>

    <div class="relative">
      <input
        :id="id"
        v-model="model"
        :type="type"
        :placeholder="placeholder"
        :autocomplete="autocomplete"
        :inputmode="inputmode"
        :required="required"
        :disabled="disabled"
        class="h-14 w-full border-4 border-black bg-transparent px-4 text-sm font-bold outline-none transition duration-150 ease-linear placeholder:font-medium placeholder:text-black/30 focus:bg-[var(--swiss-muted)] disabled:cursor-not-allowed disabled:opacity-60"
      >

      <div v-if="$slots.trailing" class="pointer-events-none absolute inset-y-0 right-4 flex items-center">
        <div class="pointer-events-auto">
          <slot name="trailing" />
        </div>
      </div>
    </div>
  </div>
</template>
