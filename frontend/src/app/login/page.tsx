"use client";

import { useState, useCallback } from "react";
import { useAuth } from "@/components/AuthProvider";
import { SignInPage } from "@/components/sign-in";

function friendlyError(code: string): string {
  const map: Record<string, string> = {
    "auth/invalid-email": "Please enter a valid email address.",
    "auth/user-disabled": "This account has been disabled.",
    "auth/user-not-found": "No account found with this email.",
    "auth/wrong-password": "Incorrect password. Please try again.",
    "auth/invalid-credential": "Invalid email or password.",
    "auth/email-already-in-use": "An account with this email already exists.",
    "auth/weak-password": "Password must be at least 6 characters.",
    "auth/too-many-requests": "Too many attempts. Please wait a moment.",
    "auth/popup-closed-by-user": "Google sign-in was cancelled.",
    "auth/network-request-failed": "Network error. Check your connection.",
  };
  return map[code] || `Something went wrong. (${code || "Unknown error"})`;
}

export default function LoginPage() {
  const { login, signup, loginWithGoogle } = useAuth();
  const [error, setError] = useState("");
  const [mode, setMode] = useState<"login" | "signup">("login");

  const handleSignIn = useCallback(
    async (e: React.FormEvent<HTMLFormElement>) => {
      e.preventDefault();
      setError("");
      const formData = new FormData(e.currentTarget);
      const email = formData.get("email") as string;
      const password = formData.get("password") as string;

      if (!email?.trim() || !password?.trim()) {
        setError("Please fill in all fields.");
        return;
      }

      try {
        if (mode === "login") {
          await login(email, password);
        } else {
          await signup(email, password);
        }
      } catch (err: unknown) {
        const firebaseErr = err as { code?: string };
        setError(friendlyError(firebaseErr.code || ""));
      }
    },
    [mode, login, signup]
  );

  const handleGoogleSignIn = useCallback(async () => {
    setError("");
    try {
      await loginWithGoogle();
    } catch (err: unknown) {
      const firebaseErr = err as { code?: string };
      setError(friendlyError(firebaseErr.code || ""));
    }
  }, [loginWithGoogle]);

  return (
    <div className="signin-page">
      {error && (
        <div
          style={{
            position: "fixed",
            top: "1rem",
            left: "50%",
            transform: "translateX(-50%)",
            zIndex: 9999,
            background: "#fef2f2",
            border: "1px solid #fecaca",
            color: "#dc2626",
            padding: "0.75rem 1.5rem",
            borderRadius: "12px",
            fontSize: "0.875rem",
            maxWidth: "400px",
            textAlign: "center",
            boxShadow: "0 4px 12px rgba(0,0,0,0.1)",
          }}
        >
          {error}
        </div>
      )}
      <SignInPage
        heroImageSrc="/bank.jpg"
        testimonials={[
          {
            avatarSrc: "https://i.pravatar.cc/80?img=47",
            name: "Sarah Chen",
            handle: "@sarahdigital",
            text: "Amazing platform! The user experience is seamless and the features are exactly what I needed.",
          },
          {
            avatarSrc: "https://i.pravatar.cc/80?img=68",
            name: "Marcus Johnson",
            handle: "@marcustech",
            text: "This service has transformed how I work. Clean design, powerful features, and excellent support.",
          },
        ]}
        title={
          <span className="font-light text-foreground tracking-tighter">
            {mode === "login" ? "Welcome" : "Create Account"}
          </span>
        }
        description={
          mode === "login"
            ? "Access your account and continue your journey with us"
            : "Sign up to get started with StatementSense"
        }
        onSignIn={handleSignIn}
        onGoogleSignIn={handleGoogleSignIn}
        onResetPassword={() => {
          // TODO: implement password reset
          alert("Password reset coming soon!");
        }}
        onCreateAccount={() => {
          setMode(mode === "login" ? "signup" : "login");
          setError("");
        }}
      />
    </div>
  );
}
