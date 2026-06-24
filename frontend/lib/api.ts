import { ScanResponse, UserResponse } from "@/types/scan";
import { getAuthToken } from "@/lib/auth";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function getAuthHeaders(): Promise<HeadersInit> {
  const token = await getAuthToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  return headers;
}

export async function createScan(repoUrl: string): Promise<ScanResponse> {
  const res = await fetch(`${API_BASE}/api/v1/scans/`, {
    method: "POST",
    headers: await getAuthHeaders(),
    body: JSON.stringify({ repo_url: repoUrl }),
  });

  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Failed to create scan (${res.status}): ${body}`);
  }

  return res.json() as Promise<ScanResponse>;
}

export async function getScan(id: string): Promise<ScanResponse> {
  const res = await fetch(`${API_BASE}/api/v1/scans/${id}`, {
    headers: await getAuthHeaders(),
  });

  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Failed to fetch scan (${res.status}): ${body}`);
  }

  return res.json() as Promise<ScanResponse>;
}

export async function listScans(limit: number = 20): Promise<ScanResponse[]> {
  const res = await fetch(`${API_BASE}/api/v1/scans/?limit=${limit}`, {
    headers: await getAuthHeaders(),
  });

  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Failed to list scans (${res.status}): ${body}`);
  }

  return res.json() as Promise<ScanResponse[]>;
}

export async function getCurrentUserInfo(): Promise<UserResponse> {
  const res = await fetch(`${API_BASE}/api/v1/auth/me`, {
    headers: await getAuthHeaders(),
  });

  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Failed to get user info (${res.status}): ${body}`);
  }

  return res.json() as Promise<UserResponse>;
}
