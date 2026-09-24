export class ApiError extends Error {
  constructor(
    public status: number,
    public detail?: string,
  ) {
    super(detail ?? `Request failed (${status})`);
  }
}

export const UNAUTHORIZED_EVENT = "smartfin:unauthorized";

interface Options {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  signal?: AbortSignal;
}

export async function api<T>(path: string, { method = "GET", body, signal }: Options = {}): Promise<T> {
  const headers: Record<string, string> = { "X-Requested-With": "smartfin" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  let response: Response;
  try {
    response = await fetch(path, {
      method,
      headers,
      credentials: "same-origin",
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
    });
  } catch (err) {
    if ((err as Error).name === "AbortError") throw err;
    throw new ApiError(0, "network");
  }
  if (response.status === 401 && path !== "/api/auth/login") {
    window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
  }
  if (!response.ok) {
    let detail: string | undefined;
    try {
      const data = await response.json();
      detail = typeof data.detail === "string" ? data.detail : undefined;
    } catch {
      // not JSON
    }
    throw new ApiError(response.status, detail);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

/** A Hebrew message for anything that went wrong talking to the server */
export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 0) return "אין חיבור לשרת. בדקו את הרשת ונסו שוב.";
    if (err.status === 409) return "אי אפשר: הפריט בשימוש.";
    if (err.status === 422) return "חלק מהפרטים לא תקינים.";
    if (err.status === 429) return "יותר מדי ניסיונות. נסו שוב בעוד כמה דקות.";
    if (err.status >= 500) return "משהו השתבש בשרת. נסו שוב בעוד רגע.";
  }
  return "משהו השתבש. נסו שוב.";
}
