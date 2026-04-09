import { getCurrentInstance, onUnmounted, ref } from "vue";
import { useApiClient } from "@/composables/useApiClient";
import {
  getTicketCancellationStatus,
  requestTicketCancellation,
} from "@/lib/cancellationApi";

const POLL_INTERVAL_MS = 4000;
const MAX_POLL_ATTEMPTS = 30;

function hasMeaningfulRefundAmount(value) {
  if (value == null) return false;
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0;
}

function isTerminalStatus(status) {
  return [
    "DENIED",
    "ALREADY_REFUNDED",
    "REFUND_COMPLETED",
    "REALLOCATION_CONFIRMED",
  ].includes(String(status || "").toUpperCase());
}

export function useTicketCancellation() {
  const api = useApiClient();

  const status = ref("IDLE");
  const message = ref("");
  const latestResponse = ref(null);
  const isSubmitting = ref(false);
  const isPolling = ref(false);

  let pollTimer = null;
  let pollAttempts = 0;

  function stopPolling() {
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
    pollAttempts = 0;
    isPolling.value = false;
  }

  async function pollCancellationStatus({ bookingID, userID, newHoldID }) {
    const result = await getTicketCancellationStatus(api, {
      bookingID,
      userID,
      newHoldID,
    });

    latestResponse.value = result;
    status.value = result.status || "UNKNOWN";
    message.value = result.reason || "";

    const terminal =
      Boolean(result.terminal) || isTerminalStatus(result.status);
    if (terminal) {
      stopPolling();
    }

    return result;
  }

  async function beginStatusPolling({ bookingID, userID, newHoldID }) {
    stopPolling();
    isPolling.value = true;

    await pollCancellationStatus({ bookingID, userID, newHoldID });
    if (!isPolling.value) {
      return latestResponse.value;
    }

    pollTimer = setInterval(async () => {
      pollAttempts += 1;
      await pollCancellationStatus({ bookingID, userID, newHoldID });

      if (pollAttempts >= MAX_POLL_ATTEMPTS) {
        message.value =
          message.value ||
          "Cancellation status polling timed out. Please refresh.";
        stopPolling();
      }
    }, POLL_INTERVAL_MS);

    return latestResponse.value;
  }

  async function cancelTicket({
    bookingID,
    userID,
    reason,
    newHoldID,
    simulateRefundFailure,
  } = {}) {
    isSubmitting.value = true;
    message.value = "";

    try {
      const result = await requestTicketCancellation(api, {
        bookingID,
        userID,
        reason,
        simulateRefundFailure,
      });

      latestResponse.value = result;
      status.value = result.status || "UNKNOWN";
      message.value = result.reason || "";

      if (
        String(result.status || "").toUpperCase() === "ALREADY_REFUNDED" &&
        !hasMeaningfulRefundAmount(result.refundAmount)
      ) {
        const resolved = await getTicketCancellationStatus(api, {
          bookingID,
          userID,
          newHoldID: result.newHoldID || newHoldID || null,
        });

        latestResponse.value = {
          ...result,
          ...resolved,
          refundAmount: resolved.refundAmount || result.refundAmount || null,
        };
        status.value = latestResponse.value.status || status.value;
        message.value = latestResponse.value.reason || message.value;
        return latestResponse.value;
      }

      if (
        String(result.status || "").toUpperCase() === "REALLOCATION_PENDING"
      ) {
        await beginStatusPolling({
          bookingID,
          userID,
          newHoldID: result.newHoldID || newHoldID || null,
        });
      }

      return result;
    } finally {
      isSubmitting.value = false;
    }
  }

  if (getCurrentInstance()) {
    onUnmounted(() => {
      stopPolling();
    });
  }

  return {
    status,
    message,
    latestResponse,
    isSubmitting,
    isPolling,
    cancelTicket,
    pollCancellationStatus,
    stopPolling,
  };
}
