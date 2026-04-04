<script setup>
import { ref } from 'vue'
import AuthFormField from '@/components/auth/AuthFormField.vue'

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
  placeholder: {
    type: String,
    default: '',
  },
  autocomplete: {
    type: String,
    default: 'current-password',
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

const emit = defineEmits(['input'])
const showPassword = ref(false)

function handleInput(event) {
  emit('input', event)
}
</script>

<template>
  <AuthFormField
    :id="id"
    v-model="model"
    :type="showPassword ? 'text' : 'password'"
    :label="label"
    :placeholder="placeholder"
    :autocomplete="autocomplete"
    :required="required"
    :disabled="disabled"
    @input="handleInput"
  >
    <template #trailing>
      <button
        type="button"
        class="inline-flex h-9 min-w-[3.4rem] items-center justify-center border-2 border-black bg-white px-2 text-[11px] font-black uppercase transition duration-150 ease-linear hover:bg-black hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--swiss-accent)]"
        :aria-label="showPassword ? 'Hide password' : 'Show password'"
        @click="showPassword = !showPassword"
      >
        {{ showPassword ? 'Hide' : 'View' }}
      </button>
    </template>
  </AuthFormField>
</template>