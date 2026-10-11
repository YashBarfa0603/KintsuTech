"use client";

import React, { useState, useEffect } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { LandingScreen } from "@/components/screens/LandingScreen";
import { AuthScreen } from "@/components/screens/AuthScreen";
import { Screen } from "@/types";
import { supabase, isSupabaseConfigured } from "@/lib/supabase";

export default function Home() {
  const [view, setView] = useState<"app" | "landing" | "auth">("landing");
  const [authMode, setAuthMode] = useState<"signin" | "signup">("signin");
  const [screen, setScreen] = useState<Screen>("projects");
  const [isAuthenticated, setIsAuthenticated] = useState(false);

  useEffect(() => {
    if (!isSupabaseConfigured()) return;

    // Check initial active session
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (session) {
        setIsAuthenticated(true);
      }
    });

    // Listen for auth state changes (e.g. OAuth callback, token refresh, sign in / sign out)
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((event, session) => {
      if (session) {
        setIsAuthenticated(true);
        if (event === "SIGNED_IN") {
          // If returning from an OAuth callback or confirmation link, enter the app
          setView("app");
        }
      } else {
        setIsAuthenticated(false);
      }
    });

    return () => {
      subscription.unsubscribe();
    };
  }, []);

  if (view === "auth") {
    return (
      <AuthScreen
        initialMode={authMode}
        onSuccess={() => {
          setIsAuthenticated(true);
          setView("app");
        }}
        onBack={() => setView("landing")}
      />
    );
  }

  if (view === "landing") {
    return (
      <LandingScreen
        onEnter={(targetScreen?: Screen) => {
          if (targetScreen) setScreen(targetScreen);
          setView("app");
        }}
        onOpenAuth={(mode) => {
          setAuthMode(mode);
          setView("auth");
        }}
        isAuthenticated={isAuthenticated}
      />
    );
  }

  return (
    <AppShell
      initialScreen={screen}
      onNavigateHome={() => setView("landing")}
    />
  );
}
