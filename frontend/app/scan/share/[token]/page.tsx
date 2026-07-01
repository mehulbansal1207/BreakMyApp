"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { getShareScan } from "@/lib/api";
import { ScanShareResponse } from "@/types/scan";

export default function ShareScanPage({ params }: { params: { token: string } }) {
  const shareToken = params.token;
  const [scan, setScan] = useState<ScanShareResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pollTimedOut, setPollTimedOut] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let timeoutId: ReturnType<typeof setTimeout>;

    const POLL_TIMEOUT_MS = 10 * 60 * 1000;
    const startedAt = Date.now();

    const poll = async () => {
      try {
        const data = await getShareScan(shareToken);
        if (cancelled) return;
        setScan(data);
        if (data.status === "completed" || data.status === "failed") return;
        if (Date.now() - startedAt > POLL_TIMEOUT_MS) {
          setPollTimedOut(true);
          return;
        }
        timeoutId = setTimeout(poll, 2000);
      } catch (err: unknown) {
        if (cancelled) return;
        const msg =
          err instanceof Error ? err.message : "Failed to fetch scan.";
        if (msg.includes("(404)")) {
          setError("Scan not found. The share link may be invalid or expired.");
        } else {
          setError(msg);
        }
      }
    };

    poll();
    return () => {
      cancelled = true;
      clearTimeout(timeoutId);
    };
  }, [shareToken]);

  if (!scan && !error) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen space-y-4 bg-gray-950 text-white">
        <Spinner />
        <p className="text-gray-400">Loading scan results...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen p-6 bg-gray-950 text-white">
        <div className="bg-red-500/10 border border-red-500/20 rounded-xl p-8 max-w-lg text-center space-y-6">
          <svg className="w-12 h-12 text-red-400 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
          <div className="text-red-400 font-medium text-lg">Scan Not Found</div>
          <p className="text-gray-300">{error}</p>
          <Link
            href="/"
            className="inline-block px-6 py-3 bg-gray-800 hover:bg-gray-700 text-white rounded-lg transition-colors"
          >
            ← Back to Home
          </Link>
        </div>
      </div>
    );
  }

  if (pollTimedOut) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen p-6 bg-gray-950 text-white">
        <div className="bg-gray-900 border border-indigo-500/20 rounded-xl p-10 max-w-lg w-full text-center space-y-6 shadow-2xl">
          <h2 className="text-xl font-semibold text-white">Taking longer than expected</h2>
          <p className="text-gray-400 text-sm">
            This scan is still processing. Check back in a few minutes.
          </p>
          <Link
            href="/"
            className="inline-block px-6 py-3 bg-gray-800 hover:bg-gray-700 text-white rounded-lg transition-colors"
          >
            ← Back to Home
          </Link>
        </div>
      </div>
    );
  }

  if (scan?.status === "pending") {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen p-6 bg-gray-950 text-white">
        <div className="bg-gray-900 border border-indigo-500/20 rounded-xl p-10 max-w-lg w-full text-center space-y-6 shadow-2xl">
          <div className="flex justify-center">
            <Spinner size="w-12 h-12" />
          </div>
          <div className="space-y-2">
            <h2 className="text-xl font-semibold text-white">Cloning repository...</h2>
            <p className="text-sm text-gray-400 break-all">{scan.repo_url}</p>
          </div>
          <p className="text-xs text-gray-500 pt-4">
            This usually takes 30-90 seconds
          </p>
        </div>
      </div>
    );
  }

  if (scan?.status === "running") {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen p-6 bg-gray-950 text-white">
        <div className="bg-gray-900 border border-indigo-500/20 rounded-xl p-10 max-w-lg w-full text-center space-y-6 shadow-2xl">
          <p className="text-sm text-gray-400 break-all">{scan.repo_url}</p>
          <h2 className="text-xl font-semibold text-white">Scanning repository...</h2>
          <div className="w-2 h-2 rounded-full bg-indigo-500 animate-pulse mx-auto mt-4" />
          <p className="text-xs text-gray-500">Results will appear automatically</p>
        </div>
      </div>
    );
  }

  if (scan?.status === "failed") {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen p-6 bg-gray-950 text-white">
        <div className="bg-red-500/10 border border-red-500/20 rounded-xl p-8 max-w-lg text-center space-y-6">
          <div className="text-red-400 text-xl font-semibold">Scan Failed</div>
          <p className="text-gray-300">
            An error occurred during the analysis process.
          </p>
          <Link
            href="/"
            className="inline-block px-6 py-3 bg-red-500 hover:bg-red-600 text-white rounded-lg transition-colors"
          >
            ← Back to Home
          </Link>
        </div>
      </div>
    );
  }

  // ── Completed scan — limited public view ──────────────────────────────────

  if (!scan) return null;

  const scoreColor = (scan.score ?? 0) >= 80
    ? "#22c55e"
    : (scan.score ?? 0) >= 60
      ? "#eab308"
      : (scan.score ?? 0) >= 40
        ? "#f97316"
        : "#ef4444";

  const categoryLabels: Record<string, { label: string; icon: string }> = {
    secrets: { label: "Secrets & Credentials", icon: "🔐" },
    security: { label: "Static Security (SAST)", icon: "🛡️" },
    code_quality: { label: "Code Quality & Linting", icon: "🔧" },
    dependencies: { label: "Vulnerable Dependencies", icon: "📦" },
    custom: { label: "Custom Vulnerability Scan", icon: "🎯" },
  };

  return (
    <div className="max-w-3xl mx-auto px-6 py-10 space-y-10 bg-gray-950 text-white min-h-screen">
      {/* Header */}
      <div className="space-y-2">
        <div className="flex items-center gap-2 text-indigo-400">
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
          </svg>
          <span className="text-sm font-medium">Shared Scan Report</span>
        </div>
        <h1 className="text-2xl font-bold break-all">{scan.repo_url}</h1>
        <p className="text-xs text-gray-500">
          Scanned on {new Date(scan.created_at).toLocaleDateString("en-US", {
            year: "numeric",
            month: "long",
            day: "numeric",
          })}
        </p>
      </div>

      {/* Score + Executive Summary */}
      <div className="flex flex-col md:flex-row gap-8 items-center md:items-start bg-gray-900 border border-gray-800 rounded-2xl p-8">
        <div className="shrink-0">
          <ShareScoreRing score={scan.score ?? 0} color={scoreColor} />
        </div>
        <div className="space-y-4 flex-1">
          <h2 className="text-xl font-semibold text-white">Executive Summary</h2>
          <p className="text-gray-300 leading-relaxed text-lg">
            {scan.executive_summary || "No summary available yet."}
          </p>
          {scan.score_explanation && (
            <div className="text-sm text-gray-400 bg-gray-800/50 p-4 rounded-lg border border-gray-700/50">
              {scan.score_explanation}
            </div>
          )}
        </div>
      </div>

      {/* Top Priorities */}
      {scan.top_priorities && scan.top_priorities.length > 0 && (
        <div className="space-y-4">
          <h3 className="text-xl font-bold">Top Priorities</h3>
          <div className="grid gap-4">
            {scan.top_priorities.map((p, idx) => (
              <div
                key={idx}
                className="bg-gray-900 border border-gray-800 rounded-xl p-5 flex gap-4"
              >
                <div className="shrink-0 mt-0.5">
                  <div className="w-7 h-7 bg-indigo-500/20 text-indigo-400 rounded-full flex items-center justify-center font-bold text-sm">
                    {idx + 1}
                  </div>
                </div>
                <div className="space-y-2 flex-1">
                  <div className="flex items-center gap-3">
                    <h4 className="font-semibold">{p.title}</h4>
                    <span className="px-2 py-0.5 rounded text-[10px] font-bold tracking-wider border uppercase bg-gray-800 text-gray-300 border-gray-700">
                      {p.severity}
                    </span>
                  </div>
                  <p className="text-gray-400 text-sm">{p.explanation}</p>
                  <div className="bg-green-500/10 border border-green-500/20 text-green-400 text-sm p-2.5 rounded-lg font-medium">
                    <span className="mr-1.5">💡</span>
                    {p.action}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Findings Summary */}
      <div className="space-y-4">
        <h3 className="text-xl font-bold">Findings Overview</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {Object.entries(scan.findings_summary).map(([key, count]) => {
            const meta = categoryLabels[key];
            if (!meta) return null;
            return (
              <div
                key={key}
                className="flex items-center justify-between bg-gray-900 border border-gray-800 rounded-xl px-5 py-4"
              >
                <div className="flex items-center gap-3">
                  <span className="text-lg">{meta.icon}</span>
                  <span className="text-sm text-gray-300 font-medium">{meta.label}</span>
                </div>
                <span
                  className={`text-lg font-bold ${
                    count > 0 ? "text-amber-400" : "text-green-400"
                  }`}
                >
                  {count}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Category Summaries */}
      {scan.category_summaries && Object.keys(scan.category_summaries).length > 0 && (
        <div className="space-y-4">
          <h3 className="text-xl font-bold">Category Analysis</h3>
          <div className="grid gap-3">
            {Object.entries(scan.category_summaries).map(([key, summary]) => {
              const meta = categoryLabels[key];
              if (!meta || !summary) return null;
              return (
                <div
                  key={key}
                  className="bg-gray-900 border border-gray-800 rounded-xl p-5 space-y-2"
                >
                  <div className="flex items-center gap-2">
                    <span className="text-lg">{meta.icon}</span>
                    <h4 className="font-semibold text-gray-200">{meta.label}</h4>
                  </div>
                  <p className="text-gray-400 text-sm leading-relaxed">{summary}</p>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Sign In CTA */}
      <div className="bg-gradient-to-r from-indigo-500/10 to-purple-500/10 border border-indigo-500/20 rounded-2xl p-8 text-center space-y-4">
        <svg
          className="w-10 h-10 text-indigo-400 mx-auto"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={1.5}
            d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
          />
        </svg>
        <h3 className="text-lg font-bold text-white">
          Want the full report?
        </h3>
        <p className="text-gray-400 text-sm max-w-md mx-auto">
          Sign in to see all individual findings, export reports as PDF/Markdown,
          download raw scanner artifacts, and create GitHub Issues automatically.
        </p>
        <Link
          href={`/login?returnTo=/scan/share/${shareToken}`}
          className="inline-block bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl px-8 py-3 text-sm font-medium transition"
        >
          Sign in to see full report
        </Link>
      </div>

      {/* Footer */}
      <div className="text-center pt-6 pb-4 border-t border-gray-800">
        <a
          href="https://breakmyapp.tech"
          target="_blank"
          rel="noopener noreferrer"
          className="text-sm text-gray-500 hover:text-gray-300 transition"
        >
          Powered by <span className="font-semibold text-indigo-400">BreakMyApp</span>
        </a>
      </div>
    </div>
  );
}

// ── Score Ring (simplified version for share page) ──────────────────────────

function ShareScoreRing({ score, color }: { score: number; color: string }) {
  const [animatedScore, setAnimatedScore] = useState(0);
  useEffect(() => {
    const timer = setTimeout(() => setAnimatedScore(score), 50);
    return () => clearTimeout(timer);
  }, [score]);

  const size = 180;
  const strokeWidth = 14;
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference - (animatedScore / 100) * circumference;

  return (
    <div className="relative flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="transform -rotate-90" style={{ overflow: "visible" }}>
        <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="#1f2937" strokeWidth={strokeWidth} />
        <circle
          cx={size / 2} cy={size / 2} r={radius}
          fill="none" stroke={color} strokeWidth={strokeWidth}
          strokeDasharray={circumference} strokeDashoffset={strokeDashoffset}
          strokeLinecap="round"
          style={{ transition: "stroke-dashoffset 1s ease-out" }}
        />
      </svg>
      <div className="absolute flex flex-col items-center justify-center text-center">
        <span className="text-4xl font-bold tracking-tighter" style={{ color }}>
          {animatedScore}
        </span>
        <span className="text-[10px] font-medium text-gray-400 mt-1 uppercase tracking-widest">
          / 100
        </span>
      </div>
    </div>
  );
}

function Spinner({ size = "w-8 h-8" }: { size?: string }) {
  return (
    <svg
      className={`animate-spin text-indigo-400 ${size}`}
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
    >
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
      />
    </svg>
  );
}
