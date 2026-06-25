"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  signInWithGoogle,
  signInWithGithub,
  signInWithEmail,
  signUpWithEmail,
  onAuthChange,
  reloadUser,
  resendVerificationEmail,
  logOut,
} from "@/lib/firebase-auth";
import { auth } from "@/lib/firebase";
import { getCurrentUserInfo } from "@/lib/api";

function getFirebaseErrorMessage(code: string): string | null {
  switch (code) {
    case "auth/user-not-found":
      return "No account found with this email.";
    case "auth/wrong-password":
      return "Incorrect password.";
    case "auth/email-already-in-use":
      return "An account with this email already exists.";
    case "auth/weak-password":
      return "Password must be at least 6 characters.";
    case "auth/popup-closed-by-user":
      return null; // silent
    case "auth/invalid-credential":
      return "Invalid email or password.";
    case "auth/too-many-requests":
      return "Too many failed attempts. Please try again later.";
    case "auth/account-exists-with-different-credential":
      return "An account already exists with a different sign-in method for this email.";
    case "auth/unauthorized-domain":
      return "This domain is not authorised for sign-in. Please contact support.";
    case "auth/operation-not-allowed":
      return "This sign-in method is not enabled. Please contact support.";
    case "auth/popup-blocked":
      return "Sign-in popup was blocked by your browser. Please allow popups and try again.";
    case "auth/cancelled-popup-request":
      return null; // silent – another popup opened
    default:
      return "Something went wrong. Please try again.";
  }
}

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [awaitingVerification, setAwaitingVerification] = useState(false);
  const [resentConfirm, setResentConfirm] = useState(false);
  const [resendCooldown, setResendCooldown] = useState(0);

  // Redirect if already logged in (and verified)
  useEffect(() => {
    const unsubscribe = onAuthChange((user) => {
      if (user && (user.emailVerified || user.providerData[0]?.providerId !== "password")) {
        router.replace("/");
      }
    });
    return unsubscribe;
  }, [router]);

  useEffect(() => {
    if (resendCooldown <= 0) return;
    const timer = setTimeout(() => setResendCooldown((c) => c - 1), 1000);
    return () => clearTimeout(timer);
  }, [resendCooldown]);

  const handleSocialLogin = async (provider: "google" | "github") => {
    setError(null);
    setIsLoading(true);
    try {
      if (provider === "google") {
        await signInWithGoogle();
      } else {
        await signInWithGithub();
      }
      // Register / update the user in the backend DB immediately.
      // Without this call, /api/v1/auth/me is never hit and the user
      // record is never created, breaking all authenticated API calls.
      await getCurrentUserInfo();
      router.replace("/");
    } catch (err: unknown) {
      const code = (err as { code?: string }).code ?? "";
      console.error("Firebase social login failed", { provider, code, err });
      const msg = getFirebaseErrorMessage(code);
      if (msg) setError(msg);
    } finally {
      setIsLoading(false);
    }
  };

  const handleEmailSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsLoading(true);
    try {
      if (mode === "signin") {
        await signInWithEmail(email, password);
        // Check email verification for password accounts
        if (!auth.currentUser?.emailVerified) {
          await logOut();
          setError(
            "Please verify your email before signing in. Check your inbox for the verification link."
          );
          return;
        }
        router.replace("/");
      } else {
        await signUpWithEmail(email, password);
        // Don't redirect — show verification pending screen
        setAwaitingVerification(true);
      }
    } catch (err: unknown) {
      const code = (err as { code?: string }).code ?? "";
      const msg = getFirebaseErrorMessage(code);
      if (msg) setError(msg);
    } finally {
      setIsLoading(false);
    }
  };

  const handleCheckVerified = async () => {
    setError(null);
    try {
      await reloadUser();
      if (auth.currentUser?.emailVerified) {
        router.replace("/");
      } else {
        setError("Email not verified yet. Please check your inbox.");
      }
    } catch {
      setError("Something went wrong. Please try again.");
    }
  };

  const handleResend = async () => {
    if (resendCooldown > 0) return;
    setError(null);
    const result = await resendVerificationEmail();
    if (result.success) {
      setResentConfirm(true);
      setResendCooldown(60);
      setTimeout(() => setResentConfirm(false), 3000);
    } else {
      if (result.errorCode === "auth/too-many-requests") {
        setError("Too many requests. Please wait a few minutes before resending.");
      } else {
        setError("Failed to resend verification email. Please try again.");
      }
    }
  };

  // ── Verification pending screen ──────────────────────────────────────────
  if (awaitingVerification) {
    return (
      <main className="min-h-screen bg-gray-950 flex items-center justify-center px-6 py-16">
        <div className="w-full max-w-md">
          <div className="bg-gray-900 border border-gray-800 rounded-2xl p-8 space-y-6 text-center">
            {/* Email icon */}
            <svg
              className="w-12 h-12 text-indigo-400 mx-auto"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={1.5}
                d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"
              />
            </svg>

            <h1 className="text-xl font-bold text-white">Check your email</h1>
            <p className="text-gray-400 text-sm">
              We sent a verification link to{" "}
              <span className="text-indigo-300 font-medium">{email}</span>. Click
              the link to verify your account.
            </p>

            {error && <p className="text-red-400 text-sm">{error}</p>}

            <button
              onClick={handleCheckVerified}
              className="w-full py-3 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl font-medium text-sm transition"
            >
              I&apos;ve verified my email
            </button>

            <button
              onClick={handleResend}
              disabled={resendCooldown > 0}
              className="text-sm text-indigo-400 hover:text-indigo-300 transition disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {resentConfirm
                ? "Sent! ✓"
                : resendCooldown > 0
                ? `Resend in ${resendCooldown}s`
                : "Resend verification email"}
            </button>

            <p className="text-xs text-gray-600">
              <button
                onClick={() => {
                  setAwaitingVerification(false);
                  setMode("signin");
                  setError(null);
                }}
                className="hover:text-gray-400 transition"
              >
                ← Back to sign in
              </button>
            </p>
          </div>
        </div>
      </main>
    );
  }

  // ── Main login form ──────────────────────────────────────────────────────
  return (
    <main className="min-h-screen bg-gray-950 flex items-center justify-center px-6 py-16">
      <div className="w-full max-w-md">
        <div className="bg-gray-900 border border-gray-800 rounded-2xl p-8 space-y-6">
          {/* Header */}
          <div className="text-center space-y-1">
            <h1 className="text-2xl font-bold text-indigo-400">BreakMyApp</h1>
            <p className="text-gray-400 text-sm">Sign in to continue</p>
          </div>

          {/* Social login buttons */}
          <div className="space-y-3">
            <button
              onClick={() => handleSocialLogin("google")}
              disabled={isLoading}
              className="w-full flex items-center justify-center gap-3 py-3 px-4 bg-white text-gray-900 hover:bg-gray-50 rounded-xl font-semibold text-sm transition disabled:opacity-50 shadow-sm border border-gray-200"
            >
              {/* Google G icon */}
              <svg width="18" height="18" viewBox="0 0 24 24">
                <path
                  fill="#4285F4"
                  d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
                />
                <path
                  fill="#34A853"
                  d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                />
                <path
                  fill="#FBBC05"
                  d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
                />
                <path
                  fill="#EA4335"
                  d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
                />
              </svg>
              Continue with Google
            </button>

            <button
              onClick={() => handleSocialLogin("github")}
              disabled={isLoading}
              className="w-full flex items-center justify-center gap-3 py-3 px-4 bg-[#24292e] text-white hover:bg-[#2f363d] rounded-xl font-semibold text-sm transition disabled:opacity-50 border border-gray-600"
            >
              {/* GitHub mark */}
              <svg width="18" height="18" viewBox="0 0 24 24" fill="white">
                <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0 0 24 12c0-6.63-5.37-12-12-12z" />
              </svg>
              Continue with GitHub
            </button>
          </div>

          {/* Divider */}
          <div className="flex items-center gap-4">
            <div className="flex-1 h-px bg-gray-800" />
            <span className="text-gray-600 text-sm">or</span>
            <div className="flex-1 h-px bg-gray-800" />
          </div>

          {/* Email/password form */}
          <form onSubmit={handleEmailSubmit} className="space-y-4">
            <div>
              <label htmlFor="login-email" className="block text-xs text-gray-500 mb-1 uppercase tracking-wider font-medium">
                Email
              </label>
              <input
                id="login-email"
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                className="w-full px-4 py-3 bg-gray-950 border border-gray-700 rounded-xl text-white placeholder:text-gray-600 focus:outline-none focus:ring-2 focus:ring-indigo-500 transition text-sm"
              />
            </div>

            <div>
              <label htmlFor="login-password" className="block text-xs text-gray-500 mb-1 uppercase tracking-wider font-medium">
                Password
              </label>
              <input
                id="login-password"
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className="w-full px-4 py-3 bg-gray-950 border border-gray-700 rounded-xl text-white placeholder:text-gray-600 focus:outline-none focus:ring-2 focus:ring-indigo-500 transition text-sm"
              />
            </div>

            {error && <p className="text-red-400 text-sm">{error}</p>}

            <button
              type="submit"
              disabled={isLoading}
              className="w-full py-3 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl font-medium transition disabled:opacity-50 disabled:cursor-not-allowed text-sm"
            >
              {isLoading
                ? "Please wait..."
                : mode === "signin"
                ? "Sign In"
                : "Sign Up"}
            </button>

            <p className="text-center text-sm text-gray-500">
              {mode === "signin" ? (
                <>
                  Don&apos;t have an account?{" "}
                  <button
                    type="button"
                    onClick={() => { setMode("signup"); setError(null); }}
                    className="text-indigo-400 hover:text-indigo-300 transition"
                  >
                    Sign up
                  </button>
                </>
              ) : (
                <>
                  Already have an account?{" "}
                  <button
                    type="button"
                    onClick={() => { setMode("signin"); setError(null); }}
                    className="text-indigo-400 hover:text-indigo-300 transition"
                  >
                    Sign in
                  </button>
                </>
              )}
            </p>
          </form>

          <p className="text-center text-xs text-gray-600">
            <Link href="/" className="hover:text-gray-400 transition">
              ← Back to scanner
            </Link>
          </p>
        </div>
      </div>
    </main>
  );
}
