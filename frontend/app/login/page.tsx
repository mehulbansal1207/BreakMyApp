import { Suspense } from "react";
import LoginContent from "./LoginContent";

/**
 * /login — outer page (server component).
 *
 * `useSearchParams()` is called inside <LoginContent>, which is a client
 * component.  Next.js 14 requires every component that calls
 * `useSearchParams()` to be wrapped in a <Suspense> boundary; without one
 * the static pre-render step throws:
 *
 *   Error: useSearchParams() should be wrapped in a suspense boundary …
 *
 * Keeping this file as a server component and wrapping <LoginContent> in
 * <Suspense> is the minimal, idiomatic fix.
 */
export default function LoginPage() {
  return (
    <Suspense
      fallback={
        <main className="min-h-screen bg-gray-950 flex items-center justify-center">
          <div className="w-8 h-8 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
        </main>
      }
    >
      <LoginContent />
    </Suspense>
  );
}
