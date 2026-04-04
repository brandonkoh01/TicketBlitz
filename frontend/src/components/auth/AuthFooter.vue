<script setup>
const footerLinks = [
  { label: 'Privacy Policy', href: '#' },
  { label: 'Terms of Service', href: '#' },
  { label: 'Accessibility', href: '#' },
  { label: 'Contact', href: '#' },
]
</script>

<template>
  <footer class="relative z-10 border-t-4 border-black bg-white">
    <div class="mx-auto grid w-full max-w-[1440px] grid-cols-1 gap-10 px-6 py-14 md:grid-cols-2 md:gap-12">
      <div class="flex flex-col justify-between gap-6">
        <p class="text-[clamp(2.4rem,7vw,5.5rem)] font-black uppercase leading-[0.85] tracking-[-0.06em]">
          Ticket
          <br>
          Blitz
        </p>
        <p class="text-[11px] font-black uppercase tracking-[0.16em]">©2026 TicketBlitz. Engineered Precision.</p>
      </div>

      <div class="grid grid-cols-2 gap-6 md:gap-8">
        <a
          v-for="item in footerLinks"
          :key="item.label"
          :href="item.href"
          class="text-sm font-black uppercase tracking-[0.1em] transition duration-150 ease-linear hover:text-[var(--swiss-accent)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--swiss-accent)] focus-visible:ring-offset-2"
        >
          {{ item.label }}
        </a>
      </div>
    </div>
  </footer>
</template>
