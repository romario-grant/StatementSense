"use client";
import { GoogleAuthProvider } from "firebase/auth";
import {
  createContext,
  useContext,
  useEffect,
  useState,
  useCallback,
  type ReactNode,
} from "react";
import { usePathname, useRouter } from "next/navigation";
import {
  auth,
  googleProvider,
  signInWithEmailAndPassword,
  createUserWithEmailAndPassword,
  signInWithPopup,
  signOut as firebaseSignOut,
  onAuthStateChanged,
  type User,
} from "@/lib/firebase";
import { clearAllPageSessions } from "@/lib/pageSessionStore";
import { clearSubscriptionSession } from "@/lib/subscriptionStore";
import { clearUserPreferences } from "@/lib/userPreferenceStore";

/* ── Types ── */

interface AuthContextValue {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (email: string, password: string) => Promise<void>;
  loginWithGoogle: () => Promise<void>;
  logout: () => Promise<void>;
  deleteAccount: () => Promise<void>;
}

/* ── Context ── */

const AuthContext = createContext<AuthContextValue>({
  user: null,
  loading: true,
  login: async () => {},
  signup: async () => {},
  loginWithGoogle: async () => {},
  logout: async () => {},
  deleteAccount: async () => {},
});

export function useAuth() {
  return useContext(AuthContext);
}

/* ── Public Routes ── */
const PUBLIC_ROUTES = ["/login"];

const clearLocalUserData = () => {
  if (typeof window === "undefined") return;
  localStorage.removeItem("google_access_token");
  clearSubscriptionSession();
  clearAllPageSessions();
  clearUserPreferences();
};

/* ── Provider ── */

export default function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const pathname = usePathname();
  const router = useRouter();

  /* Listen for auth state changes */
  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, (firebaseUser) => {
      setUser(firebaseUser);
      setLoading(false);
    });
    return () => unsubscribe();
  }, []);

  /* Route guard — redirect logic */
  useEffect(() => {
    if (loading) return;

    const isPublicRoute = PUBLIC_ROUTES.includes(pathname);

    if (!user && !isPublicRoute) {
      // Not logged in → send to login
      router.replace("/login");
    } else if (user && isPublicRoute) {
      // Already logged in → send to dashboard
      router.replace("/");
    }
  }, [user, loading, pathname, router]);

  /* ── Auth Actions ── */

  const login = useCallback(async (email: string, password: string) => {
    await signInWithEmailAndPassword(auth, email, password);
    clearLocalUserData();
  }, []);

  const signup = useCallback(async (email: string, password: string) => {
    await createUserWithEmailAndPassword(auth, email, password);
    clearLocalUserData();
  }, []);

  const loginWithGoogle = useCallback(async () => {
    const result = await signInWithPopup(auth, googleProvider);
    clearLocalUserData();
    // Extract the OAuth access token to use for Google Calendar API
    const credential = GoogleAuthProvider.credentialFromResult(result);
    if (credential?.accessToken) {
      localStorage.setItem("google_access_token", credential.accessToken);
    }
  }, []);

  const logout = useCallback(async () => {
    await firebaseSignOut(auth);
    clearLocalUserData();
    router.replace("/login");
  }, [router]);

  const deleteAccount = useCallback(async () => {
    if (!user) return;
    try {
      await user.delete();
      clearLocalUserData();
      router.replace("/login");
    } catch (err: unknown) {
      const code = typeof err === "object" && err !== null && "code" in err
        ? String((err as { code?: unknown }).code)
        : "";
      if (code === "auth/requires-recent-login") {
        throw new Error("For security, please log out and log back in before deleting your account.");
      }
      throw err;
    }
  }, [user, router]);

  /* ── Loading Screen ── */
  if (loading) {
    return (
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          height: "100vh",
          background: "var(--bg-primary)",
        }}
      >
        <div
          style={{
            width: "36px",
            height: "36px",
            border: "3px solid var(--border-default)",
            borderTopColor: "var(--accent-teal)",
            borderRadius: "50%",
            animation: "spin 0.8s linear infinite",
          }}
        />
      </div>
    );
  }

  /* While redirecting, show nothing for protected pages */
  const isPublicRoute = PUBLIC_ROUTES.includes(pathname);
  if (!user && !isPublicRoute) return null;
  if (user && isPublicRoute) return null;

  return (
    <AuthContext.Provider
      value={{ user, loading, login, signup, loginWithGoogle, logout, deleteAccount }}
    >
      {children}
    </AuthContext.Provider>
  );
}
