import { ref } from 'vue'
import { loadStripe } from '@stripe/stripe-js'

const publishableKey = (import.meta.env.VITE_STRIPE_PUBLISHABLE_KEY || '').trim()
let stripePromise = null

async function getStripe() {
  if (!publishableKey) {
    throw new Error('Stripe publishable key is missing. Set VITE_STRIPE_PUBLISHABLE_KEY in frontend/.env.local.')
  }

  if (!stripePromise) {
    stripePromise = loadStripe(publishableKey)
  }

  return stripePromise
}

export function useStripePaymentElement() {
  const isReady = ref(false)
  const isSubmitting = ref(false)
  const errorMessage = ref('')

  let stripe = null
  let elements = null
  let paymentElement = null

  async function mount({ clientSecret, mountNode }) {
    errorMessage.value = ''

    if (!clientSecret) {
      throw new Error('Client secret is required to mount Stripe Payment Element.')
    }

    if (!mountNode) {
      throw new Error('Missing mount node for Stripe Payment Element.')
    }

    stripe = await getStripe()
    elements = stripe.elements({
      clientSecret,
      appearance: {
        theme: 'stripe',
      },
    })

    paymentElement = elements.create('payment')
    paymentElement.mount(mountNode)
    isReady.value = true
  }

  async function confirmPayment({ returnUrl }) {
    if (!stripe || !elements) {
      throw new Error('Payment form is not ready yet.')
    }

    errorMessage.value = ''
    isSubmitting.value = true

    try {
      const submitResult = await elements.submit()
      if (submitResult.error) {
        throw new Error(submitResult.error.message)
      }

      const { error, paymentIntent } = await stripe.confirmPayment({
        elements,
        confirmParams: {
          return_url: returnUrl,
        },
        redirect: 'if_required',
      })

      if (error) {
        throw new Error(error.message)
      }

      return paymentIntent || null
    } finally {
      isSubmitting.value = false
    }
  }

  function unmount() {
    if (paymentElement) {
      paymentElement.unmount()
      paymentElement.destroy()
      paymentElement = null
    }

    elements = null
    isReady.value = false
  }

  return {
    isReady,
    isSubmitting,
    errorMessage,
    mount,
    confirmPayment,
    unmount,
  }
}
