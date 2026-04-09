import { afterEach, describe, expect, it, vi } from 'vitest'

async function loadComposable({
  firstElement,
  secondElement,
  loadStripeOverrides,
} = {}) {
  vi.resetModules()
  vi.stubEnv('VITE_STRIPE_PUBLISHABLE_KEY', 'pk_test_ticketblitz')

  const fallbackElement = {
    mount: vi.fn(),
    unmount: vi.fn(),
    destroy: vi.fn(),
  }

  const createdElements = []
  const create = vi.fn(() => {
    const next = createdElements.length === 0 ? (firstElement || fallbackElement) : (secondElement || firstElement || fallbackElement)
    createdElements.push(next)
    return next
  })

  const stripe = {
    elements: vi.fn(() => ({
      create,
      submit: vi.fn().mockResolvedValue({ error: null }),
    })),
    confirmPayment: vi.fn().mockResolvedValue({ error: null, paymentIntent: null }),
    ...(loadStripeOverrides || {}),
  }

  const loadStripe = vi.fn().mockResolvedValue(stripe)

  vi.doMock('@stripe/stripe-js', () => ({
    loadStripe,
  }))

  const { useStripePaymentElement } = await import('./useStripePaymentElement.js')

  return {
    composable: useStripePaymentElement(),
    loadStripe,
    stripe,
    create,
    createdElements,
  }
}

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllEnvs()
  vi.resetModules()
})

describe('useStripePaymentElement', () => {
  it('does not throw when unmounting an already destroyed element', async () => {
    const alreadyDestroyed = 'This Element has already been destroyed. Please create a new one.'
    const firstElement = {
      mount: vi.fn(),
      unmount: vi.fn(() => {
        throw new Error(alreadyDestroyed)
      }),
      destroy: vi.fn(() => {
        throw new Error(alreadyDestroyed)
      }),
    }

    const { composable } = await loadComposable({ firstElement })

    await composable.mount({
      clientSecret: 'secret_1',
      mountNode: {},
    })

    expect(() => composable.unmount()).not.toThrow()
    expect(() => composable.unmount()).not.toThrow()
    expect(composable.errorMessage.value).toBe('')
  })

  it('captures unexpected cleanup errors without interrupting callers', async () => {
    const firstElement = {
      mount: vi.fn(),
      unmount: vi.fn(() => {
        throw new Error('unexpected teardown failure')
      }),
      destroy: vi.fn(() => {
        throw new Error('unexpected destroy failure')
      }),
    }

    const { composable } = await loadComposable({ firstElement })

    await composable.mount({
      clientSecret: 'secret_1',
      mountNode: {},
    })

    expect(() => composable.unmount()).not.toThrow()
    expect(composable.errorMessage.value).toBe('Payment form cleanup encountered an issue.')
  })

  it('cleans up previous Stripe element before remounting', async () => {
    const firstElement = {
      mount: vi.fn(),
      unmount: vi.fn(),
      destroy: vi.fn(),
    }

    const secondElement = {
      mount: vi.fn(),
      unmount: vi.fn(),
      destroy: vi.fn(),
    }

    const { composable, create, createdElements } = await loadComposable({
      firstElement,
      secondElement,
    })

    await composable.mount({
      clientSecret: 'secret_1',
      mountNode: {},
    })

    await composable.mount({
      clientSecret: 'secret_2',
      mountNode: {},
    })

    expect(create).toHaveBeenCalledTimes(2)
    expect(createdElements).toEqual([firstElement, secondElement])
    expect(firstElement.unmount).toHaveBeenCalledTimes(1)
    expect(firstElement.destroy).toHaveBeenCalledTimes(1)
  })
})
