import { ref } from "vue";
import { useAuthStore } from "@/stores/authStore";
import { useApiClient } from "@/composables/useApiClient";
import { ApiClientError } from "@/lib/apiClient";
import { getUserBookings, mapBookingLifecycleStatus } from "@/lib/ticketsApi";

const ACTIVE_BOOKING_STATUSES = [
  "SUCCEEDED",
  "REFUND_PENDING",
  "REFUND_FAILED",
];

function fallbackEventName(eventID) {
  if (!eventID) return "TicketBlitz Event";
  return `Event ${String(eventID).slice(0, 8).toUpperCase()}`;
}

function mapLifecycleLabel(status) {
  if (status === "REFUND_COMPLETED") return "Refund Completed";
  if (status === "CANCELLATION_IN_PROGRESS") return "Cancellation In Progress";
  return "Confirmed";
}

async function fetchEventNameLookup(api, bookings) {
  const eventIDs = [
    ...new Set(
      bookings
        .map((booking) => String(booking?.eventID || "").trim())
        .filter(Boolean),
    ),
  ];
  if (eventIDs.length === 0) return new Map();

  const results = await Promise.allSettled(
    eventIDs.map(async (eventID) => {
      const payload = await api.get(`/event/${encodeURIComponent(eventID)}`, {
        includeUserHeader: false,
      });

      return {
        eventID,
        eventName: String(payload?.name || "").trim(),
      };
    }),
  );

  const lookup = new Map();
  for (const result of results) {
    if (result.status !== "fulfilled") continue;

    const eventID = String(result.value?.eventID || "").trim();
    const eventName = String(result.value?.eventName || "").trim();
    if (!eventID || !eventName) continue;

    lookup.set(eventID, eventName);
  }

  return lookup;
}

async function fetchBookingStatusLookup(api, bookings) {
  const holdIDs = [
    ...new Set(
      bookings
        .map((booking) => String(booking?.holdID || "").trim())
        .filter(Boolean),
    ),
  ];
  if (holdIDs.length === 0) return new Map();

  const results = await Promise.allSettled(
    holdIDs.map(async (holdID) => {
      const payload = await api.get(
        `/booking-status/${encodeURIComponent(holdID)}`,
        {
          includeUserHeader: false,
        },
      );

      return {
        holdID,
        seatNumber: String(payload?.seatNumber || "").trim(),
        ticketID: String(payload?.ticketID || "").trim(),
      };
    }),
  );

  const lookup = new Map();
  for (const result of results) {
    if (result.status !== "fulfilled") continue;

    const holdID = String(result.value?.holdID || "").trim();
    if (!holdID) continue;

    lookup.set(holdID, {
      seatNumber: result.value?.seatNumber || "",
      ticketID: result.value?.ticketID || "",
    });
  }

  return lookup;
}

function normalizeBookingToTicketCard(
  booking,
  eventNameLookup,
  bookingStatusLookup,
) {
  const lifecycleStatus = mapBookingLifecycleStatus(booking);
  const eventID = String(booking?.eventID || "").trim();
  const holdID = String(booking?.holdID || booking?.bookingID || "").trim();
  const bookingStatus = bookingStatusLookup.get(holdID) || null;
  const resolvedTicketID =
    bookingStatus?.ticketID || booking?.ticketID || booking?.bookingID || null;
  const resolvedSeatNumber =
    bookingStatus?.seatNumber || booking?.seatNumber || null;

  return {
    bookingID: booking?.bookingID || null,
    holdID: holdID || null,
    ticketID: resolvedTicketID,
    seatNumber: resolvedSeatNumber,
    eventID: eventID || null,
    eventName: eventNameLookup.get(eventID) || fallbackEventName(eventID),
    status: mapLifecycleLabel(lifecycleStatus),
    lifecycleStatus,
    paymentStatus: booking?.paymentStatus || null,
    refundStatus: booking?.refundStatus || null,
    refundAmount: booking?.refundAmount || null,
    amount: booking?.amount || null,
    currency: booking?.currency || null,
    createdAt: booking?.createdAt || null,
    updatedAt:
      booking?.updatedAt || booking?.createdAt || new Date().toISOString(),
  };
}

function buildErrorState(error) {
  const hasApiClientShape =
    error instanceof ApiClientError ||
    (error && typeof error === "object" && typeof error.status === "number");

  if (!hasApiClientShape) {
    return {
      kind: "unknown",
      status: 0,
      code: "",
      message: error?.message || "Unable to load user bookings.",
    };
  }

  if (error.status === 404) {
    return {
      kind: "endpoint-missing",
      status: 404,
      code: error.code || "ENDPOINT_NOT_FOUND",
      message: "Please buy a ticket to see your confirmed tickets",
    };
  }

  if (error.status === 408 || error.status === 0) {
    return {
      kind: "network",
      status: error.status,
      code: error.code || "",
      message:
        "Unable to reach TicketBlitz services. Check connectivity and try again.",
    };
  }

  if (error.status >= 500) {
    return {
      kind: "server",
      status: error.status,
      code: error.code || "",
      message:
        "Ticket services are temporarily unavailable. Please try again shortly.",
    };
  }

  return {
    kind: "request",
    status: error.status,
    code: error.code || "",
    message: error.message || "Unable to load user bookings.",
  };
}

export function useUserBookings() {
  const authStore = useAuthStore();
  const api = useApiClient();

  const tickets = ref([]);
  const loading = ref(false);
  const errorMessage = ref("");
  const requestState = ref({
    kind: "idle",
    status: 0,
    code: "",
    message: "",
  });

  async function refreshTickets() {
    const userID = String(authStore.state.user?.id || "").trim();
    errorMessage.value = "";

    if (!userID) {
      tickets.value = [];
      requestState.value = { kind: "idle", status: 0, code: "", message: "" };
      return tickets.value;
    }

    loading.value = true;
    requestState.value = { kind: "loading", status: 0, code: "", message: "" };

    try {
      const bookings = await getUserBookings(api, {
        userID,
        statuses: ACTIVE_BOOKING_STATUSES,
      });
      const [eventNameLookup, bookingStatusLookup] = await Promise.all([
        fetchEventNameLookup(api, bookings),
        fetchBookingStatusLookup(api, bookings),
      ]);

      tickets.value = bookings
        .map((booking) =>
          normalizeBookingToTicketCard(
            booking,
            eventNameLookup,
            bookingStatusLookup,
          ),
        )
        .sort(
          (left, right) =>
            new Date(right.updatedAt || 0).getTime() -
            new Date(left.updatedAt || 0).getTime(),
        );

      requestState.value = {
        kind: "success",
        status: 200,
        code: "",
        message: "",
      };
      return tickets.value;
    } catch (error) {
      const normalized = buildErrorState(error);
      tickets.value = [];
      errorMessage.value = normalized.message;
      requestState.value = normalized;
      throw error;
    } finally {
      loading.value = false;
    }
  }

  return {
    tickets,
    loading,
    errorMessage,
    requestState,
    refreshTickets,
  };
}
