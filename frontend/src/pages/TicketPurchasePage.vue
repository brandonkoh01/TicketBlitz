<script setup>
const navItems = [
  { label: 'Events', to: '#' },
  { label: 'Venues', to: '#' },
  { label: 'My Tickets', to: '#' },
  { label: 'Dashboard', to: '/organiser-dashboard' },
]

const footerGroups = [
  {
    title: 'Navigation',
    links: ['Press Kit', 'Privacy Policy', 'Terms of Service'],
  },
  {
    title: 'Connect',
    links: ['Share', 'Language', 'Mail'],
  },
]

function handleSubmit(event) {
  event.preventDefault()
}
</script>

<template>
  <main class="min-h-screen bg-[var(--swiss-bg)] text-[var(--swiss-fg)]">
    <header class="border-b-4 border-black bg-white">
      <div class="mx-auto flex max-w-[1800px] items-center justify-between gap-4 px-6 py-5 md:px-10">
        <div>
          <p class="text-sm font-black uppercase tracking-[0.28em]">TicketBlitz</p>
          <p class="text-[10px] font-medium uppercase tracking-[0.22em] text-black/65">Main Page 01</p>
        </div>

        <nav class="hidden items-center gap-6 lg:flex">
          <component
            :is="item.to === '#' ? 'a' : 'RouterLink'"
            v-for="item in navItems"
            :key="item.label"
            :to="item.to !== '#' ? item.to : undefined"
            :href="item.to === '#' ? '#' : undefined"
            class="swiss-link-slide text-xs font-black uppercase tracking-[0.2em] focus-visible:outline-none"
            :data-alt="item.label"
          >
            <span>{{ item.label }}</span>
          </component>
        </nav>

        <div class="flex items-center gap-3">
          <button
            type="button"
            aria-label="Search"
            class="inline-flex h-11 w-11 items-center justify-center border-2 border-black text-lg font-black transition duration-200 ease-out hover:bg-black hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--swiss-accent)] focus-visible:ring-offset-2"
          >
            ⌕
          </button>
          <UiButton variant="primary" class="min-w-[9rem]">Sign Up</UiButton>
        </div>
      </div>
    </header>

    <section class="border-b-4 border-black bg-white">
      <div class="mx-auto max-w-[1800px] px-6 py-7 md:px-10 md:py-9">
        <SectionLabel index="06." label="Concert Checkout" />
        <h1 class="mt-8 text-[clamp(2.2rem,6vw,5.2rem)] font-black uppercase leading-[0.9] tracking-[-0.04em]">
          Complete Your
          <br>
          Booking Details
        </h1>
        <p class="mt-5 max-w-3xl text-sm uppercase leading-relaxed tracking-[0.04em] md:text-base">
          You're signed in. Enter contact and payment details to continue with your concert ticket purchase.
        </p>
      </div>
    </section>

    <section class="border-b-4 border-black">
      <div class="mx-auto grid max-w-[1800px] grid-cols-1 gap-0 lg:grid-cols-12">
        <div class="swiss-grid-pattern border-b-4 border-black p-6 md:p-10 lg:col-span-8 lg:border-b-0 lg:border-r-4 lg:p-14">
          <SectionLabel index="07." label="Buyer Information" />

          <form class="mt-8 space-y-6" @submit="handleSubmit">
            <div class="grid gap-5 md:grid-cols-2">
              <label class="block">
                <span class="mb-2 block text-[11px] font-black uppercase tracking-[0.22em]">Full Name</span>
                <input
                  type="text"
                  name="fullName"
                  autocomplete="name"
                  required
                  class="w-full border-2 border-black bg-white px-4 py-3 text-sm font-medium outline-none transition duration-200 ease-out focus:border-[var(--swiss-accent)]"
                  placeholder="Your full name"
                >
              </label>

              <label class="block">
                <span class="mb-2 block text-[11px] font-black uppercase tracking-[0.22em]">Contact Email</span>
                <input
                  type="email"
                  name="email"
                  autocomplete="email"
                  required
                  class="w-full border-2 border-black bg-white px-4 py-3 text-sm font-medium outline-none transition duration-200 ease-out focus:border-[var(--swiss-accent)]"
                  placeholder="name@email.com"
                >
              </label>
            </div>

            <label class="block">
              <span class="mb-2 block text-[11px] font-black uppercase tracking-[0.22em]">Contact Number</span>
              <input
                type="tel"
                name="phone"
                autocomplete="tel"
                required
                class="w-full border-2 border-black bg-white px-4 py-3 text-sm font-medium outline-none transition duration-200 ease-out focus:border-[var(--swiss-accent)]"
                placeholder="+65 8123 4567"
              >
            </label>

            <div class="border-t-2 border-black pt-6">
              <p class="text-sm font-black uppercase tracking-[0.18em]">Payment Details</p>

              <div class="mt-5 space-y-5">
                <label class="block">
                  <span class="mb-2 block text-[11px] font-black uppercase tracking-[0.22em]">Cardholder Name</span>
                  <input
                    type="text"
                    name="cardholderName"
                    autocomplete="cc-name"
                    required
                    class="w-full border-2 border-black bg-white px-4 py-3 text-sm font-medium outline-none transition duration-200 ease-out focus:border-[var(--swiss-accent)]"
                    placeholder="Name on card"
                  >
                </label>

                <label class="block">
                  <span class="mb-2 block text-[11px] font-black uppercase tracking-[0.22em]">Card Number</span>
                  <input
                    type="text"
                    name="cardNumber"
                    autocomplete="cc-number"
                    inputmode="numeric"
                    required
                    class="w-full border-2 border-black bg-white px-4 py-3 text-sm font-medium outline-none transition duration-200 ease-out focus:border-[var(--swiss-accent)]"
                    placeholder="1234 5678 9012 3456"
                  >
                </label>

                <div class="grid gap-5 md:grid-cols-2">
                  <label class="block">
                    <span class="mb-2 block text-[11px] font-black uppercase tracking-[0.22em]">Expiry Date</span>
                    <input
                      type="text"
                      name="expiryDate"
                      autocomplete="cc-exp"
                      inputmode="numeric"
                      required
                      class="w-full border-2 border-black bg-white px-4 py-3 text-sm font-medium outline-none transition duration-200 ease-out focus:border-[var(--swiss-accent)]"
                      placeholder="MM / YY"
                    >
                  </label>

                  <label class="block">
                    <span class="mb-2 block text-[11px] font-black uppercase tracking-[0.22em]">CVV</span>
                    <input
                      type="password"
                      name="cvv"
                      autocomplete="cc-csc"
                      inputmode="numeric"
                      required
                      class="w-full border-2 border-black bg-white px-4 py-3 text-sm font-medium outline-none transition duration-200 ease-out focus:border-[var(--swiss-accent)]"
                      placeholder="***"
                    >
                  </label>
                </div>
              </div>
            </div>

            <div class="flex flex-col gap-4 border-t-2 border-black pt-6 sm:flex-row">
              <UiButton type="submit" variant="primary" :full-width="true" class="sm:w-auto">
                Continue
              </UiButton>
              <RouterLink
                to="/"
                class="inline-flex h-14 w-full items-center justify-center border-2 border-black bg-white px-6 text-xs font-black uppercase tracking-[0.24em] transition duration-200 ease-out hover:bg-black hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--swiss-accent)] focus-visible:ring-offset-2 sm:w-auto sm:min-w-[12rem]"
              >
                Back
              </RouterLink>
            </div>
          </form>
        </div>

        <aside class="swiss-dots bg-[var(--swiss-muted)] p-6 md:p-10 lg:col-span-4 lg:p-14">
          <SectionLabel index="08." label="Order Summary" />

          <div class="mt-8 border-4 border-black bg-white p-6">
            <p class="text-xs font-bold uppercase tracking-[0.2em] text-black/70">Selected Concert</p>
            <h2 class="mt-4 text-3xl font-black uppercase leading-[0.92] tracking-tight">Rock Revival 2026</h2>

            <div class="mt-6 space-y-3 border-t-2 border-black pt-4 text-sm font-medium">
              <div class="flex items-center justify-between">
                <span>Date</span>
                <span class="font-black">Dec 02 2026</span>
              </div>
              <div class="flex items-center justify-between">
                <span>Venue</span>
                <span class="font-black">London Arena</span>
              </div>
              <div class="flex items-center justify-between">
                <span>Seat Category</span>
                <span class="font-black">General Admission</span>
              </div>
              <div class="flex items-center justify-between">
                <span>Quantity</span>
                <span class="font-black">1 Ticket</span>
              </div>
            </div>

            <div class="mt-6 border-t-2 border-black pt-4">
              <div class="flex items-center justify-between text-base">
                <span class="font-black uppercase tracking-[0.08em]">Total</span>
                <span class="text-xl font-black">$125.00</span>
              </div>
            </div>
          </div>

          <p class="mt-5 text-xs font-medium uppercase tracking-[0.14em] text-black/60">
            UI-only page. No live inventory, pricing, or payment processing connected yet.
          </p>
        </aside>
      </div>
    </section>

    <footer class="bg-black px-6 py-14 text-white md:px-10 md:py-20">
      <div class="mx-auto grid max-w-[1800px] gap-10 lg:grid-cols-12">
        <div class="lg:col-span-7">
          <p class="text-xs font-black uppercase tracking-[0.3em] text-[var(--swiss-accent)]">05. TicketBlitz International</p>
          <h2 class="mt-5 text-5xl font-black uppercase leading-[0.88] tracking-[-0.04em] md:text-7xl">TicketBlitz</h2>
          <p class="mt-6 max-w-xl text-sm leading-relaxed text-white/80 md:text-base">
            The world's fastest ticketing platform for high-demand experiences.
          </p>
        </div>

        <div class="grid gap-8 sm:grid-cols-2 lg:col-span-5">
          <FooterLinkGroup
            v-for="group in footerGroups"
            :key="group.title"
            :title="group.title"
            :links="group.links"
          />
        </div>

        <p class="border-t-2 border-white/20 pt-6 text-[11px] font-medium uppercase tracking-[0.2em] text-white/70 lg:col-span-12">
          ©2026 TicketBlitz International
        </p>
      </div>
    </footer>
  </main>
</template>