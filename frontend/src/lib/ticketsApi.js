const DEFAULT_USER_BOOKING_STATUSES = [
  "SUCCEEDED",
  "REFUND_PENDING",
  "REFUND_SUCCEEDED",
  "REFUND_FAILED",
];

function normalizeStatuses(statuses) {
  if (Array.isArray(statuses)) {
    return statuses.map((value) => String(value || "").trim()).filter(Boolean);
  }

  if (typeof statuses === "string" && statuses.trim()) {
    return statuses
      .split(",")
      .map((value) => value.trim())
      .filter(Boolean);
  }

  return [...DEFAULT_USER_BOOKING_STATUSES];
}

function buildUserBookingsPath(userID, statuses) {
  const normalizedStatuses = normalizeStatuses(statuses);
  const statusQuery = normalizedStatuses
    .map((value) => value.toUpperCase())
    .join(",");
  const encodedUserID = encodeURIComponent(String(userID || "").trim());
  const encodedStatus = encodeURIComponent(statusQuery);
  return `/payments/user/${encodedUserID}/bookings?status=${encodedStatus}`;
}

function normalizeBooking(rawBooking) {
  return {
    bookingID: rawBooking?.bookingID || rawBooking?.transactionID || null,
    transactionID: rawBooking?.transactionID || rawBooking?.bookingID || null,
    holdID: rawBooking?.holdID || null,
    userID: rawBooking?.userID || null,
    eventID: rawBooking?.eventID || null,
    amount: rawBooking?.amount || null,
    currency: rawBooking?.currency || null,
    paymentStatus: rawBooking?.paymentStatus || null,
    refundStatus: rawBooking?.refundStatus || null,
    refundAmount: rawBooking?.refundAmount || null,
    createdAt: rawBooking?.createdAt || null,
    updatedAt: rawBooking?.updatedAt || rawBooking?.createdAt || null,
  };
}

function mapBookingLifecycleStatus(booking) {
  const paymentStatus = String(booking?.paymentStatus || "").toUpperCase();
  if (paymentStatus === "REFUND_PENDING") return "CANCELLATION_IN_PROGRESS";
  if (paymentStatus === "REFUND_FAILED") return "CANCELLATION_IN_PROGRESS";
  if (paymentStatus === "REFUND_SUCCEEDED") return "REFUND_COMPLETED";
  return "CONFIRMED";
}

async function getUserBookings(api, { userID, statuses } = {}) {
  const parsedUserID = String(userID || "").trim();
  if (!parsedUserID) {
    throw new Error("userID is required to load user bookings.");
  }

  if (!api || typeof api.get !== "function") {
    throw new Error("A valid API client is required.");
  }

  const path = buildUserBookingsPath(parsedUserID, statuses);
  const payload = await api.get(path, { includeUserHeader: false });
  const bookings = Array.isArray(payload?.bookings) ? payload.bookings : [];

  return bookings.map(normalizeBooking);
}

export {
  DEFAULT_USER_BOOKING_STATUSES,
  buildUserBookingsPath,
  getUserBookings,
  mapBookingLifecycleStatus,
};
