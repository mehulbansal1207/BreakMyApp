"use client";

import { useEffect, useState } from "react";

interface ScoreRingProps {
  score: number;
  size?: number;
}

export default function ScoreRing({ score, size = 200 }: ScoreRingProps) {
  const [animatedScore, setAnimatedScore] = useState(0);

  useEffect(() => {
    const timer = setTimeout(() => {
      setAnimatedScore(score);
    }, 50);
    return () => clearTimeout(timer);
  }, [score]);

  let color = "#ef4444";
  if (score >= 80) color = "#22c55e";
  else if (score >= 60) color = "#eab308";
  else if (score >= 40) color = "#f97316";

  const strokeWidth = Math.round(size / 12);
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset =
    circumference - (animatedScore / 100) * circumference;

  return (
    <div
      className="relative flex items-center justify-center"
      style={{ width: size, height: size }}
    >
      <svg
        width={size}
        height={size}
        className="transform -rotate-90"
        style={{ overflow: "visible" }}
      >
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="#1f2937"
          strokeWidth={strokeWidth}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={strokeWidth}
          strokeDasharray={circumference}
          strokeDashoffset={strokeDashoffset}
          strokeLinecap="round"
          style={{ transition: "stroke-dashoffset 1s ease-out" }}
        />
      </svg>

      <div className="absolute flex flex-col items-center justify-center text-center">
        <span
          className="text-5xl font-bold tracking-tighter"
          style={{ color }}
        >
          {animatedScore}
        </span>
        <span className="text-xs font-medium text-gray-400 mt-1 uppercase tracking-widest max-w-[60%] leading-tight">
          Production Readiness
        </span>
      </div>
    </div>
  );
}
