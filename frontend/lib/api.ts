type ApiPayload = Record<string, unknown>;

export class ApiError extends Error {
  status: number;
  data: ApiPayload;

  constructor(
    status: number,
    data: ApiPayload,
  ) {
    const detail = data.detail;
    let message = "요청을 처리하지 못했습니다.";

    if (typeof detail === "string") {
      message = detail;
    } else if (
      detail &&
      typeof detail === "object" &&
      "message" in detail &&
      typeof detail.message === "string"
    ) {
      message = detail.message;

      if (
        "retry_after" in detail &&
        typeof detail.retry_after === "number"
      ) {
        message += ` ${detail.retry_after}초 후 다시 시도하세요.`;
      } else if (
        "remaining_attempts" in detail &&
        typeof detail.remaining_attempts === "number"
      ) {
        message += ` 남은 시도 횟수: ${detail.remaining_attempts}회`;
      }
    } else if (
      typeof data.message === "string"
    ) {
      message = data.message;
    }

    super(message);
    this.name = "ApiError";
    this.status = status;
    this.data = data;
  }
}

async function apiRequest<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch(path, {
    ...options,
    credentials: "include",
    cache: "no-store",
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
  });

  let data: ApiPayload = {};

  try {
    data = await response.json();
  } catch {
    data = {};
  }

  if (!response.ok) {
    throw new ApiError(
      response.status,
      data,
    );
  }

  return data as T;
}

export function getAuthenticationStatus() {
  return apiRequest<{
    authenticated: boolean;
  }>("/api/auth/status");
}

export function loginWithPassword(
  password: string,
) {
  return apiRequest<{
    authenticated: boolean;
    message: string;
  }>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ password }),
  });
}

export function logoutSession() {
  return apiRequest<{
    authenticated: boolean;
    message: string;
  }>("/api/auth/logout", {
    method: "POST",
  });
}
