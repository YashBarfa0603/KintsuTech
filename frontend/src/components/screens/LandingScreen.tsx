"use client";

import React, { useState, useEffect } from "react";
import { Button, Badge } from "@/components/ui/Primitives";
import { Icon, Logo } from "@/components/ui/Icons";

export function LandingScreen({ onEnter }: { onEnter: () => void }) {
  const [heroStage, setHeroStage] = useState(0);
  const [heroPlaying, setHeroPlaying] = useState(false);

  useEffect(() => {
    if (!heroPlaying) return;
    const timer = window.setTimeout(() => {
      setHeroStage((s) => {
        if (s >= 2) {
          setHeroPlaying(false);
          return 3;
        }
        return s + 1;
      });
    }, 900);
    return () => window.clearTimeout(timer);
  }, [heroPlaying]);

  return (
    <main className="min-h-screen bg-[#FAF8F5] text-stone-900">
      {/* Top Nav */}
      <nav className="border-b border-stone-200 bg-white/80 backdrop-blur sticky top-0 z-30">
        <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
          <Logo />
          <div className="flex items-center gap-6 text-sm font-semibold text-stone-600">
            <a href="#how" className="hover:text-stone-900">How It Works</a>
            <a href="#how" className="hover:text-stone-900">Architecture</a>
          </div>
          <div className="flex items-center gap-3">
            <Button variant="secondary" onClick={onEnter}>Sign In</Button>
            <Button variant="primary" onClick={onEnter}>Explore Workspace</Button>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="max-w-6xl mx-auto px-6 py-20 grid grid-cols-2 gap-12 items-center">
        <div>
          <span className="text-xs font-bold tracking-widest text-amber-700 uppercase">
            RESILIENCE, BY DESIGN
          </span>
          <h1 className="text-5xl font-extrabold tracking-tight text-stone-950 mt-3 mb-6 leading-tight">
            When APIs break,<br />
            <em className="text-emerald-800 font-serif italic">connections heal.</em>
          </h1>
          <p className="text-base text-stone-600 mb-8 leading-relaxed">
            Detect external dependency changes, trace their impact across your workflows, and prove
            deterministic compatibility repairs before activation.
          </p>
          <div className="flex items-center gap-4">
            <Button variant="primary" icon="arrow" onClick={onEnter}>
              Open KintsuTech Console
            </Button>
            <Button
              variant="secondary"
              icon="play"
              onClick={() => {
                setHeroStage(0);
                setHeroPlaying(true);
              }}
            >
              Watch simulated recovery
            </Button>
          </div>
        </div>

        {/* Animated Visual Card */}
        <div className="p-6 bg-white border border-stone-200 rounded-lg shadow-sm">
          <div className="flex items-center justify-between pb-4 border-b border-stone-100 mb-6">
            <span className="text-xs font-bold text-stone-500 uppercase">SIMULATED RECOVERY PATH</span>
            <Badge tone={heroStage === 3 ? "success" : heroStage === 2 ? "gold" : heroStage === 1 ? "danger" : "neutral"}>
              {heroStage === 0
                ? "Connected"
                : heroStage === 1
                ? "Change detected"
                : heroStage === 2
                ? "Validation running"
                : "Validated · Reconnected"}
            </Badge>
          </div>

          <div className="flex items-center justify-between px-4 py-8 bg-stone-50 rounded border border-stone-100 mb-4">
            <div className="text-center">
              <span className="w-10 h-10 rounded bg-blue-100 text-blue-700 flex items-center justify-center mx-auto mb-2">
                <Icon name="home" size={18} />
              </span>
              <strong className="text-xs block text-stone-800">Checkout App</strong>
            </div>

            <div className="flex-1 px-4 text-center">
              <div className="h-0.5 bg-stone-300 relative my-2">
                <span
                  className={`absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-4 h-4 rounded-full flex items-center justify-center text-[10px] ${
                    heroStage === 3 ? "bg-emerald-600 text-white" : heroStage >= 1 ? "bg-red-500 text-white" : "bg-stone-500 text-white"
                  }`}
                >
                  {heroStage === 3 ? "✓" : heroStage >= 1 ? "!" : "→"}
                </span>
              </div>
            </div>

            <div className="text-center">
              <span className="w-10 h-10 rounded bg-amber-100 text-amber-700 flex items-center justify-center mx-auto mb-2">
                <Icon name="api" size={18} />
              </span>
              <strong className="text-xs block text-stone-800">Payments API</strong>
            </div>
          </div>

          <div className="p-3 bg-stone-900 text-stone-100 font-mono text-xs rounded">
            <code>
              {heroStage < 1 ? '"name": "Annual Pro Plan"' : '"display_name": "Annual Pro Plan"'}
            </code>
            <div className="text-stone-400 font-sans text-[11px] mt-1">
              {heroStage === 0
                ? "Baseline observed and locked."
                : heroStage === 1
                ? "Divergence detected: response field replaced."
                : heroStage === 2
                ? "14 isolated sandbox checks executing."
                : "Deterministic verification passed. Ready for approval."}
            </div>
          </div>
        </div>
      </section>

      {/* How it Works */}
      <section id="how" className="max-w-6xl mx-auto px-6 py-16 border-t border-stone-200">
        <div className="text-center mb-12">
          <span className="text-xs font-bold text-amber-700 tracking-wider uppercase">HOW IT WORKS</span>
          <h2 className="text-3xl font-extrabold text-stone-950 mt-1">Evidence before action.</h2>
        </div>
        <div className="grid grid-cols-3 gap-8">
          <div className="p-6 bg-white border border-stone-200 rounded-md">
            <span className="text-xs font-bold text-stone-400 block mb-2">01</span>
            <Icon name="alert" size={24} className="text-amber-600 mb-3" />
            <h3 className="font-bold text-base text-stone-900 mb-1">Detect</h3>
            <p className="text-sm text-stone-600">
              Continuously compare observed API and dependency behavior with verified baselines.
            </p>
          </div>
          <div className="p-6 bg-white border border-stone-200 rounded-md">
            <span className="text-xs font-bold text-stone-400 block mb-2">02</span>
            <Icon name="graph" size={24} className="text-blue-600 mb-3" />
            <h3 className="font-bold text-base text-stone-900 mb-1">Trace & Repair</h3>
            <p className="text-sm text-stone-600">
              Trace confirmed impact paths through the AI Dependency Graph and prepare an isolated proposal.
            </p>
          </div>
          <div className="p-6 bg-white border border-stone-200 rounded-md">
            <span className="text-xs font-bold text-stone-400 block mb-2">03</span>
            <Icon name="test" size={24} className="text-emerald-600 mb-3" />
            <h3 className="font-bold text-base text-stone-900 mb-1">Validate</h3>
            <p className="text-sm text-stone-600">
              Run independent deterministic checks in a sandbox before requiring human engineering review.
            </p>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-stone-200 py-10 bg-white">
        <div className="max-w-6xl mx-auto px-6 flex items-center justify-between text-xs text-stone-500">
          <Logo />
          <div>© {new Date().getFullYear()} KintsuTech. Detect. Adapt. Recover.</div>
        </div>
      </footer>
    </main>
  );
}
