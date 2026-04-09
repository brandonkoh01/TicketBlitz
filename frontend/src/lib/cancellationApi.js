import { ApiClientError } from "@/lib/apiClient";

function parseStatus(payload, httpStatus) {
  const explicit = String(payload?.status || "")
    .trim()
    .toUpperCase();
  if (explicit) return explicit;

  if (httpStatus === 409) return "DENIED";
  if (httpStatus === 502) return "CANCELLATION_IN_PROGRESS";
  if (httpStatus === 202) return "REALLOCATION_PENDING";
  if (httpStatus === 200) return "REFUND_COMPLETED";
  return "UNKNOWN";
}

function parseReason(payload, fallback = "") {
  if (typeof payload?.reason === "string" && payload.reason.trim())
    return payload.reason.trim();
  if (typeof payload?.error === "string" && payload.error.trim())
    return payload.error.trim();
  if (typeof payload?.message === "string" && payload.message.trim())
    return payload.message.trim();
  return fallback;
}

function normalizeResult({ payload, httpStatus, ok, fallbackReason = "" }) {
  return {
    ok,
    httpStatus,
    status: parseStatus(payload, httpStatus),
    reason: parseReason(payload, fallbackReason),
    terminal: Boolean(payload?.terminal),
    bookingID: payload?.bookingID || null,
    newHoldID: payload?.newHoldID || null,
    refundAmount: payload?.refundAmount || null,
    payload,
  };
}

async function requestTicketCancellation(
  api,
  { bookingID, userID, reason, simulateRefundFailure } = {},
) {
  const parsedBookingID = String(bookingID || "").trim();
  const parsedUserID = String(userID || "").trim();

  if (!parsedBookingID)
    throw new Error("bookingID is required to request cancellation.");
  if (!parsedUserID)
    throw new Error("userID is required to request cancellation.");

  try {
    const payload = await api.post(
      `/bookings/cancel/${encodeURIComponent(parsedBookingID)}`,
      {
        bookingID: parsedBookingID,
        userID: parsedUserID,
        ...(reason ? { reason: String(reason) } : {}),
        ...(simulateRefundFailure ? { simulateRefundFailure: true } : {}),
      },
      { includeUserHeader: false },
    );

    const inferredStatusCode =
      String(payload?.status || "").toUpperCase() === "REALLOCATION_PENDING"
        ? 202
        : 200;
    return normalizeResult({
      payload,
      httpStatus: inferredStatusCode,
      ok: true,
    });
  } catch (error) {
    if (error instanceof ApiClientError) {
      return normalizeResult({
        payload: error.payload,
        httpStatus: Number(error.status || 0),
        ok: false,
        fallbackReason: error.message || "Cancellation request failed.",
      });
    }

    throw error;
  }
}

async function getTicketCancellationStatus(
  api,
  { bookingID, userID, newHoldID } = {},
) {
  const parsedBookingID = String(bookingID || "").trim();
  const parsedUserID = String(userID || "").trim();

  if (!parsedBookingID)
    throw new Error("bookingID is required to poll cancellation status.");
  if (!parsedUserID)
    throw new Error("userID is required to poll cancellation status.");

  const params = new URLSearchParams({ userID: parsedUserID });
  if (newHoldID) params.set("newHoldID", String(newHoldID).trim());

  try {
    const payload = await api.get(
      `/bookings/cancel/status/${encodeURIComponent(parsedBookingID)}?${params.toString()}`,
      { includeUserHeader: false },
    );

    return normalizeResult({
      payload,
      httpStatus: 200,
      ok: true,
    });
  } catch (error) {
    if (error instanceof ApiClientError) {
      return normalizeResult({
        payload: error.payload,
        httpStatus: Number(error.status || 0),
        ok: false,
        fallbackReason: error.message || "Unable to poll cancellation status.",
      });
    }

    throw error;
  }
}

export { getTicketCancellationStatus, requestTicketCancellation };
