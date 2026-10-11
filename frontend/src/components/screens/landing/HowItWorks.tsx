"use client";

import React, { useState } from "react";
import { Icon } from "@/components/ui/Icons";
import { IconName } from "@/types";

interface StepData {
  num: string;
  icon: IconName;
  title: string;
  description: string;
  detail: string;
}

const steps: StepData[] = [
  {
    num: "01",
    icon: "alert",
    title: "Detect",
    description: "Compare observed dependency behaviour with the saved baseline.",
    detail: "Real-time diffing of payload shapes, status codes, and latency distributions against verified baselines.",
  },
  {
    num: "02",
    icon: "graph",
    title: "Trace & Repair",
    description: "Follow known impact paths and prepare a controlled proposal.",
    detail: "Identifies upstream workflows, assesses blast radius, and synthesizes a non-destructive adapter.",
  },
  {
    num: "03",
    icon: "test",
    title: "Validate",
    description: "Run independent checks before developer review.",
    detail: "Deterministic compatibility matrix checks, type assertions, and isolated regression tests.",
  },
];

export function HowItWorks() {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);

  return (
    <section id="how" className="editorial-how">
      <div className="container">
        <div className="section-heading">
          <span>HOW IT WORKS</span>
          <h2>Evidence before action.</h2>
        </div>

        <div
          className={`editorial-steps ${hoveredIndex !== null ? "has-hovered" : ""}`}
          onMouseLeave={() => setHoveredIndex(null)}
        >
          {steps.map((step, index) => {
            const isHovered = hoveredIndex === index;
            const isDimmed = hoveredIndex !== null && !isHovered;

            return (
              <article
                key={step.title}
                tabIndex={0}
                className={`step-card ${isHovered ? "is-active" : ""} ${
                  isDimmed ? "is-dimmed" : ""
                }`}
                onMouseEnter={() => setHoveredIndex(index)}
                onFocus={() => setHoveredIndex(index)}
                onBlur={() => setHoveredIndex(null)}
                onTouchStart={() => setHoveredIndex(index)}
              >
                <div className="step-card-header">
                  <span className="step-num">{step.num}</span>
                  <div className="step-icon-wrap">
                    <Icon name={step.icon} size={22} />
                  </div>
                </div>

                <h3>{step.title}</h3>
                <p>{step.description}</p>

                {/* Extra line of detail text revealed on hover */}
                <div className="step-detail-revealed">
                  <span className="gold-accent-dash" />
                  <small>{step.detail}</small>
                </div>
              </article>
            );
          })}
        </div>
      </div>
    </section>
  );
}
