import { ScanResponse } from "@/types/scan";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function createScan(repoUrl: string): Promise<ScanResponse> {
  const res = await fetch(`${API_BASE}/api/v1/scans/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ repo_url: repoUrl }),
  });

  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Failed to create scan (${res.status}): ${body}`);
  }

  return res.json() as Promise<ScanResponse>;
}

export async function getScan(id: string): Promise<ScanResponse> {
  const res = await fetch(`${API_BASE}/api/v1/scans/${id}`);

  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Failed to fetch scan (${res.status}): ${body}`);
  }

  return res.json() as Promise<ScanResponse>;
}

export async function listScans(limit: number = 20): Promise<ScanResponse[]> {
  const res = await fetch(`${API_BASE}/api/v1/scans/?limit=${limit}`);

  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Failed to list scans (${res.status}): ${body}`);
  }

  return res.json() as Promise<ScanResponse[]>;
}
