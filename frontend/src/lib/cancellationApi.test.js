import { describe, expect, it, vi } from "vitest";
import { ApiClientError } from "@/lib/apiClient";
import {
  getTicketCancellationStatus,
  requestTicketCancellation,
} from "./cancellationApi";

describe("cancellationApi.requestTicketCancellation", () => {
  it("normalizes successful 202 reallocation response", async () => {
    const api = {
      post: vi.fn().mockResolvedValue({
        status: "REALLOCATION_PENDING",
        bookingID: "bk-001",
        newHoldID: "hold-002",
      }),
    };

    const result = await requestTicketCancellation(api, {
      bookingID: "bk-001",
      userID: "user-001",
    });

    expect(result.ok).toBe(true);
    expect(result.status).toBe("REALLOCATION_PENDING");
    expect(result.newHoldID).toBe("hold-002");
  });

  it("normalizes denied 409 response from ApiClientError", async () => {
    const api = {
      post: vi.fn().mockRejectedValue(
        new ApiClientError("Denied", {
          status: 409,
          payload: { status: "DENIED", reason: "Not eligible under policy" },
        }),
      ),
    };

    const result = await requestTicketCancellation(api, {
      bookingID: "bk-001",
      userID: "user-001",
    });

    expect(result.ok).toBe(false);
    expect(result.status).toBe("DENIED");
    expect(result.reason).toContain("Not eligible");
  });
});

describe("cancellationApi.getTicketCancellationStatus", () => {
  it("returns normalized polling payload", async () => {
    const api = {
      get: vi.fn().mockResolvedValue({
        status: "REALLOCATION_CONFIRMED",
        terminal: true,
        bookingID: "bk-001",
      }),
    };

    const result = await getTicketCancellationStatus(api, {
      bookingID: "bk-001",
      userID: "user-001",
      newHoldID: "hold-002",
    });

    expect(result.ok).toBe(true);
    expect(result.status).toBe("REALLOCATION_CONFIRMED");
    expect(result.terminal).toBe(true);
  });
});
