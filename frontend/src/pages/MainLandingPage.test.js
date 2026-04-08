import { afterEach, describe, expect, it, vi } from 'vitest'

async function mountPage({ upcomingEvents = [], featuredEvent = null } = {}) {
  vi.resetModules()

  vi.doMock('@/composables/useHomeEventShowcase', async () => {
    const { ref } = await import('vue')

    return {
      useHomeEventShowcase: () => ({
        heroBanners: ref([
          { label: 'Global Tickets Sold', value: '2.5M+' },
          { label: 'Partner Venues', value: '120' },
          { label: 'Verified Artists', value: '500+' },
        ]),
        upcomingEvents: ref(upcomingEvents),
        featuredEvent: ref(featuredEvent),
        loadingUpcoming: ref(false),
        loadingFeatured: ref(false),
        upcomingErrorMessage: ref(''),
        featuredErrorMessage: ref(''),
        reloadHome: vi.fn(),
      }),
    }
  })

  const { createApp, nextTick } = await import('vue')
  const { default: MainLandingPage } = await import('./MainLandingPage.vue')

  const container = document.createElement('div')
  document.body.appendChild(container)

  const app = createApp(MainLandingPage)
  app.component('AppTopNav', {
    props: {
      pageLabel: { type: String, default: '' },
    },
    template: '<header data-test="top-nav">{{ pageLabel }}</header>',
  })
  app.component('SectionLabel', {
    props: {
      index: { type: String, default: '' },
      label: { type: String, default: '' },
    },
    template: '<div data-test="section-label">{{ index }} {{ label }}</div>',
  })
  app.component('MetricCard', {
    props: {
      label: { type: String, default: '' },
      value: { type: String, default: '' },
    },
    template: '<div data-test="metric-card">{{ label }} {{ value }}</div>',
  })
  app.component('HomeHeroBannerStrip', {
    props: {
      banners: { type: Array, default: () => [] },
    },
    template: '<div data-test="hero-banners"><span v-for="banner in banners" :key="banner.label">{{ banner.label }} {{ banner.value }}</span></div>',
  })
  app.component('UiButton', {
    props: {
      to: { type: [String, Object], default: '' },
    },
    template: '<a :href="typeof to === \'string\' ? to : \'#\'"><slot /></a>',
  })
  app.component('HomeFeaturedEventPanel', {
    props: {
      event: { type: Object, default: null },
      loading: { type: Boolean, default: false },
      errorMessage: { type: String, default: '' },
    },
    template: '<div data-test="featured-panel">{{ loading ? \'loading\' : event?.name || errorMessage || \'none\' }}</div>',
  })
  app.component('HomeUpcomingEventsSection', {
    props: {
      events: { type: Array, default: () => [] },
      loading: { type: Boolean, default: false },
      errorMessage: { type: String, default: '' },
    },
    template: '<div data-test="upcoming-panel">UPCOMING_COUNT:{{ events.length }} <span v-for="event in events" :key="event.id">{{ event.title }}</span> {{ loading ? \'loading\' : errorMessage }}</div>',
  })
  app.component('FooterLinkGroup', {
    props: {
      title: { type: String, default: '' },
      links: { type: Array, default: () => [] },
    },
    template: '<div data-test="footer-links">{{ title }}</div>',
  })

  app.mount(container)
  await nextTick()

  return {
    app,
    container,
  }
}

afterEach(() => {
  vi.restoreAllMocks()
  vi.resetModules()
  document.body.innerHTML = ''
})

describe('MainLandingPage', () => {
  it('removes Live Map CTA and renders Richard Boone as featured event', async () => {
    const { app, container } = await mountPage({
      featuredEvent: {
        id: '10000000-0000-0000-0000-000000000501',
        name: 'Richard Boone Asia Tour 2026',
        venue: 'Singapore Indoor Arena',
        dateLabel: '12/07/26 08:00 PM SGT',
        copy: 'Regional multi-city headline concert experience.',
        detailTo: '/events/10000000-0000-0000-0000-000000000501',
      },
    })

    expect(container.textContent).toContain('Explore Events')
    expect(container.textContent).toContain('Global Tickets Sold 2.5M+')
    expect(container.textContent).toContain('Partner Venues 120')
    expect(container.textContent).toContain('Verified Artists 500+')
    expect(container.textContent).toContain('Richard Boone Asia Tour 2026')
    expect(container.textContent).not.toContain('Live Map')

    app.unmount()
  })

  it('renders top three upcoming events from live mapping', async () => {
    const { app, container } = await mountPage({
      featuredEvent: {
        id: '10000000-0000-0000-0000-000000000501',
        name: 'Richard Boone Asia Tour 2026',
        venue: 'Singapore Indoor Arena',
        dateLabel: '12/07/26 08:00 PM SGT',
        copy: 'Regional multi-city headline concert experience.',
        detailTo: '/events/10000000-0000-0000-0000-000000000501',
      },
      upcomingEvents: [
        {
          id: '10000000-0000-0000-0000-000000000301',
          title: 'Coldplay Live 2026',
        },
        {
          id: '10000000-0000-0000-0000-000000000501',
          title: 'Richard Boone Asia Tour 2026',
        },
        {
          id: '10000000-0000-0000-0000-000000000502',
          title: 'Lawrence Wong Guitar Solo',
        },
      ],
    })

    expect(container.textContent).toContain('UPCOMING_COUNT:3')
    expect(container.textContent).toContain('Coldplay Live 2026')
    expect(container.textContent).toContain('Richard Boone Asia Tour 2026')
    expect(container.textContent).toContain('Lawrence Wong Guitar Solo')
    expect(container.textContent).not.toContain('Synthwave Night')

    app.unmount()
  })
})