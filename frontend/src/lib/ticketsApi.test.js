import { describe, expect, it, vi } from "vitest";
import {
  DEFAULT_USER_BOOKING_STATUSES,
  buildUserBookingsPath,
  getUserBookings,
  mapBookingLifecycleStatus,
} from "./ticketsApi";

describe("ticketsApi.buildUserBookingsPath", () => {
  it("builds path with default statuses", () => {
    const path = buildUserBookingsPath("10000000-0000-0000-0000-000000000001");

    expect(path).toContain(
      "/payments/user/10000000-0000-0000-0000-000000000001/bookings",
    );
    expect(path).toContain(
      encodeURIComponent(DEFAULT_USER_BOOKING_STATUSES.join(",")),
    );
  });

  it("normalizes custom status values", () => {
    const path = buildUserBookingsPath("10000000-0000-0000-0000-000000000001", [
      "succeeded",
      "refund_pending",
    ]);
    expect(path).toContain(encodeURIComponent("SUCCEEDED,REFUND_PENDING"));
  });
});

describe("ticketsApi.getUserBookings", () => {
  it("rejects when userID is missing", async () => {
    const api = { get: vi.fn() };
    await expect(getUserBookings(api, { userID: "" })).rejects.toThrow(
      "userID is required",
    );
  });

  it("returns normalized bookings array", async () => {
    const api = {
      get: vi.fn().mockResolvedValue({
        bookings: [
          {
            bookingID: "bk-001",
            holdID: "hold-001",
            eventID: "evt-001",
            paymentStatus: "SUCCEEDED",
            updatedAt: "2026-04-08T00:00:00Z",
          },
        ],
      }),
    };

    const result = await getUserBookings(api, {
      userID: "10000000-0000-0000-0000-000000000001",
    });

    expect(api.get).toHaveBeenCalledTimes(1);
    expect(result[0]).toMatchObject({
      bookingID: "bk-001",
      holdID: "hold-001",
      eventID: "evt-001",
      paymentStatus: "SUCCEEDED",
    });
  });
});

describe("ticketsApi.mapBookingLifecycleStatus", () => {
  it("maps refund states to lifecycle buckets", () => {
    expect(mapBookingLifecycleStatus({ paymentStatus: "REFUND_PENDING" })).toBe(
      "CANCELLATION_IN_PROGRESS",
    );
    expect(
      mapBookingLifecycleStatus({ paymentStatus: "REFUND_SUCCEEDED" }),
    ).toBe("REFUND_COMPLETED");
    expect(mapBookingLifecycleStatus({ paymentStatus: "SUCCEEDED" })).toBe(
      "CONFIRMED",
    );
  });
});
