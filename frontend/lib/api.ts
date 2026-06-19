// ---------------------------------------------------------------------------
// BreakMyApp – API client (native fetch, no axios)
// ---------------------------------------------------------------------------

import { ScanResponse } from "@/types/scan";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/**
 * Create a new scan by submitting a repository URL.
 * POST /api/v1/scans/
 */
export async function createScan(repoUrl: string): Promise<ScanResponse> {
  const res = await fetch(`${API_BASE}/api/v1/scans/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ repo_url: repoUrl }),
  });

  if (!res.ok) {
    const body = await res.text();
    throw new Error(
      `Failed to create scan (${res.status}): ${body}`
    );
  }

  return res.json() as Promise<ScanResponse>;
}

/**
 * Retrieve an existing scan by its ID.
 * GET /api/v1/scans/{id}
 */
export async function getScan(id: string): Promise<ScanResponse> {
  const res = await fetch(`${API_BASE}/api/v1/scans/${id}`);

  if (!res.ok) {
    const body = await res.text();
    throw new Error(
      `Failed to fetch scan (${res.status}): ${body}`
    );
  }

  return res.json() as Promise<ScanResponse>;
}
