import { initializeApp, getApps } from "firebase/app";
import { getAuth } from "firebase/auth";

const firebaseConfig = {
  apiKey: "AIzaSyBNeoa6SexUoOrilFCUKERCGuGNEMYnxd4",
  authDomain: "break-my-app.firebaseapp.com",
  projectId: "break-my-app",
  storageBucket: "break-my-app.firebasestorage.app",
  messagingSenderId: "1002848451947",
  appId: "1:1002848451947:web:c2c52ecdc45cb7a9e6e02e",
  measurementId: "G-KJEQLCX689",
};

// Prevent duplicate initialization in Next.js hot reload
const app =
  getApps().length === 0 ? initializeApp(firebaseConfig) : getApps()[0];

export const auth = getAuth(app);
export default app;
