const DEFAULT_TIMEOUT_MS = 12000;
const DEV_CUSTOMER_API_KEY = "ticketblitz-customer-dev-key";

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || "/api").replace(
  /\/$/,
  "",
);
const customerApiKey = (
  import.meta.env.VITE_CUSTOMER_API_KEY ||
  (import.meta.env.DEV ? DEV_CUSTOMER_API_KEY : "")
).trim();

class ApiClientError extends Error {
  constructor(message, { status = 0, payload = null, code = "" } = {}) {
    super(message);
    this.name = "ApiClientError";
    this.status = status;
    this.payload = payload;
    this.code = code;
  }
}

function createCorrelationId() {
  if (
    typeof crypto !== "undefined" &&
    typeof crypto.randomUUID === "function"
  ) {
    return crypto.randomUUID();
  }

  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

async function parseResponse(response) {
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    try {
      return await response.json();
    } catch {
      return null;
    }
  }

  const text = await response.text();
  return text ? { message: text } : null;
}

function resolveErrorMessage(payload, fallback) {
  if (!payload) return fallback;
  if (typeof payload === "string") return payload;
  if (typeof payload.error === "string" && payload.error.trim())
    return payload.error;
  if (typeof payload.message === "string" && payload.message.trim())
    return payload.message;
  return fallback;
}

function buildHeaders({ authStore, includeUserHeader = true, headers = {} }) {
  const merged = {
    Accept: "application/json",
    "Content-Type": "application/json",
    "X-Correlation-ID": createCorrelationId(),
    ...headers,
  };

  if (customerApiKey) {
    merged["x-customer-api-key"] = customerApiKey;
  }

  const userId = authStore?.state?.user?.id;
  if (includeUserHeader && typeof userId === "string" && userId.trim()) {
    merged["X-User-ID"] = userId.trim();
  }

  return merged;
}

async function request({
  authStore,
  method,
  path,
  body,
  timeoutMs = DEFAULT_TIMEOUT_MS,
  includeUserHeader = true,
  headers,
}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(`${apiBaseUrl}${path}`, {
      method,
      headers: buildHeaders({ authStore, includeUserHeader, headers }),
      body: body == null ? undefined : JSON.stringify(body),
      signal: controller.signal,
    });

    const payload = await parseResponse(response);

    if (!response.ok) {
      throw new ApiClientError(
        resolveErrorMessage(
          payload,
          `Request failed with status ${response.status}`,
        ),
        {
          status: response.status,
          payload,
          code: typeof payload?.code === "string" ? payload.code : "",
        },
      );
    }

    return payload;
  } catch (error) {
    if (error?.name === "AbortError") {
      throw new ApiClientError("Request timed out. Please try again.", {
        status: 408,
      });
    }

    if (error instanceof ApiClientError) {
      throw error;
    }

    throw new ApiClientError(
      "Unable to reach TicketBlitz services. Please try again.",
      { payload: error },
    );
  } finally {
    clearTimeout(timer);
  }
}

function createApiClient(authStore) {
  return {
    get(path, options = {}) {
      return request({ authStore, method: "GET", path, ...options });
    },
    post(path, body, options = {}) {
      return request({ authStore, method: "POST", path, body, ...options });
    },
    put(path, body, options = {}) {
      return request({ authStore, method: "PUT", path, body, ...options });
    },
    patch(path, body, options = {}) {
      return request({ authStore, method: "PATCH", path, body, ...options });
    },
    delete(path, options = {}) {
      return request({ authStore, method: "DELETE", path, ...options });
    },
  };
}

export { ApiClientError, createApiClient };
