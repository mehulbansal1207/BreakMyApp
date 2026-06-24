import { auth } from "@/lib/firebase";
import { getIdToken } from "@/lib/firebase-auth";

export async function getAuthToken(): Promise<string | null> {
  try {
    return await getIdToken();
  } catch {
    return null;
  }
}

export function getCurrentUser() {
  return auth.currentUser;
}

export function isLoggedIn(): boolean {
  return auth.currentUser !== null;
}
