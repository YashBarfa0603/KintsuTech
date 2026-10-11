/**
 * API client to communicate with the KintsuTech FastAPI backend.
 * Provides resilient fallbacks if the local backend server is not running.
 */

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function checkBackendHealth(): Promise<{ status: string; detail?: string }> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/v1/health`, {
      method: "GET",
      headers: { "Content-Type": "application/json" },
      signal: AbortSignal.timeout(3000),
    });
    if (res.ok) {
      return await res.json();
    }
    return { status: "error", detail: `HTTP ${res.status}` };
  } catch (err: unknown) {
    return { status: "offline", detail: err instanceof Error ? err.message : "Backend unreachable" };
  }
}

export async function checkAuthHealth(): Promise<Record<string, unknown> | null> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/v1/auth/health`, {
      method: "GET",
      headers: { "Content-Type": "application/json" },
      signal: AbortSignal.timeout(3000),
    });
    if (res.ok) {
      return await res.json();
    }
    return null;
  } catch {
    return null;
  }
}

export async function verifyTokenWithBackend(token: string): Promise<Record<string, unknown> | null> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/v1/auth/verify`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      signal: AbortSignal.timeout(4000),
    });
    if (res.ok) {
      return await res.json();
    }
    return null;
  } catch {
    return null;
  }
}

export async function fetchBackendServices(): Promise<Record<string, unknown>[]> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/v1/services`, {
      signal: AbortSignal.timeout(3000),
    });
    if (res.ok) {
      const data = await res.json();
      return Array.isArray(data) ? data : data.services || [];
    }
    return [];
  } catch {
    return [];
  }
}

export async function fetchBackendIncidents(): Promise<Record<string, unknown>[]> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/v1/incidents`, {
      signal: AbortSignal.timeout(3000),
    });
    if (res.ok) {
      const data = await res.json();
      return Array.isArray(data) ? data : data.incidents || [];
    }
    return [];
  } catch {
    return [];
  }
}
