import { computed, onUnmounted, ref, watch } from 'vue'

export function useHoldCountdown(holdExpiryRef) {
  const now = ref(Date.now())
  let intervalId = null

  function start() {
    if (intervalId) return
    intervalId = window.setInterval(() => {
      now.value = Date.now()
    }, 1000)
  }

  function stop() {
    if (!intervalId) return
    window.clearInterval(intervalId)
    intervalId = null
  }

  watch(
    holdExpiryRef,
    (value) => {
      if (value) {
        start()
      } else {
        stop()
      }
    },
    { immediate: true }
  )

  const secondsRemaining = computed(() => {
    const raw = holdExpiryRef.value
    if (!raw) return 0

    const expiry = new Date(raw).getTime()
    if (Number.isNaN(expiry)) return 0

    return Math.max(0, Math.floor((expiry - now.value) / 1000))
  })

  const isExpired = computed(() => secondsRemaining.value <= 0)

  const label = computed(() => {
    const totalSeconds = secondsRemaining.value
    const minutes = Math.floor(totalSeconds / 60)
    const seconds = totalSeconds % 60
    return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
  })

  onUnmounted(() => {
    stop()
  })

  return {
    secondsRemaining,
    isExpired,
    label,
  }
}
