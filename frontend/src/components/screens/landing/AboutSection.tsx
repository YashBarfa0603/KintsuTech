"use client";

import React, { useEffect, useRef, useState } from "react";
import { Icon } from "@/components/ui/Icons";

export function AboutSection() {
  const sectionRef = useRef<HTMLElement>(null);
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    const el = sectionRef.current;
    if (!el) return;

    // Check prefers-reduced-motion
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setIsVisible(true);
      return;
    }

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setIsVisible(true);
          observer.disconnect();
        }
      },
      { threshold: 0.25 }
    );

    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return (
    <section id="about" ref={sectionRef} className="editorial-about">
      <div className="container">
        <div className="about-workflow-landing-anchor" aria-hidden="true">
          <div className="about-landing-pip" />
        </div>

        <div className="editorial-about-grid">
          {/* Column 1: Copy with staggered entrance */}
          <div className={`about-copy-col ${isVisible ? "animate-in" : ""}`}>
            <span className="eyebrow">ABOUT KINTSUTECH</span>
            <h2>Where breaks become strength.</h2>
            <p className="about-lead">
              KintsuTech is a software resilience platform that helps developers detect external
              dependency changes, trace their impact, and validate compatibility repairs before
              approval. Inspired by{" "}
              <strong className="kintsugi-highlight">
                Kintsugi, the Japanese art of repairing broken pottery with gold
              </strong>
              , we believe that a break doesn&apos;t have to mean the end. Just as Kintsugi
              transforms cracks into part of an object&apos;s story, KintsuTech turns software
              failures into opportunities to build stronger, more reliable connections.
            </p>

            <div className="about-pillars">
              <div className="about-pillar-item">
                <span className="about-pillar-icon"><Icon name="shield" size={16} /></span>
                <div>
                  <strong>Preserve Contracts</strong>
                  <p>Safeguard internal consumer schemas without breaking client workflows.</p>
                </div>
              </div>
              <div className="about-pillar-item">
                <span className="about-pillar-icon"><Icon name="spark" size={16} /></span>
                <div>
                  <strong>Golden Seams</strong>
                  <p>Transform brittle integration points into explicit, observable adapters.</p>
                </div>
              </div>
            </div>
          </div>

          {/* Column 2: Ceramic bowl with branching Kintsugi gold seams */}
          <div className="about-illustration-col" aria-hidden="true">
            <div className={`kintsugi-ceramic-card ${isVisible ? "animate-gold" : ""}`}>
              {/* Subtle background nodes & circles matching hero */}
              <svg className="ceramic-bg-elements" viewBox="0 0 440 380" fill="none">
                <circle cx="220" cy="190" r="170" stroke="rgba(200, 150, 36, 0.12)" strokeWidth="1" strokeDasharray="4 6" />
                <circle cx="220" cy="190" r="130" stroke="rgba(12, 54, 48, 0.06)" strokeWidth="1" />
                <circle cx="65" cy="85" r="4" fill="rgba(200, 150, 36, 0.35)" />
                <circle cx="375" cy="85" r="4" fill="rgba(200, 150, 36, 0.35)" />
                <circle cx="65" cy="295" r="4" fill="rgba(200, 150, 36, 0.35)" />
                <circle cx="375" cy="295" r="4" fill="rgba(200, 150, 36, 0.35)" />
                <line x1="65" y1="85" x2="375" y2="85" stroke="rgba(200, 150, 36, 0.08)" strokeWidth="1" />
                <line x1="65" y1="295" x2="375" y2="295" stroke="rgba(200, 150, 36, 0.08)" strokeWidth="1" />
              </svg>

              <svg
                className="ceramic-bowl-svg"
                viewBox="0 0 360 300"
                fill="none"
                xmlns="http://www.w3.org/2000/svg"
              >
                <defs>
                  {/* Subtle Ceramic Glaze Gradient */}
                  <linearGradient id="ceramicGlaze" x1="60" y1="50" x2="300" y2="260" gradientUnits="userSpaceOnUse">
                    <stop stopColor="#ffffff" />
                    <stop offset="0.45" stopColor="#f4f1ea" />
                    <stop offset="0.85" stopColor="#e8e2d5" />
                    <stop offset="1" stopColor="#ded5c4" />
                  </linearGradient>

                  {/* Kintsugi Gold Gradient */}
                  <linearGradient id="kintsugiGold" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" stopColor="#ffd875" />
                    <stop offset="35%" stopColor="#e0a328" />
                    <stop offset="70%" stopColor="#c28b24" />
                    <stop offset="100%" stopColor="#fff0a0" />
                  </linearGradient>

                  {/* Gold Glow Filter */}
                  <filter id="goldGlow" x="-20%" y="-20%" width="140%" height="140%">
                    <feDropShadow dx="0" dy="0" stdDeviation="3" floodColor="#e0a328" floodOpacity="0.65" />
                  </filter>
                </defs>

                {/* Bowl Silhouette (Traditional Chawan form) */}
                <path
                  d="M 50 110 C 50 205, 110 240, 180 240 C 250 240, 310 205, 310 110 C 310 95, 50 95, 50 110 Z"
                  fill="url(#ceramicGlaze)"
                  stroke="#dcd5c7"
                  strokeWidth="2"
                />

                {/* Foot ring of the bowl */}
                <path
                  d="M 130 240 L 132 254 C 132 258, 228 258, 228 254 L 230 240"
                  fill="#d8cebc"
                  stroke="#c5baaa"
                  strokeWidth="1.5"
                />

                {/* Rim highlight */}
                <ellipse cx="180" cy="110" rx="130" ry="24" fill="none" stroke="#ede7dc" strokeWidth="2.5" />

                {/* Subtle crack hair-lines (underlay) */}
                <g className="base-crack-lines" stroke="rgba(80, 70, 60, 0.25)" strokeWidth="1.2" strokeLinecap="round">
                  <path d="M 80 110 Q 110 150 145 175 T 180 238" />
                  <path d="M 145 175 Q 185 160 215 170 T 260 190" />
                  <path d="M 215 170 Q 235 135 255 120 T 290 112" />
                  <path d="M 125 155 Q 110 180 100 200" />
                </g>

                {/* Golden Kintsugi Seams (Draw-on animated path) */}
                <g className="gold-seam-lines" stroke="url(#kintsugiGold)" strokeWidth="3.2" strokeLinecap="round" strokeLinejoin="round" filter="url(#goldGlow)">
                  {/* Primary Fault Line */}
                  <path
                    className="gold-seam-path path-1"
                    d="M 80 110 Q 110 150 145 175 T 180 238"
                  />
                  {/* Branch 1 */}
                  <path
                    className="gold-seam-path path-2"
                    d="M 145 175 Q 185 160 215 170 T 260 190"
                  />
                  {/* Branch 2 towards rim */}
                  <path
                    className="gold-seam-path path-3"
                    d="M 215 170 Q 235 135 255 120 T 290 112"
                  />
                  {/* Subsidiary hair branch */}
                  <path
                    className="gold-seam-path path-4"
                    d="M 125 155 Q 110 180 100 200"
                  />
                </g>

                {/* Golden gold nodes at connection points */}
                <circle className="gold-joint node-1" cx="145" cy="175" r="4.5" fill="#ffd875" stroke="#c28b24" strokeWidth="1.5" />
                <circle className="gold-joint node-2" cx="215" cy="170" r="3.8" fill="#ffd875" stroke="#c28b24" strokeWidth="1.5" />
                <circle className="gold-joint node-3" cx="180" cy="238" r="3.5" fill="#ffd875" stroke="#c28b24" strokeWidth="1.5" />
                <circle className="gold-joint node-4" cx="80" cy="110" r="3.5" fill="#ffd875" stroke="#c28b24" strokeWidth="1.5" />
              </svg>

              <div className="ceramic-caption">
                <span className="caption-gold-pill">
                  <span className="shimmer-dot" /> Kintsugi Repair
                </span>
                <small>Failures converted into structural integrity</small>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
