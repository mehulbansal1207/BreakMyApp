"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { User as FirebaseUser } from "firebase/auth";
import { onAuthChange } from "@/lib/firebase-auth";

export default function AuthGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [user, setUser] = useState<FirebaseUser | null>(null);

  useEffect(() => {
    const unsubscribe = onAuthChange((firebaseUser) => {
      setUser(firebaseUser);
      setLoading(false);

      const isEmailProvider = firebaseUser?.providerData.some(
        (p) => p.providerId === "password"
      );
      const needsVerification = isEmailProvider && !firebaseUser?.emailVerified;

      if (!firebaseUser || needsVerification) {
        router.replace("/login");
      }
    });
    return unsubscribe;
  }, [router]);

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-950 flex items-center justify-center">
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
      </div>
    );
  }

  // Determine auth validity (social users skip email verification)
  const isEmailProvider = user?.providerData.some(
    (p) => p.providerId === "password"
  );
  const needsVerification = isEmailProvider && !user?.emailVerified;

  if (!user || needsVerification) {
    // Router is redirecting — render nothing to avoid flash
    return null;
  }

  return <>{children}</>;
}
