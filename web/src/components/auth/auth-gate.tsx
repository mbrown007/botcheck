"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import type { Route } from "next";
import { ensureFreshAuthSession } from "@/lib/auth";

interface AuthGateProps {
  children: React.ReactNode;
}

export function AuthGate({ children }: AuthGateProps) {
  const router = useRouter();
  const [checking, setChecking] = useState(true);
  const [allowed, setAllowed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function checkSession() {
      try {
        const session = await ensureFreshAuthSession();
        if (cancelled) {
          return;
        }
        if (!session?.token) {
          router.replace("/login" as Route);
          return;
        }
        setAllowed(true);
      } catch {
        if (cancelled) {
          return;
        }
        // Refresh failed (network error etc.) — treat as unauthenticated.
        router.replace("/login" as Route);
      } finally {
        if (!cancelled) {
          setChecking(false);
        }
      }
    }
    void checkSession();
    return () => {
      cancelled = true;
    };
  }, [router]);

  if (checking) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-bg-base text-sm text-text-muted">
        Loading session…
      </div>
    );
  }

  if (!allowed) {
    return null;
  }

  return <>{children}</>;
}
