<script setup>
import { computed, onMounted, ref } from "vue";
import QRCode from "qrcode";
import { useAuthStore } from "@/stores/authStore";
import { useRoleNavigation } from "@/composables/useRoleNavigation";
import { useUserBookings } from "@/composables/useUserBookings";
import { useTicketCancellation } from "@/composables/useTicketCancellation";

const authStore = useAuthStore();
const isAuthenticated = computed(() => authStore.isAuthenticated.value);
const { primaryNavItems: navItems } = useRoleNavigation();
const {
  tickets: purchasedTickets,
  loading: isLoading,
  errorMessage: loadError,
  requestState: ticketRequestState,
  refreshTickets,
} = useUserBookings();
const ticketCancellation = useTicketCancellation();
const activeCancellationBookingID = ref("");
const cancellationTargetTicket = ref(null);
const cancellationDialogError = ref("");

const footerGroups = [
  {
    title: "Navigation",
    links: ["Press Kit", "Privacy Policy", "Terms of Service"],
  },
  {
    title: "Connect",
    links: ["Share", "Language", "Mail"],
  },
];

const hasLoadError = computed(() => Boolean(loadError.value));
const isEndpointMissingError = computed(
  () => ticketRequestState.value.kind === "endpoint-missing",
);
const ticketErrorTone = computed(() =>
  isEndpointMissingError.value ? "warning" : "error",
);
const ticketErrorEyebrow = computed(() =>
  isEndpointMissingError.value ? "OutSystems Integration" : "Ticket Service",
);
const ticketErrorTitle = computed(() => {
  if (isEndpointMissingError.value) {
    return "You have no tickets yet";
  }

  return "Unable to Load Ticket List";
});
const hasCancellationFeedback = computed(
  () =>
    ticketCancellation.status.value !== "IDLE" ||
    Boolean(ticketCancellation.message.value),
);
const cancellationNoticeTone = computed(() => {
  const status = String(ticketCancellation.status.value || "").toUpperCase();
  if (status === "DENIED") return "warning";
  if (status === "REFUND_COMPLETED" || status === "REALLOCATION_CONFIRMED")
    return "neutral";
  return "error";
});
const cancellationNoticeTitle = computed(() => {
  const status = String(ticketCancellation.status.value || "").toUpperCase();
  if (status === "DENIED") return "Cancellation Denied";
  if (status === "REFUND_COMPLETED") return "Refund Completed";
  if (status === "REALLOCATION_PENDING") return "Reallocation Pending";
  if (status === "REALLOCATION_CONFIRMED") return "Reallocation Confirmed";
  if (status === "CANCELLATION_IN_PROGRESS") return "Cancellation In Progress";
  if (status === "ALREADY_REFUNDED") return "Already Refunded";
  return "Cancellation Update";
});
const isCancellationModalVisible = computed(() =>
  Boolean(cancellationTargetTicket.value),
);
const cancellationPreview = computed(() => {
  if (!cancellationTargetTicket.value) return null;
  return getRefundBreakdown(cancellationTargetTicket.value, null);
});
const cancellationProgressState = computed(() => {
  const steps = [
    "Request Received",
    "Refund Processing",
    "Seat Resolution",
    "Completed",
  ];
  const status = String(ticketCancellation.status.value || "").toUpperCase();

  if (ticketCancellation.isSubmitting.value) {
    return {
      steps,
      currentStep: 0,
      tone: "neutral",
      statusText: "Submitting your cancellation request.",
    };
  }

  if (status === "CANCELLATION_IN_PROGRESS") {
    return {
      steps,
      currentStep: 1,
      tone: "neutral",
      statusText: "Refund is being processed.",
    };
  }

  if (status === "REALLOCATION_PENDING") {
    return {
      steps,
      currentStep: 2,
      tone: "warning",
      statusText: "Refund started. Seat reallocation is pending.",
    };
  }

  if (
    ["REFUND_COMPLETED", "REALLOCATION_CONFIRMED", "ALREADY_REFUNDED"].includes(
      status,
    )
  ) {
    return {
      steps,
      currentStep: 3,
      tone: "success",
      statusText: "Cancellation finalized successfully.",
    };
  }

  if (status === "DENIED") {
    return {
      steps,
      currentStep: 0,
      tone: "warning",
      statusText: "Cancellation is not eligible under policy.",
    };
  }

  return {
    steps,
    currentStep: 0,
    tone: "neutral",
    statusText: "Ready to request cancellation.",
  };
});
const cancellationModalProgressState = computed(() => {
  if (ticketCancellation.isSubmitting.value) {
    return {
      ...cancellationProgressState.value,
      statusText: "Submitting cancellation and validating refund.",
    };
  }

  return {
    steps: [
      "Request Received",
      "Refund Processing",
      "Seat Resolution",
      "Completed",
    ],
    currentStep: 0,
    tone: "neutral",
    statusText: "Review details, then confirm cancellation.",
  };
});

const selectedTicket = ref(null);
const passQrDataUrl = ref("");
const passQrError = ref("");

function parseAmount(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function formatCurrency(amount, currency = "SGD") {
  if (amount == null) return "N/A";

  try {
    return new Intl.NumberFormat("en-SG", {
      style: "currency",
      currency,
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(amount);
  } catch {
    return `${currency} ${amount.toFixed(2)}`;
  }
}

function getRefundBreakdown(ticket, result) {
  const currency = String(ticket?.currency || "SGD").toUpperCase();
  const baseAmount = parseAmount(ticket?.amount);
  const feeAmount =
    baseAmount == null ? null : Number((baseAmount * 0.1).toFixed(2));
  const expectedRefundAmount =
    baseAmount == null ? null : Number((baseAmount - feeAmount).toFixed(2));

  const resolvedStatus = String(result?.status || "").toUpperCase();
  let actualRefundAmount =
    parseAmount(result?.refundAmount) ??
    parseAmount(ticket?.refundAmount) ??
    expectedRefundAmount;

  if (
    ["REFUND_COMPLETED", "REALLOCATION_CONFIRMED", "ALREADY_REFUNDED"].includes(
      resolvedStatus,
    ) &&
    actualRefundAmount != null &&
    actualRefundAmount <= 0 &&
    expectedRefundAmount != null
  ) {
    actualRefundAmount = expectedRefundAmount;
  }

  return {
    currency,
    baseAmount,
    feeAmount,
    expectedRefundAmount,
    actualRefundAmount,
    baseLabel: formatCurrency(baseAmount, currency),
    feeLabel: formatCurrency(feeAmount, currency),
    expectedRefundLabel: formatCurrency(expectedRefundAmount, currency),
    actualRefundLabel: formatCurrency(actualRefundAmount, currency),
  };
}

function openPass(ticket) {
  selectedTicket.value = ticket;
  generatePassQr(ticket);
}

function closePass() {
  selectedTicket.value = null;
  passQrDataUrl.value = "";
  passQrError.value = "";
}

function isCancellingTicket(ticket) {
  if (!ticket) return false;
  return (
    activeCancellationBookingID.value ===
    String(ticket.bookingID || ticket.ticketID || ticket.holdID || "")
  );
}

function canCancelTicket(ticket) {
  const lifecycleStatus = String(ticket?.lifecycleStatus || "").toUpperCase();
  const paymentStatus = String(ticket?.paymentStatus || "").toUpperCase();
  return lifecycleStatus === "CONFIRMED" && paymentStatus === "SUCCEEDED";
}

function openCancellationModal(ticket) {
  if (!canCancelTicket(ticket)) return;
  cancellationDialogError.value = "";
  cancellationTargetTicket.value = ticket;
}

function closeCancellationModal() {
  if (ticketCancellation.isSubmitting.value) return;
  cancellationDialogError.value = "";
  cancellationTargetTicket.value = null;
}

async function confirmCancellation() {
  const ticket = cancellationTargetTicket.value;
  if (!ticket) return;

  const bookingID = String(ticket?.bookingID || ticket?.ticketID || "").trim();
  const userID = String(authStore.state.user?.id || "").trim();

  if (!bookingID || !userID) {
    cancellationDialogError.value =
      "Unable to cancel this ticket right now. Please refresh and try again.";
    return;
  }

  cancellationDialogError.value = "";
  activeCancellationBookingID.value = bookingID;

  try {
    const result = await ticketCancellation.cancelTicket({
      bookingID,
      userID,
      newHoldID: ticket?.newHoldID || null,
    });

    const finalBreakdown = getRefundBreakdown(ticket, result);
    const status = String(result.status || "").toUpperCase();

    if (
      [
        "REFUND_COMPLETED",
        "REALLOCATION_CONFIRMED",
        "ALREADY_REFUNDED",
      ].includes(status)
    ) {
      ticketCancellation.message.value =
        `10% cancellation fee (${finalBreakdown.feeLabel}) was deducted. ` +
        `Final refunded amount: ${finalBreakdown.actualRefundLabel}.`;
    }

    if (status === "REALLOCATION_PENDING") {
      ticketCancellation.message.value =
        `10% cancellation fee (${finalBreakdown.feeLabel}) will be deducted. ` +
        `Expected refund amount: ${finalBreakdown.expectedRefundLabel}.`;
    }

    if (status === "DENIED") {
      const deniedEventName = String(ticket?.eventName || "This event").trim();
      const deniedReason = String(
        result.reason ||
          ticketCancellation.message.value ||
          "Not eligible under 48-hour cancellation policy.",
      ).trim();
      ticketCancellation.message.value = `${deniedEventName} cannot be cancelled. ${deniedReason}`;
    }

    const statusesToRefresh = new Set([
      "CANCELLATION_IN_PROGRESS",
      "REALLOCATION_PENDING",
      "DENIED",
      "ALREADY_REFUNDED",
      "REFUND_COMPLETED",
      "REALLOCATION_CONFIRMED",
    ]);

    if (statusesToRefresh.has(status)) {
      await refreshTickets();
    }

    closeCancellationModal();
  } catch (error) {
    cancellationDialogError.value =
      error?.message ||
      "Unable to process cancellation right now. Please try again.";
  } finally {
    activeCancellationBookingID.value = "";
  }
}

async function generatePassQr(ticket) {
  passQrDataUrl.value = "";
  passQrError.value = "";

  const qrValue = ticket?.ticketID;
  if (!qrValue) {
    passQrError.value = "QR unavailable";
    return;
  }

  try {
    passQrDataUrl.value = await QRCode.toDataURL(qrValue, {
      errorCorrectionLevel: "M",
      margin: 1,
      width: 256,
      color: {
        dark: "#000000",
        light: "#FFFFFF",
      },
    });
  } catch (error) {
    passQrError.value = "Unable to render QR";
  }
}

onMounted(() => {
  refreshTickets();
});
</script>

<template>
  <main class="min-h-screen bg-[var(--swiss-bg)] text-[var(--swiss-fg)]">
    <header class="border-b-4 border-black bg-white">
      <div
        class="mx-auto flex max-w-[1800px] items-center justify-between gap-4 px-6 py-5 md:px-10"
      >
        <RouterLink to="/" class="block focus-visible:outline-none">
          <p class="text-sm font-black uppercase tracking-[0.28em]">
            TicketBlitz
          </p>
          <p
            class="text-[10px] font-medium uppercase tracking-[0.22em] text-black/65"
          >
            Main Page 01
          </p>
        </RouterLink>

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

          <AuthSessionControls v-if="isAuthenticated" />
          <UiButton v-else to="/sign-in" variant="primary" class="min-w-[9rem]"
            >Login</UiButton
          >
        </div>
      </div>
    </header>

    <section class="border-b-4 border-black bg-white">
      <div class="mx-auto max-w-[1800px] px-6 py-8 md:px-10 md:py-10">
        <SectionLabel index="09." label="My Tickets" />
        <h1
          class="mt-8 text-[clamp(2.2rem,7vw,5.6rem)] font-black uppercase leading-[0.9] tracking-[-0.04em]"
        >
          Purchased
          <br />
          Tickets
        </h1>
        <p
          class="mt-5 max-w-3xl text-sm uppercase leading-relaxed tracking-[0.04em] md:text-base"
        >
          View your confirmed bookings and keep your ticket details ready for
          event day.
        </p>
      </div>
    </section>

    <section class="border-b-4 border-black bg-[var(--swiss-muted)]">
      <div class="mx-auto max-w-[1800px] px-6 py-10 md:px-10 md:py-14">
        <article class="border-4 border-black bg-white p-6 md:p-8">
          <div
            class="flex flex-col gap-4 border-b-2 border-black pb-5 md:flex-row md:items-center md:justify-between"
          >
            <p
              class="text-[11px] font-black uppercase tracking-[0.2em] text-black/65"
            >
              Confirmed Tickets
            </p>
            <span
              class="inline-flex items-center border-2 border-black bg-[var(--swiss-accent)] px-3 py-1 text-[10px] font-black uppercase tracking-[0.2em]"
            >
              {{ purchasedTickets.length }} Confirmed
            </span>
          </div>

          <UiStateNotice
            v-if="hasLoadError"
            class="mt-6"
            :tone="ticketErrorTone"
            :title="ticketErrorTitle"
            :message="loadError"
          >
            <template #actions>
              <button
                type="button"
                class="inline-flex h-10 items-center justify-center border-2 border-black bg-white px-4 text-[10px] font-black uppercase tracking-[0.18em] text-black transition duration-150 ease-out hover:bg-black hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--swiss-accent)] focus-visible:ring-offset-2"
                @click="refreshTickets"
              >
                Retry
              </button>
              <RouterLink
                v-if="isEndpointMissingError"
                to="/ticket-purchase"
                class="inline-flex h-10 items-center justify-center border-2 border-black bg-black px-4 text-[10px] font-black uppercase tracking-[0.18em] text-white transition duration-150 ease-out hover:bg-white hover:text-black focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--swiss-accent)] focus-visible:ring-offset-2"
              >
                Continue Booking
              </RouterLink>
            </template>
          </UiStateNotice>

          <UiStateNotice
            v-if="hasCancellationFeedback"
            class="mt-6"
            :tone="cancellationNoticeTone"
            :title="cancellationNoticeTitle"
            :message="ticketCancellation.message.value || 'Status updated.'"
          />

          <UiStatusProgressBar
            v-if="
              hasCancellationFeedback || ticketCancellation.isSubmitting.value
            "
            class="mt-3"
            :steps="cancellationProgressState.steps"
            :current-step="cancellationProgressState.currentStep"
            :tone="cancellationProgressState.tone"
            :status-text="cancellationProgressState.statusText"
          />

          <p
            v-if="isLoading"
            class="mt-6 border-2 border-black bg-[var(--swiss-muted)] px-4 py-3 text-xs font-black uppercase tracking-[0.14em]"
          >
            Loading latest tickets...
          </p>

          <div
            v-if="purchasedTickets.length === 0 && !isLoading && !hasLoadError"
            class="mt-6 border-2 border-black bg-[var(--swiss-muted)] p-5"
          >
            <p class="text-xs font-black uppercase tracking-[0.16em]">
              No confirmed tickets yet.
            </p>
            <p
              class="mt-2 text-xs font-bold uppercase tracking-[0.08em] text-black/70"
            >
              Complete a booking flow and your ticket will appear here.
            </p>
            <RouterLink
              to="/ticket-purchase"
              class="mt-4 inline-flex h-10 items-center justify-center border-2 border-black bg-white px-4 text-[10px] font-black uppercase tracking-[0.18em] transition duration-150 ease-out hover:bg-black hover:text-white"
            >
              Start New Booking
            </RouterLink>
          </div>

          <div
            class="mt-6 hidden border-2 border-black bg-[var(--swiss-muted)] px-4 py-3 md:grid md:grid-cols-12 md:gap-4"
          >
            <p
              class="md:col-span-3 text-[10px] font-black uppercase tracking-[0.18em] text-black/60"
            >
              Event
            </p>
            <p
              class="md:col-span-2 text-[10px] font-black uppercase tracking-[0.18em] text-black/60"
            >
              Status
            </p>
            <p
              class="md:col-span-2 text-[10px] font-black uppercase tracking-[0.18em] text-black/60"
            >
              Seat
            </p>
            <p
              class="md:col-span-3 text-[10px] font-black uppercase tracking-[0.18em] text-black/60"
            >
              Ticket ID
            </p>
            <p
              class="md:col-span-1 text-[10px] font-black uppercase tracking-[0.18em] text-black/60"
            >
              Hold ID
            </p>
            <p
              class="md:col-span-1 text-right text-[10px] font-black uppercase tracking-[0.18em] text-black/60"
            >
              Actions
            </p>
          </div>

          <div class="mt-4 space-y-4" v-if="purchasedTickets.length > 0">
            <article
              v-for="ticket in purchasedTickets"
              :key="ticket.holdID"
              class="border-2 border-black bg-white p-4"
            >
              <div class="grid gap-4 md:grid-cols-12 md:items-center">
                <div class="md:col-span-3">
                  <p
                    class="text-[10px] font-black uppercase tracking-[0.18em] text-black/60 md:hidden"
                  >
                    Event
                  </p>
                  <p class="text-sm font-black uppercase tracking-[0.05em]">
                    {{ ticket.eventName }}
                  </p>
                </div>

                <div class="md:col-span-2">
                  <p
                    class="text-[10px] font-black uppercase tracking-[0.18em] text-black/60 md:hidden"
                  >
                    Status
                  </p>
                  <p class="text-xs font-bold uppercase tracking-[0.06em]">
                    {{ ticket.status }}
                  </p>
                </div>

                <div class="md:col-span-2">
                  <p
                    class="text-[10px] font-black uppercase tracking-[0.18em] text-black/60 md:hidden"
                  >
                    Seat
                  </p>
                  <p class="text-xs font-bold uppercase tracking-[0.06em]">
                    {{ ticket.seatNumber || "N/A" }}
                  </p>
                </div>

                <div class="md:col-span-3">
                  <p
                    class="text-[10px] font-black uppercase tracking-[0.18em] text-black/60 md:hidden"
                  >
                    Ticket ID
                  </p>
                  <p class="text-xs font-black uppercase tracking-[0.11em]">
                    {{ ticket.ticketID || "N/A" }}
                  </p>
                </div>

                <div class="md:col-span-1">
                  <p
                    class="text-[10px] font-black uppercase tracking-[0.18em] text-black/60 md:hidden"
                  >
                    Hold ID
                  </p>
                  <p
                    class="truncate text-xs font-black uppercase tracking-[0.11em]"
                  >
                    {{ ticket.holdID }}
                  </p>
                </div>

                <div class="md:col-span-1 md:text-right">
                  <div class="flex flex-wrap justify-end gap-2">
                    <button
                      type="button"
                      class="inline-flex h-10 items-center justify-center border-2 border-black bg-[var(--swiss-accent)] px-3 text-[10px] font-black uppercase tracking-[0.18em] transition duration-150 ease-out hover:bg-black hover:text-white"
                      @click="openPass(ticket)"
                    >
                      View Pass
                    </button>
                    <button
                      type="button"
                      class="inline-flex h-10 items-center justify-center border-2 border-black bg-white px-3 text-[10px] font-black uppercase tracking-[0.18em] transition duration-150 ease-out hover:bg-black hover:text-white disabled:cursor-not-allowed disabled:opacity-60"
                      :disabled="
                        !canCancelTicket(ticket) ||
                        (ticketCancellation.isSubmitting.value &&
                          isCancellingTicket(ticket))
                      "
                      @click="openCancellationModal(ticket)"
                    >
                      {{
                        !canCancelTicket(ticket)
                          ? "Unavailable"
                          : ticketCancellation.isSubmitting.value &&
                              isCancellingTicket(ticket)
                            ? "Cancelling..."
                            : "Cancel"
                      }}
                    </button>
                  </div>
                </div>
              </div>
            </article>
          </div>
        </article>
      </div>
    </section>

    <section
      v-if="isCancellationModalVisible"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/70 px-6"
      @click.self="closeCancellationModal"
    >
      <div class="w-full max-w-lg border-4 border-black bg-white p-5 md:p-6">
        <div
          class="flex items-start justify-between gap-4 border-b-2 border-black pb-4"
        >
          <div>
            <p
              class="text-[10px] font-black uppercase tracking-[0.2em] text-black/60"
            >
              Cancel Ticket
            </p>
            <h3 class="mt-1 text-lg font-black uppercase leading-tight">
              {{ cancellationTargetTicket?.eventName || "TicketBlitz Event" }}
            </h3>
          </div>
          <button
            type="button"
            class="inline-flex h-10 w-10 items-center justify-center border-2 border-black text-base font-black transition duration-150 ease-out hover:bg-black hover:text-white disabled:cursor-not-allowed disabled:opacity-60"
            :disabled="ticketCancellation.isSubmitting.value"
            @click="closeCancellationModal"
          >
            ✕
          </button>
        </div>

        <div
          class="mt-4 space-y-3 border-2 border-black bg-[var(--swiss-muted)] p-4"
        >
          <p class="text-[11px] font-black uppercase tracking-[0.14em]">
            Cancellation policy: 10% is deducted as a fee.
          </p>
          <div
            class="grid grid-cols-2 gap-2 text-[11px] font-black uppercase tracking-[0.08em]"
          >
            <p class="text-black/70">Ticket amount</p>
            <p class="text-right">
              {{ cancellationPreview?.baseLabel || "N/A" }}
            </p>
            <p class="text-black/70">Cancellation fee (10%)</p>
            <p class="text-right">
              {{ cancellationPreview?.feeLabel || "N/A" }}
            </p>
            <p class="text-black/70">Final refund (90%)</p>
            <p class="text-right">
              {{ cancellationPreview?.expectedRefundLabel || "N/A" }}
            </p>
          </div>
        </div>

        <UiStatusProgressBar
          class="mt-4"
          :steps="cancellationModalProgressState.steps"
          :current-step="cancellationModalProgressState.currentStep"
          :tone="cancellationModalProgressState.tone"
          :status-text="cancellationModalProgressState.statusText"
        />

        <p
          v-if="cancellationDialogError"
          class="mt-4 border-2 border-black bg-red-50 px-3 py-2 text-xs font-black uppercase tracking-[0.08em] text-red-700"
        >
          {{ cancellationDialogError }}
        </p>

        <div class="mt-5 flex flex-col gap-2 sm:flex-row sm:justify-end">
          <button
            type="button"
            class="inline-flex h-10 items-center justify-center border-2 border-black bg-white px-4 text-[10px] font-black uppercase tracking-[0.18em] transition duration-150 ease-out hover:bg-black hover:text-white disabled:cursor-not-allowed disabled:opacity-60"
            :disabled="ticketCancellation.isSubmitting.value"
            @click="closeCancellationModal"
          >
            Keep Ticket
          </button>
          <button
            type="button"
            class="inline-flex h-10 items-center justify-center border-2 border-black bg-[var(--swiss-accent)] px-4 text-[10px] font-black uppercase tracking-[0.18em] transition duration-150 ease-out hover:bg-black hover:text-white disabled:cursor-not-allowed disabled:opacity-60"
            :disabled="ticketCancellation.isSubmitting.value"
            @click="confirmCancellation"
          >
            {{
              ticketCancellation.isSubmitting.value
                ? "Cancelling..."
                : "Confirm Cancellation"
            }}
          </button>
        </div>
      </div>
    </section>

    <section
      v-if="selectedTicket"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/70 px-6"
      @click.self="closePass"
    >
      <div class="w-full max-w-xl border-4 border-black bg-white p-4 md:p-5">
        <div
          class="flex items-start justify-between gap-4 border-b-2 border-black pb-4"
        >
          <div>
            <p
              class="text-[10px] font-black uppercase tracking-[0.2em] text-black/60"
            >
              Entry Pass
            </p>
            <h3 class="mt-1 text-xl font-black uppercase leading-tight">
              {{ selectedTicket.eventName }}
            </h3>
          </div>
          <button
            type="button"
            class="inline-flex h-10 w-10 items-center justify-center border-2 border-black text-base font-black transition duration-150 ease-out hover:bg-black hover:text-white"
            @click="closePass"
          >
            ✕
          </button>
        </div>

        <div class="mt-4 grid gap-3 sm:grid-cols-2">
          <div class="border-2 border-black bg-[var(--swiss-muted)] p-3">
            <p
              class="text-[10px] font-black uppercase tracking-[0.2em] text-black/60"
            >
              Ticket Status
            </p>
            <p class="mt-2 text-xs font-black uppercase tracking-[0.08em]">
              {{ selectedTicket.status }}
            </p>
          </div>
          <div class="border-2 border-black bg-[var(--swiss-muted)] p-3">
            <p
              class="text-[10px] font-black uppercase tracking-[0.2em] text-black/60"
            >
              Seat Number
            </p>
            <p class="mt-2 text-xs font-black uppercase tracking-[0.08em]">
              {{ selectedTicket.seatNumber || "N/A" }}
            </p>
          </div>
          <div
            class="border-2 border-black bg-[var(--swiss-muted)] p-3 sm:col-span-2"
          >
            <p
              class="text-[10px] font-black uppercase tracking-[0.2em] text-black/60"
            >
              Ticket ID
            </p>
            <p class="mt-2 text-xs font-black uppercase tracking-[0.12em]">
              {{ selectedTicket.ticketID || "N/A" }}
            </p>
          </div>
          <div
            class="border-2 border-black bg-[var(--swiss-muted)] p-3 sm:col-span-2"
          >
            <p
              class="text-[10px] font-black uppercase tracking-[0.2em] text-black/60"
            >
              Hold ID
            </p>
            <p
              class="mt-2 break-all text-xs font-black uppercase tracking-[0.12em]"
            >
              {{ selectedTicket.holdID }}
            </p>
          </div>
        </div>

        <div class="mt-4 border-2 border-black bg-[var(--swiss-accent)] p-3">
          <div class="border-2 border-black bg-white p-3">
            <div class="flex flex-col items-center">
              <img
                v-if="passQrDataUrl"
                :src="passQrDataUrl"
                alt="Ticket QR code"
                class="h-24 w-24 border-2 border-black bg-white object-contain md:h-28 md:w-28"
              />
              <div
                v-else
                class="swiss-grid-pattern h-24 w-24 border-2 border-black bg-[var(--swiss-muted)] md:h-28 md:w-28"
              />
              <p
                class="mt-3 text-center text-[10px] font-black uppercase tracking-[0.2em] text-black/65"
              >
                {{
                  passQrDataUrl
                    ? "Scan at entry"
                    : passQrError || "QR unavailable"
                }}
              </p>
            </div>
          </div>
        </div>

        <button
          type="button"
          class="mt-4 inline-flex h-10 w-full items-center justify-center border-2 border-black bg-white px-4 text-xs font-black uppercase tracking-[0.2em] transition duration-150 ease-out hover:bg-black hover:text-white"
          @click="closePass"
        >
          Close
        </button>
      </div>
    </section>

    <footer class="bg-black px-6 py-14 text-white md:px-10 md:py-20">
      <div class="mx-auto grid max-w-[1800px] gap-10 lg:grid-cols-12">
        <div class="lg:col-span-7">
          <p
            class="text-xs font-black uppercase tracking-[0.3em] text-[var(--swiss-accent)]"
          >
            05. TicketBlitz International
          </p>
          <h2
            class="mt-5 text-5xl font-black uppercase leading-[0.88] tracking-[-0.04em] md:text-7xl"
          >
            TicketBlitz
          </h2>
          <p
            class="mt-6 max-w-xl text-sm leading-relaxed text-white/80 md:text-base"
          >
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

        <p
          class="border-t-2 border-white/20 pt-6 text-[11px] font-medium uppercase tracking-[0.2em] text-white/70 lg:col-span-12"
        >
          ©2026 TicketBlitz International
        </p>
      </div>
    </footer>
  </main>
</template>
