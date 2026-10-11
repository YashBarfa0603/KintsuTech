"use client";

import React, { useState } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { LandingScreen } from "@/components/screens/LandingScreen";
import { Screen } from "@/types";

export default function Home() {
  const [view, setView] = useState<"app" | "landing">("app");
  const [screen] = useState<Screen>("projects");

  if (view === "landing") {
    return <LandingScreen onEnter={() => setView("app")} />;
  }

  return <AppShell initialScreen={screen} onNavigateHome={() => setView("landing")} />;
}
