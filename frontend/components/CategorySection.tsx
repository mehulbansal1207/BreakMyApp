"use client";

import { useState, ReactNode } from "react";
import clsx from "clsx";

interface CategorySectionProps {
  title: string;
  findingsCount: number;
  aiSummary?: string;
  icon?: ReactNode;
  children: ReactNode;
  defaultOpen?: boolean;
}

export default function CategorySection({
  title,
  findingsCount,
  aiSummary,
  icon,
  children,
  defaultOpen,
}: CategorySectionProps) {
  const [isOpen, setIsOpen] = useState(defaultOpen ?? findingsCount > 0);

  return (
    <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between p-6 bg-gray-900 hover:bg-gray-800/80 transition-colors text-left"
      >
        <div className="flex items-center gap-3">
          {icon && <div className="text-gray-400">{icon}</div>}
          <h2 className="text-xl font-semibold text-gray-100">{title}</h2>
          <span
            className={clsx(
              "ml-2 px-2.5 py-0.5 rounded-full text-xs font-medium",
              findingsCount > 0
                ? "bg-red-500/20 text-red-400 border border-red-500/30"
                : "bg-gray-800 text-gray-400 border border-gray-700"
            )}
          >
            {findingsCount}
          </span>
        </div>

        <div
          className={clsx(
            "text-gray-500 transition-transform duration-300 transform",
            isOpen ? "rotate-180" : "rotate-0"
          )}
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="20"
            height="20"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <polyline points="6 9 12 15 18 9"></polyline>
          </svg>
        </div>
      </button>

      <div
        className={clsx(
          "transition-all duration-300 ease-in-out px-6",
          isOpen
            ? "max-h-[9999px] opacity-100 pb-6"
            : "max-h-0 opacity-0 overflow-hidden pb-0"
        )}
      >
        <div className="space-y-6 pt-2 border-t border-gray-800">
          {aiSummary && (
            <p className="border-l-2 border-indigo-500/50 pl-3 italic text-gray-400 text-sm">
              {aiSummary}
            </p>
          )}
          <div className="space-y-3">{children}</div>
        </div>
      </div>
    </div>
  );
}
