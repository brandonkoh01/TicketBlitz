<script setup>
import { computed } from "vue";

const props = defineProps({
  steps: {
    type: Array,
    default: () => [],
  },
  currentStep: {
    type: Number,
    default: 0,
  },
  tone: {
    type: String,
    default: "neutral",
  },
  statusText: {
    type: String,
    default: "",
  },
});

const safeSteps = computed(() =>
  props.steps.map((step) => String(step || "").trim()).filter(Boolean),
);

const normalizedIndex = computed(() => {
  if (safeSteps.value.length === 0) return 0;
  const maxIndex = safeSteps.value.length - 1;
  return Math.min(Math.max(Number(props.currentStep || 0), 0), maxIndex);
});

const progressPercent = computed(() => {
  if (safeSteps.value.length <= 1) return 100;
  return Math.round(
    (normalizedIndex.value / (safeSteps.value.length - 1)) * 100,
  );
});

const fillClasses = computed(() => {
  if (props.tone === "warning") return "bg-[var(--swiss-accent)]";
  if (props.tone === "error") return "bg-black";
  if (props.tone === "success") return "bg-black";
  return "bg-black";
});
</script>

<template>
  <div class="border-2 border-black bg-white p-3">
    <div class="h-2 w-full border border-black bg-[var(--swiss-muted)]">
      <div
        class="h-full transition-all duration-300 ease-out"
        :class="fillClasses"
        :style="{ width: `${progressPercent}%` }"
      />
    </div>

    <div
      v-if="safeSteps.length > 0"
      class="mt-3 grid gap-2 text-[10px] font-black uppercase tracking-[0.1em] md:grid-cols-4"
    >
      <p
        v-for="(step, index) in safeSteps"
        :key="`${step}-${index}`"
        :class="index <= normalizedIndex ? 'text-black' : 'text-black/40'"
      >
        {{ step }}
      </p>
    </div>

    <p
      v-if="statusText"
      class="mt-3 text-[10px] font-bold uppercase tracking-[0.1em] text-black/70"
    >
      {{ statusText }}
    </p>
  </div>
</template>
