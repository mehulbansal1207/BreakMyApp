"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { getScan } from "@/lib/api";
import { ScanResponse } from "@/types/scan";
import ScoreRing from "./ScoreRing";
import CategorySection from "./CategorySection";
import FindingCard from "./FindingCard";

export default function StatusPoller({ scanId }: { scanId: string }) {
  const [scan, setScan] = useState<ScanResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    let timeoutId: ReturnType<typeof setTimeout>;

    const poll = async () => {
      try {
        const data = await getScan(scanId);
        if (cancelled) return;
        setScan(data);
        if (data.status === "completed" || data.status === "failed") return;
        timeoutId = setTimeout(poll, 2000);
      } catch (err: unknown) {
        if (cancelled) return;
        const msg =
          err instanceof Error ? err.message : "Failed to fetch scan status.";
        setError(msg);
      }
    };

    poll();
    return () => {
      cancelled = true;
      clearTimeout(timeoutId);
    };
  }, [scanId]);

  if (!scan && !error) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen space-y-4">
        <Spinner />
        <p className="text-gray-400">Initializing scan...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen p-6">
        <div className="bg-red-500/10 border border-red-500/20 rounded-xl p-8 max-w-lg text-center space-y-6">
          <div className="text-red-400 font-medium">Error</div>
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

  if (scan?.status === "pending" || scan?.status === "running") {
    const statusMsg =
      scan.status === "pending"
        ? "Cloning repository..."
        : "Running security scanners...";
    return (
      <div className="flex flex-col items-center justify-center min-h-screen p-6">
        <div className="bg-gray-900 border border-indigo-500/20 rounded-xl p-10 max-w-lg w-full text-center space-y-6 shadow-2xl">
          <div className="flex justify-center text-brand">
            <Spinner size="w-12 h-12" />
          </div>
          <div className="space-y-2">
            <h2 className="text-xl font-semibold text-white">{statusMsg}</h2>
            <p className="text-sm text-gray-400 break-all">{scan.repo_url}</p>
          </div>
          <p className="text-xs text-gray-500 pt-4">
            This usually takes 30-90 seconds
          </p>
        </div>
      </div>
    );
  }

  if (scan?.status === "failed") {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen p-6">
        <div className="bg-red-500/10 border border-red-500/20 rounded-xl p-8 max-w-lg text-center space-y-6">
          <div className="text-red-400 text-xl font-semibold">Scan Failed</div>
          <p className="text-gray-300">
            {scan.findings?.ai_explanation?.error ||
              "An error occurred during the analysis process."}
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

  if (!scan?.findings) return null;
  const { findings, score } = scan;
  const ai = findings.ai_explanation;
  const repo = findings.repo_info;

  return (
    <div className="max-w-4xl mx-auto px-6 py-10 space-y-12">
      <div>
        <Link
          href="/"
          className="text-gray-500 hover:text-white transition-colors text-sm font-medium"
        >
          ← Scan Another Repository
        </Link>
        <h1 className="text-2xl font-bold mt-6 break-all">{scan.repo_url}</h1>
      </div>

      {score === 0 && (
        <div className="w-full bg-amber-500/10 border border-amber-500/30 rounded-xl p-4 flex gap-3">
          <svg
            className="w-5 h-5 text-amber-400 shrink-0"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
            xmlns="http://www.w3.org/2000/svg"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
            />
          </svg>
          <div>
            <h4 className="text-amber-400 font-semibold text-sm">
              {"Score of 0 — Here's why"}
            </h4>
            <p className="text-amber-300/80 text-sm">
              A score of 0 typically means critical secrets or credentials were
              detected in your repository. Each critical secret deducts 20 points.
              Review the Secrets & Credentials section below and rotate any exposed
              credentials immediately.
            </p>
          </div>
        </div>
      )}

      <div className="flex flex-col md:flex-row gap-8 items-center md:items-start bg-gray-900 border border-gray-800 rounded-2xl p-8">
        <div className="shrink-0">
          <ScoreRing score={score || 0} size={220} />
        </div>
        <div className="space-y-4 flex-1">
          <h2 className="text-xl font-semibold text-white">
            Executive Summary
          </h2>
          <p className="text-gray-300 leading-relaxed text-lg">
            {ai.executive_summary}
          </p>
          <div className="text-sm text-gray-400 bg-gray-800/50 p-4 rounded-lg border border-gray-700/50">
            {ai.score_explanation}
          </div>
        </div>
      </div>

      {ai.top_priorities && ai.top_priorities.length > 0 && (
        <div className="space-y-6">
          <h3 className="text-2xl font-bold">Top Priorities</h3>
          <div className="grid gap-4">
            {ai.top_priorities.slice(0, 3).map((p, idx) => (
              <div
                key={idx}
                className="bg-gray-900 border border-gray-800 rounded-xl p-6 flex gap-4"
              >
                <div className="shrink-0 mt-1">
                  <div className="w-8 h-8 bg-brand/20 text-brand rounded-full flex items-center justify-center font-bold">
                    {idx + 1}
                  </div>
                </div>
                <div className="space-y-3 flex-1">
                  <div className="flex items-center gap-3">
                    <h4 className="text-lg font-semibold">{p.title}</h4>
                    <span className="px-2 py-0.5 rounded text-[10px] font-bold tracking-wider border uppercase bg-gray-800 text-gray-300 border-gray-700">
                      {p.severity}
                    </span>
                  </div>
                  <p className="text-gray-400 text-sm">{p.explanation}</p>
                  <div className="bg-green-500/10 border border-green-500/20 text-green-400 text-sm p-3 rounded-lg font-medium">
                    <span className="mr-2">💡</span>
                    {p.action}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="flex flex-wrap gap-3">
        {repo.languages.map((l) => (
          <Badge key={l} color="indigo">{l}</Badge>
        ))}
        {repo.has_tests || repo.has_ci ? (
          <Badge color="green">Tests/CI Found</Badge>
        ) : (
          <Badge color="red">No Tests/CI</Badge>
        )}
        {repo.has_dockerfile ? (
          <Badge color="green">Dockerized</Badge>
        ) : (
          <Badge color="gray">No Dockerfile</Badge>
        )}
        <Badge color="gray">{repo.total_files} Files</Badge>
        <Badge color="gray">{repo.repo_size_mb.toFixed(2)} MB</Badge>
      </div>

      <div className="space-y-4">
        <h3 className="text-2xl font-bold pb-2">Detailed Findings</h3>

        <CategorySection
          title="Secrets & Credentials"
          findingsCount={findings.secrets.findings_count}
          aiSummary={ai.category_summaries.secrets}
          icon={
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" />
            </svg>
          }
        >
          {findings.secrets.findings_count === 0 ? (
            <NoIssues />
          ) : (
            findings.secrets.findings.map((f, i) => (
              <FindingCard
                key={i}
                severity={f.severity}
                file={f.file}
                line={f.line}
                message={`${f.detector} credential detected`}
                extra={{ Type: f.type, Preview: f.raw }}
              />
            ))
          )}
        </CategorySection>

        <CategorySection
          title="Static Security (SAST)"
          findingsCount={findings.semgrep.findings_count}
          aiSummary={ai.category_summaries.security}
          icon={
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
            </svg>
          }
        >
          {findings.semgrep.findings_count === 0 ? (
            <NoIssues />
          ) : (
            findings.semgrep.findings.map((f, i) => (
              <FindingCard
                key={i}
                severity={f.severity}
                file={f.file}
                line={f.line_start}
                message={f.message}
                extra={{ Rule: f.rule_id, Category: f.category }}
              />
            ))
          )}
        </CategorySection>

        <CategorySection
          title="Code Quality & Linting"
          findingsCount={findings.bandit.findings_count}
          aiSummary={ai.category_summaries.code_quality}
          icon={
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
            </svg>
          }
        >
          {findings.bandit.findings_count === 0 ? (
            <NoIssues />
          ) : (
            findings.bandit.findings.map((f, i) => (
              <FindingCard
                key={i}
                severity={f.severity}
                file={f.file}
                line={f.line}
                message={f.message}
                extra={{ Test: f.test_id, Confidence: f.confidence }}
              />
            ))
          )}
        </CategorySection>

        <CategorySection
          title="Vulnerable Dependencies"
          findingsCount={findings.dependencies.findings_count}
          aiSummary={ai.category_summaries.dependencies}
          icon={
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
            </svg>
          }
        >
          {findings.dependencies.findings_count === 0 ? (
            <NoIssues />
          ) : (
            findings.dependencies.findings.map((f, i) => (
              <FindingCard
                key={i}
                severity={f.severity}
                file={f.package}
                message={`${f.description} (Installed: ${f.installed_version})`}
                extra={{
                  ID: f.vulnerability_id,
                  Fix: f.fix_version || "None",
                  Ecosystem: f.ecosystem,
                }}
              />
            ))
          )}
        </CategorySection>
      </div>

      {ai.positive_findings && ai.positive_findings.length > 0 && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-8 space-y-6">
          <h3 className="text-xl font-bold text-white flex items-center gap-2">
            <span className="text-green-500">✨</span> What&apos;s working well
          </h3>
          <ul className="space-y-3">
            {ai.positive_findings.map((pf, idx) => (
              <li key={idx} className="flex items-start gap-3 text-gray-300">
                <span className="text-green-500 mt-0.5">✓</span>
                {pf}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function Spinner({ size = "w-8 h-8" }: { size?: string }) {
  return (
    <svg
      className={`animate-spin text-brand ${size}`}
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
  );
}

function NoIssues() {
  return (
    <div className="flex items-center gap-2 text-green-400 bg-green-500/10 border border-green-500/20 px-4 py-3 rounded-lg text-sm font-medium">
      <span>✓</span> No issues found in this category
    </div>
  );
}

function Badge({
  children,
  color,
}: {
  children: React.ReactNode;
  color: "indigo" | "green" | "red" | "gray";
}) {
  const colorMap = {
    indigo: "bg-indigo-500/20 text-indigo-300 border-indigo-500/30",
    green: "bg-green-500/20 text-green-400 border-green-500/30",
    red: "bg-red-500/20 text-red-400 border-red-500/30",
    gray: "bg-gray-800 text-gray-300 border-gray-700",
  };
  return (
    <span
      className={`px-3 py-1 text-xs font-medium border rounded-full ${colorMap[color]}`}
    >
      {children}
    </span>
  );
}
