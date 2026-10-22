export class ApiError extends Error {
  constructor(message: string, public status: number) {
    super(message);
  }
}

export async function apiRequest<T>(path: string, token: string | undefined, options: RequestInit = {}): Promise<T> {
  if (!token) throw new ApiError("Your session expired. Please sign in again.", 401);
  const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}${path}`, {
    ...options,
    headers: { ...options.headers, Authorization: `Bearer ${token}` },
  });
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError(typeof data?.detail === "string" ? data.detail : `Request failed (${response.status}). Please retry.`, response.status);
  }
  return data as T;
}

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Unable to reach the service. Please retry.";
}
