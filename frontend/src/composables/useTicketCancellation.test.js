import { afterEach, describe, expect, it, vi } from "vitest";

async function loadComposable({ cancelResponse, statusResponse } = {}) {
  vi.resetModules();

  const requestTicketCancellation = vi.fn().mockResolvedValue(
    cancelResponse || {
      ok: true,
      status: "REFUND_COMPLETED",
      terminal: true,
      reason: "",
      bookingID: "bk-001",
    },
  );
  const getTicketCancellationStatus = vi.fn().mockResolvedValue(
    statusResponse || {
      ok: true,
      status: "REALLOCATION_CONFIRMED",
      terminal: true,
      reason: "",
      bookingID: "bk-001",
    },
  );

  vi.doMock("@/composables/useApiClient", () => ({
    useApiClient: () => ({ get: vi.fn(), post: vi.fn() }),
  }));

  vi.doMock("@/lib/cancellationApi", () => ({
    requestTicketCancellation,
    getTicketCancellationStatus,
  }));

  const module = await import("./useTicketCancellation");
  return { ...module, requestTicketCancellation, getTicketCancellationStatus };
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.resetModules();
});

describe("useTicketCancellation", () => {
  it("sets terminal status for non-polling completion", async () => {
    const {
      useTicketCancellation,
      requestTicketCancellation,
      getTicketCancellationStatus,
    } = await loadComposable();
    const composable = useTicketCancellation();

    const result = await composable.cancelTicket({
      bookingID: "bk-001",
      userID: "user-001",
    });

    expect(requestTicketCancellation).toHaveBeenCalledTimes(1);
    expect(getTicketCancellationStatus).toHaveBeenCalledTimes(0);
    expect(result.status).toBe("REFUND_COMPLETED");
    expect(composable.status.value).toBe("REFUND_COMPLETED");
  });

  it("starts polling when initial status is REALLOCATION_PENDING", async () => {
    const { useTicketCancellation, getTicketCancellationStatus } =
      await loadComposable({
        cancelResponse: {
          ok: true,
          status: "REALLOCATION_PENDING",
          terminal: false,
          bookingID: "bk-001",
          newHoldID: "hold-002",
        },
        statusResponse: {
          ok: true,
          status: "REALLOCATION_CONFIRMED",
          terminal: true,
          bookingID: "bk-001",
        },
      });

    const composable = useTicketCancellation();
    await composable.cancelTicket({ bookingID: "bk-001", userID: "user-001" });

    expect(getTicketCancellationStatus).toHaveBeenCalledTimes(1);
    expect(composable.status.value).toBe("REALLOCATION_CONFIRMED");
  });

  it("resolves ALREADY_REFUNDED using status endpoint when refund amount is missing", async () => {
    const { useTicketCancellation, getTicketCancellationStatus } =
      await loadComposable({
        cancelResponse: {
          ok: true,
          status: "ALREADY_REFUNDED",
          terminal: true,
          bookingID: "bk-001",
        },
        statusResponse: {
          ok: true,
          status: "REFUND_COMPLETED",
          terminal: true,
          bookingID: "bk-001",
          refundAmount: "349.20",
        },
      });

    const composable = useTicketCancellation();
    const result = await composable.cancelTicket({
      bookingID: "bk-001",
      userID: "user-001",
    });

    expect(getTicketCancellationStatus).toHaveBeenCalledTimes(1);
    expect(result.status).toBe("REFUND_COMPLETED");
    expect(result.refundAmount).toBe("349.20");
    expect(composable.status.value).toBe("REFUND_COMPLETED");
  });
});
