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

// Auth context interface exposed to the rest of the application.
interface AuthContextValue {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (email: string, password: string) => Promise<void>;
  loginWithGoogle: () => Promise<void>;
  logout: () => Promise<void>;
  deleteAccount: () => Promise<void>;
}

// Default auth context used until the provider hydrates the real value.
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

// Routes that do not require authentication.
const PUBLIC_ROUTES = ["/login"];

const clearLocalUserData = () => {
  if (typeof window === "undefined") return;
  localStorage.removeItem("google_access_token");
  Object.keys(localStorage).forEach((key) => {
    if (key.startsWith("statementsense.")) {
      localStorage.removeItem(key);
    }
  });
  clearSubscriptionSession();
  clearAllPageSessions();
  clearUserPreferences();
};

// Provider component that exposes authentication state and actions to its descendants.
export default function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const pathname = usePathname();
  const router = useRouter();

  // Mirror Firebase's auth state into local state and clear the loading flag once it has been observed.
  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, (firebaseUser) => {
      setUser(firebaseUser);
      setLoading(false);
    });
    return () => unsubscribe();
  }, []);

  // Route guard: redirect unauthenticated users to the login page and authenticated users away from it.
  useEffect(() => {
    if (loading) return;

    const isPublicRoute = PUBLIC_ROUTES.includes(pathname);

    if (!user && !isPublicRoute) {
      router.replace("/login");
    } else if (user && isPublicRoute) {
      router.replace("/");
    }
  }, [user, loading, pathname, router]);

  // Authentication actions exposed through the context.

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
    // Persist the OAuth access token so CalendarSense can call the Google Calendar API on the user's behalf.
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

  // Render a centred loading indicator until Firebase has reported the initial auth state.
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

  // While the router is redirecting between protected and public routes, render nothing to avoid flashing the previous page.
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
