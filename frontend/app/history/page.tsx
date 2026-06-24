"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { listScans } from "@/lib/api";
import { ScanResponse } from "@/types/scan";
import AuthGuard from "@/components/AuthGuard";

function HistoryContent() {
  const [scans, setScans] = useState<ScanResponse[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchHistory = async () => {
      try {
        const data = await listScans(20);
        setScans(data);
      } catch (err: unknown) {
        const msg =
          err instanceof Error ? err.message : "Failed to load scan history.";
        setError(msg);
      } finally {
        setIsLoading(false);
      }
    };

    fetchHistory();
  }, []);

  const getScoreBadgeClass = (score: number | null) => {
    if (score === null) return "bg-gray-800 text-gray-400";
    if (score >= 80) return "bg-green-500/20 text-green-400";
    if (score >= 60) return "bg-yellow-500/20 text-yellow-400";
    if (score >= 40) return "bg-orange-500/20 text-orange-400";
    return "bg-red-500/20 text-red-400";
  };

  const getStatusBadgeClass = (status: string) => {
    if (status === "completed") return "bg-green-500/20 text-green-400";
    if (status === "failed") return "bg-red-500/20 text-red-400";
    return "bg-indigo-500/20 text-indigo-400 animate-pulse";
  };

  const formatDate = (dateString: string) => {
    try {
      const date = new Date(dateString);
      return `${date.toLocaleDateString()} ${date.toLocaleTimeString()}`;
    } catch {
      return dateString;
    }
  };

  return (
    <main className="min-h-screen bg-gray-950 text-gray-100">
      <div className="max-w-4xl mx-auto px-6 py-10 space-y-8">
        <div>
          <Link
            href="/"
            className="text-gray-500 hover:text-white transition-colors text-sm font-medium"
          >
            ← Back
          </Link>
          <h1 className="text-4xl font-bold mt-6 text-white">Scan History</h1>
          <p className="text-gray-400 mt-2">Your 20 most recent scans</p>
        </div>

        {isLoading && (
          <div className="flex flex-col items-center justify-center py-20 space-y-4">
            <svg
              className="animate-spin h-8 w-8 text-indigo-500"
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
            >
              <circle
                className="opacity-25"
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                strokeWidth="4"
              />
              <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
              />
            </svg>
            <p className="text-gray-400">Loading history...</p>
          </div>
        )}

        {error && (
          <div className="bg-red-500/10 border border-red-500/20 rounded-xl p-6 text-center space-y-4">
            <div className="text-red-400 font-semibold">Failed to Load History</div>
            <p className="text-gray-300 text-sm">{error}</p>
          </div>
        )}

        {!isLoading && !error && scans.length === 0 && (
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-10 text-center space-y-6">
            <p className="text-gray-400">
              No scans yet. Analyze a repository to get started.
            </p>
            <Link
              href="/"
              className="inline-block px-6 py-3 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg transition-colors text-sm font-medium"
            >
              Go to Homepage
            </Link>
          </div>
        )}

        {!isLoading && !error && scans.length > 0 && (
          <div className="space-y-4">
            {scans.map((scan) => (
              <div
                key={scan.id}
                className="bg-gray-900 border border-gray-800 rounded-xl p-5 hover:border-gray-700 transition flex flex-col sm:flex-row sm:items-center justify-between gap-4"
              >
                <div className="flex-1 min-w-0">
                  <h3 className="font-mono text-white text-base md:text-lg truncate block">
                    {scan.repo_url}
                  </h3>
                  <p className="text-xs text-gray-500 mt-1" suppressHydrationWarning>
                    {formatDate(scan.created_at)}
                  </p>
                </div>

                <div className="flex items-center gap-3 shrink-0 flex-wrap sm:flex-nowrap">
                  {/* Score badge */}
                  <span
                    className={`px-3 py-1 text-xs font-semibold rounded-full ${getScoreBadgeClass(
                      scan.score
                    )}`}
                  >
                    Score: {scan.score !== null ? scan.score : "—"}
                  </span>

                  {/* Status badge */}
                  <span
                    className={`px-3 py-1 text-xs font-semibold rounded-full ${getStatusBadgeClass(
                      scan.status
                    )}`}
                  >
                    {scan.status}
                  </span>

                  {/* View Results Link */}
                  {scan.status === "completed" && (
                    <Link
                      href={`/scan/${scan.id}`}
                      className="text-indigo-400 hover:text-indigo-300 text-sm font-medium ml-2"
                    >
                      View Results →
                    </Link>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </main>
  );
}

export default function HistoryPage() {
  return (
    <AuthGuard>
      <HistoryContent />
    </AuthGuard>
  );
}
