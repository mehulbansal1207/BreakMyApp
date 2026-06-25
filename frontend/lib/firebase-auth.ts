import {
  createUserWithEmailAndPassword,
  GithubAuthProvider,
  GoogleAuthProvider,
  onAuthStateChanged,
  sendEmailVerification,
  signInWithEmailAndPassword,
  signInWithPopup,
  signOut,
  User as FirebaseUser,
} from "firebase/auth";

import { auth } from "@/lib/firebase";

export const googleProvider = new GoogleAuthProvider();
export const githubProvider = new GithubAuthProvider();
githubProvider.addScope("read:user");
githubProvider.addScope("user:email");

export async function signInWithGoogle(): Promise<FirebaseUser> {
  const result = await signInWithPopup(auth, googleProvider);
  return result.user;
}

export async function signInWithGithub(): Promise<FirebaseUser> {
  const result = await signInWithPopup(auth, githubProvider);
  return result.user;
}

export async function signInWithEmail(
  email: string,
  password: string
): Promise<FirebaseUser> {
  const result = await signInWithEmailAndPassword(auth, email, password);
  return result.user;
}

export async function signUpWithEmail(
  email: string,
  password: string
): Promise<FirebaseUser> {
  const result = await createUserWithEmailAndPassword(auth, email, password);
  await sendEmailVerification(result.user);
  return result.user;
}

export async function logOut(): Promise<void> {
  await signOut(auth);
}

export async function getIdToken(): Promise<string | null> {
  const user = auth.currentUser;
  if (!user) return null;
  return user.getIdToken();
}

export function onAuthChange(
  callback: (user: FirebaseUser | null) => void
): () => void {
  return onAuthStateChanged(auth, callback);
}

export async function resendVerificationEmail(): Promise<{ success: boolean; errorCode?: string }> {
  const user = auth.currentUser;
  if (!user || user.emailVerified) {
    return { success: false, errorCode: "auth/no-user" };
  }
  try {
    await sendEmailVerification(user);
    return { success: true };
  } catch (err: unknown) {
    const code = (err as { code?: string }).code ?? "auth/unknown";
    return { success: false, errorCode: code };
  }
}

export async function reloadUser(): Promise<void> {
  try {
    const user = auth.currentUser;
    if (user) await user.reload();
  } catch {
    // Silently ignore reload failures — caller will handle unverified state
  }
}
