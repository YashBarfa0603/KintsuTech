"use client";

import React, { useEffect, useRef, useState, useCallback } from "react";
import { Button, Badge } from "@/components/ui/Primitives";
import { Icon, Logo } from "@/components/ui/Icons";
import { Screen } from "@/types";
import { WorkflowStepper } from "./landing/WorkflowStepper";
import { AboutSection } from "./landing/AboutSection";
import { HowItWorks } from "./landing/HowItWorks";
import { InteractiveDemo } from "./landing/InteractiveDemo";
import "./landing/landing.css";

interface LandingScreenProps {
  onEnter: (screen?: Screen) => void;
  onOpenAuth?: (mode: "signin" | "signup") => void;
  isAuthenticated?: boolean;
}

export function LandingScreen({ onEnter, onOpenAuth, isAuthenticated = false }: LandingScreenProps) {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const mobileMenuRef = useRef<HTMLDivElement>(null);

  // Scroll-driven horizontal recovery workflow state
  const heroRef = useRef<HTMLElement>(null);
  const [scrollProgress, setScrollProgress] = useState(0);
  const [heroStage, setHeroStage] = useState(0);

  const scrollTo = (id: string) => {
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth" });
  };

  const closeMenuAnd = (action: () => void) => {
    setMobileMenuOpen(false);
    action();
  };

  const handleSignIn = () => {
    if (isAuthenticated) {
      onEnter("overview");
    } else if (onOpenAuth) {
      onOpenAuth("signin");
    } else {
      onEnter("overview");
    }
  };

  const handleSignUp = () => {
    if (isAuthenticated) {
      onEnter("projects");
    } else if (onOpenAuth) {
      onOpenAuth("signup");
    } else {
      onEnter("projects");
    }
  };

  // Scroll listener for hero recovery workflow progress
  const handleScroll = useCallback(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setHeroStage(3);
      setScrollProgress(1);
      return;
    }

    const heroEl = heroRef.current;
    const aboutEl = document.getElementById("about");
    if (!heroEl || !aboutEl) return;

    const aboutRect = aboutEl.getBoundingClientRect();
    const viewportHeight = window.innerHeight;

    // progress = 0 at top of hero (window.scrollY === 0)
    // progress = 1 when vertical middle of About section reaches the middle of viewport
    const aboutMiddle = aboutRect.top + aboutRect.height / 2;
    const viewportMiddle = viewportHeight / 2;

    const startY = 0;
    const currentY = window.scrollY;
    const targetY = currentY + (aboutMiddle - viewportMiddle);

    if (targetY <= startY) {
      setScrollProgress(1);
      setHeroStage(3);
      return;
    }

    const rawProgress = (currentY - startY) / (targetY - startY);
    const clampedProgress = Math.min(1, Math.max(0, rawProgress));

    setScrollProgress(clampedProgress);

    // Derive heroStage: 0-0.25 -> 0, 0.25-0.5 -> 1, 0.5-0.75 -> 2, 0.75-1 -> 3
    let stage = 0;
    if (clampedProgress >= 0.75) stage = 3;
    else if (clampedProgress >= 0.5) stage = 2;
    else if (clampedProgress >= 0.25) stage = 1;
    else stage = 0;

    setHeroStage(stage);
  }, []);

  useEffect(() => {
    let ticking = false;
    const onScroll = () => {
      if (!ticking) {
        window.requestAnimationFrame(() => {
          handleScroll();
          ticking = false;
        });
        ticking = true;
      }
    };

    window.addEventListener("scroll", onScroll, { passive: true });
    handleScroll();

    return () => window.removeEventListener("scroll", onScroll);
  }, [handleScroll]);

  // Mobile menu keyboard & backdrop listeners
  useEffect(() => {
    if (!mobileMenuOpen) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const close = () => setMobileMenuOpen(false);
    const onKeyDown = (event: KeyboardEvent) => event.key === "Escape" && close();
    const onPointerDown = (event: PointerEvent) => {
      if (
        !mobileMenuRef.current?.contains(event.target as Node) &&
        !menuButtonRef.current?.contains(event.target as Node)
      ) {
        close();
      }
    };

    document.addEventListener("keydown", onKeyDown);
    document.addEventListener("pointerdown", onPointerDown);
    window.setTimeout(
      () => mobileMenuRef.current?.querySelector<HTMLButtonElement>("button")?.focus(),
      0
    );

    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", onKeyDown);
      document.removeEventListener("pointerdown", onPointerDown);
      window.setTimeout(() => menuButtonRef.current?.focus(), 0);
    };
  }, [mobileMenuOpen]);

  const watchRecovery = () => {
    scrollTo("about");
  };

  return (
    <main className="landing editorial-landing">
      {/* Navigation */}
      <nav className="landing-nav editorial-nav">
        <div className="container landing-nav-inner">
          <Button
            variant="ghost"
            className="landing-logo-button"
            onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}
            ariaLabel="KintsuTech home"
          >
            <Logo />
          </Button>

          <div className="landing-links">
            <Button variant="ghost" onClick={() => scrollTo("product")}>
              Product
            </Button>
            <Button variant="ghost" onClick={() => scrollTo("about")}>
              About KintsuTech
            </Button>
            <Button variant="ghost" onClick={() => scrollTo("how")}>
              How It Works
            </Button>
            <Button variant="ghost" onClick={() => scrollTo("features")}>
              Features
            </Button>
          </div>

          <div className="nav-actions">
            <Button variant="secondary" onClick={() => onEnter("overview")}>
              Enter Workspace
            </Button>
            <Button variant="ghost" onClick={handleSignIn}>
              Sign In
            </Button>
            <Button onClick={handleSignUp}>
              Get Started
            </Button>
          </div>

          <button
            ref={menuButtonRef}
            className="landing-menu-button"
            onClick={() => setMobileMenuOpen((open) => !open)}
            aria-label={mobileMenuOpen ? "Close navigation" : "Open navigation"}
            aria-expanded={mobileMenuOpen}
          >
            <Icon name={mobileMenuOpen ? "close" : "menu"} />
          </button>
        </div>
      </nav>

      {/* Mobile Drawer Menu */}
      {mobileMenuOpen && (
        <div className="landing-menu-scrim">
          <div
            ref={mobileMenuRef}
            className="landing-mobile-menu"
            role="dialog"
            aria-modal="true"
            aria-label="Navigation"
          >
            <Button variant="ghost" onClick={() => closeMenuAnd(() => scrollTo("product"))}>
              Product
            </Button>
            <Button variant="ghost" onClick={() => closeMenuAnd(() => scrollTo("about"))}>
              About KintsuTech
            </Button>
            <Button variant="ghost" onClick={() => closeMenuAnd(() => scrollTo("how"))}>
              How It Works
            </Button>
            <Button variant="ghost" onClick={() => closeMenuAnd(() => scrollTo("features"))}>
              Features
            </Button>
            <Button variant="secondary" onClick={() => closeMenuAnd(handleSignIn)}>
              Sign In
            </Button>
            <Button onClick={() => closeMenuAnd(handleSignUp)}>
              Get Started
            </Button>
          </div>
        </div>
      )}

      {/* Hero Section (#product) */}
      <section id="product" ref={heroRef} className="editorial-hero">
        <div className="container editorial-hero-grid">
          <div className="editorial-hero-copy">
            <span className="eyebrow">RESILIENCE, BY DESIGN</span>
            <h1>
              When APIs break,<br />
              <em>connections heal.</em>
            </h1>
            <p>
              Detect external dependency changes, trace their impact, and prove compatibility repairs before applying them.
            </p>
            <div className="hero-actions">
              <Button onClick={() => onEnter("overview")} icon="arrow">
                Explore KintsuTech
              </Button>
              <Button variant="secondary" icon="graph" onClick={() => onEnter("graph")}>
                AI Dependency Graph
              </Button>
            </div>
          </div>

          <div
            className={`connection-illustration stage-${heroStage}`}
            aria-label="Simulated application and API recovery illustration"
          >
            <div className="connection-caption">
              <span>SIMULATED RECOVERY PATH</span>
              <Badge
                tone={
                  heroStage === 3
                    ? "success"
                    : heroStage === 2
                    ? "gold"
                    : heroStage === 1
                    ? "danger"
                    : "neutral"
                }
              >
                {heroStage === 0
                  ? "Connected"
                  : heroStage === 1
                  ? "Change detected"
                  : heroStage === 2
                  ? "Validation running"
                  : "Validated · reconnected"}
              </Badge>
            </div>

            <div className="connection-scene">
              <div className="connection-node application">
                <span>
                  <Icon name="home" />
                </span>
                <small>APPLICATION</small>
                <strong>Checkout</strong>
              </div>
              <div className="connection-path">
                <span className="path-base" />
                <span className="path-break" />
                <span className="path-gold" />
                <Icon
                  name={
                    heroStage === 3 ? "check" : heroStage >= 1 ? "alert" : "arrow"
                  }
                />
              </div>
              <div className="connection-node api">
                <span>
                  <Icon name="api" />
                </span>
                <small>EXTERNAL API</small>
                <strong>Payments</strong>
              </div>
            </div>

            <div className="connection-evidence">
              <code>
                {heroStage < 1
                  ? '"name": "Annual Plan"'
                  : '"display_name": "Annual Plan"'}
              </code>
              <span>
                {heroStage === 0
                  ? "Baseline observed"
                  : heroStage === 1
                  ? "Response shape changed"
                  : heroStage === 2
                  ? "14 deterministic checks running"
                  : "Tests passed · awaiting review"}
              </span>
            </div>

            <div className="hero-scroll-workflow-anchor">
              <WorkflowStepper progress={scrollProgress} stage={heroStage} />
            </div>
          </div>
        </div>
      </section>

      {/* About Section (#about) */}
      <AboutSection />

      {/* How It Works Section (#how) */}
      <HowItWorks />

      {/* Interactive Demonstration (#features) */}
      <InteractiveDemo />

      {/* Final CTA & Footer */}
      <section className="editorial-final">
        <div className="container">
          <div className="editorial-final-content">
            <span className="eyebrow">KINTSUTECH</span>
            <h2>Make your integrations resilient.</h2>
            <p>Understand changes before they become failures.</p>
            <div className="hero-actions hero-actions-single">
              <Button onClick={handleSignUp} icon="arrow">
                Get Started
              </Button>
            </div>
          </div>

          <footer>
            <Logo />
            <span>© 2026 KintsuTech · Demonstration application</span>
            <Button variant="ghost" onClick={() => onEnter("settings")}>
              Platform Settings
            </Button>
          </footer>
        </div>
      </section>
    </main>
  );
}
