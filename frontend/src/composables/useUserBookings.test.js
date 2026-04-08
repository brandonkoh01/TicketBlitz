import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiClientError } from "@/lib/apiClient";

async function loadComposable({
  userID = "10000000-0000-0000-0000-000000000001",
  bookingsPayload,
  eventPayloadById,
  throwError,
} = {}) {
  vi.resetModules();

  const get = vi.fn(async (path) => {
    if (throwError) throw throwError;

    if (path.startsWith("/payments/user/")) {
      return bookingsPayload || { bookings: [] };
    }

    if (path.startsWith("/event/")) {
      const eventID = decodeURIComponent(path.replace("/event/", ""));
      if (eventPayloadById?.[eventID]) {
        return eventPayloadById[eventID];
      }
      return { name: "" };
    }

    return {};
  });

  vi.doMock("@/stores/authStore", () => ({
    useAuthStore: () => ({
      state: {
        user: userID ? { id: userID } : null,
      },
    }),
  }));

  vi.doMock("@/composables/useApiClient", () => ({
    useApiClient: () => ({ get }),
  }));

  const module = await import("./useUserBookings");
  return { ...module, get };
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.resetModules();
});

describe("useUserBookings", () => {
  it("returns idle state when no user is authenticated", async () => {
    const { useUserBookings } = await loadComposable({ userID: "" });
    const composable = useUserBookings();

    const result = await composable.refreshTickets();
    expect(result).toEqual([]);
    expect(composable.requestState.value.kind).toBe("idle");
  });

  it("loads and enriches bookings with event names", async () => {
    const { useUserBookings, get } = await loadComposable({
      bookingsPayload: {
        bookings: [
          {
            bookingID: "bk-001",
            holdID: "hold-001",
            eventID: "evt-001",
            paymentStatus: "SUCCEEDED",
            updatedAt: "2026-04-08T01:00:00Z",
          },
        ],
      },
      eventPayloadById: {
        "evt-001": { name: "Coldplay Live" },
      },
    });

    const composable = useUserBookings();
    const result = await composable.refreshTickets();

    expect(result).toHaveLength(1);
    expect(result[0].eventName).toBe("Coldplay Live");
    expect(result[0].status).toBe("Confirmed");
    expect(get).toHaveBeenCalledWith(
      expect.stringContaining(
        "status=SUCCEEDED%2CREFUND_PENDING%2CREFUND_FAILED",
      ),
      expect.any(Object),
    );
    expect(composable.requestState.value.kind).toBe("success");
  });

  it("maps endpoint 404 to endpoint-missing state", async () => {
    const { useUserBookings } = await loadComposable({
      throwError: new ApiClientError("Not found", { status: 404 }),
    });

    const composable = useUserBookings();
    await expect(composable.refreshTickets()).rejects.toBeTruthy();
    expect(composable.requestState.value.kind).toBe("endpoint-missing");
    expect(composable.errorMessage.value).toContain("Please buy a ticket");
  });
});
