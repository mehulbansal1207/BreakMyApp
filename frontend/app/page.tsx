"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { createScan } from "@/lib/api";

const EXAMPLES = [
  "https://github.com/mehulbansal1207/BookGPT",
  "https://github.com/tiangolo/fastapi",
  "https://github.com/vercel/next.js",
];

export default function Home() {
  const router = useRouter();
  const [inputValue, setInputValue] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async () => {
    setError(null);
    const url = inputValue.trim();

    if (!url) {
      setError("Please enter a repository URL.");
      return;
    }

    // Basic GitHub URL validation
    const githubRegex = /^https?:\/\/(www\.)?github\.com\/[\w.-]+\/[\w.-]+$/i;
    if (!githubRegex.test(url)) {
      setError("Please enter a valid GitHub repository URL (e.g., https://github.com/user/repo).");
      return;
    }

    setIsLoading(true);
    try {
      const scan = await createScan(url);
      router.push(`/scan/${scan.id}`);
    } catch (err: any) {
      setError(err.message || "Failed to start scan. Please try again.");
      setIsLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-6 bg-gray-950">
      <div className="w-full max-w-2xl text-center space-y-8">
        <div className="space-y-4">
          <h1 className="text-5xl md:text-6xl font-bold tracking-tight text-brand">
            BreakMyApp
          </h1>
          <p className="text-lg text-gray-400">
            Before your users break it, we will.
          </p>
        </div>

        <div className="space-y-4 pt-4">
          <div className="relative">
            <input
              type="text"
              placeholder="https://github.com/user/repo"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={isLoading}
              className="w-full px-6 py-4 text-lg bg-gray-900 border border-gray-800 rounded-xl focus:outline-none focus:ring-2 focus:ring-brand font-mono placeholder:text-gray-600 transition-all disabled:opacity-50"
            />
            {error && (
              <p className="absolute -bottom-6 left-2 text-sm text-score-critical">
                {error}
              </p>
            )}
          </div>

          <button
            onClick={handleSubmit}
            disabled={isLoading}
            className="w-full sm:w-auto px-8 py-4 bg-brand hover:bg-brand-dark text-white rounded-xl font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-3 mx-auto"
          >
            {isLoading && (
              <svg
                className="animate-spin h-5 w-5 text-white"
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
                ></circle>
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                ></path>
              </svg>
            )}
            {isLoading ? "Analyzing..." : "Analyze Repository"}
          </button>
        </div>

        <div className="pt-8 space-y-4">
          <p className="text-sm text-gray-500 font-medium uppercase tracking-wider">
            Try an example
          </p>
          <div className="flex flex-wrap justify-center gap-3">
            {EXAMPLES.map((url) => (
              <button
                key={url}
                onClick={() => setInputValue(url)}
                disabled={isLoading}
                className="px-4 py-2 text-sm bg-gray-900 hover:bg-gray-800 border border-gray-800 rounded-full transition-colors text-gray-300 disabled:opacity-50"
              >
                {url.replace("https://github.com/", "")}
              </button>
            ))}
          </div>
        </div>
      </div>
    </main>
  );
}
