import clsx from "clsx";

interface FindingCardProps {
  severity: "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";
  file: string;
  line?: number;
  message: string;
  extra?: Record<string, string>;
}

export default function FindingCard({
  severity,
  file,
  line,
  message,
  extra,
}: FindingCardProps) {
  const badgeClasses = clsx(
    "shrink-0 px-2.5 py-0.5 rounded text-xs font-bold border uppercase tracking-wider",
    {
      "bg-red-500/20 text-red-400 border-red-500/30": severity === "CRITICAL",
      "bg-orange-500/20 text-orange-400 border-orange-500/30":
        severity === "HIGH",
      "bg-yellow-500/20 text-yellow-400 border-yellow-500/30":
        severity === "MEDIUM",
      "bg-blue-500/20 text-blue-400 border-blue-500/30": severity === "LOW",
    }
  );

  return (
    <div className="bg-gray-800/50 rounded-lg px-4 py-3 border border-gray-700/50 hover:bg-gray-800 transition-colors flex flex-row items-start gap-3">
      <div className={badgeClasses}>{severity}</div>

      <div className="flex-1 min-w-0 space-y-1 overflow-hidden">
        <div className="font-mono text-sm text-gray-300 break-all">
          {file}
          {line !== undefined && (
            <span className="text-gray-500">:{line}</span>
          )}
        </div>
        <p className="text-sm text-gray-400 break-words whitespace-normal">
          {message}
        </p>
      </div>

      {extra && Object.keys(extra).length > 0 && (
        <div className="flex flex-wrap gap-2 max-w-[200px]">
          {Object.entries(extra).map(([key, value]) => (
            <div
              key={key}
              title={`${key}: ${value}`}
              className="inline-flex items-center px-2 py-1 rounded-md bg-gray-900 border border-gray-700 text-xs text-gray-400 max-w-full overflow-hidden"
            >
              <span className="font-medium mr-1 text-gray-500 shrink-0">{key}:</span>
              <span className="font-mono text-gray-300 truncate">{value}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
