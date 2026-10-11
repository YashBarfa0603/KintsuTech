"use client";

import React from "react";
import { Icon } from "@/components/ui/Icons";

interface WorkflowStepperProps {
  progress: number;
  stage: number;
}

export function WorkflowStepper({ progress, stage }: WorkflowStepperProps) {
  const steps = [
    { id: 0, label: "Connected", desc: "Baseline contract healthy" },
    { id: 1, label: "Change detected", desc: "Response shape diverged" },
    { id: 2, label: "Validation running", desc: "Independent checks" },
    { id: 3, label: "Validated · reconnected", desc: "Ready for review" },
  ];

  // progress is 0..1
  const fillPercent = Math.min(100, Math.max(0, progress * 100));

  return (
    <div className="horizontal-workflow-stepper" aria-label="Kintsugi recovery workflow progress">
      <div className="workflow-track">
        {/* Base line */}
        <div className="workflow-track-base" />

        {/* Crack break effect at stage 1 position (around 33%) */}
        <div className={`workflow-track-crack ${progress >= 0.25 ? "cracked" : ""}`} />

        {/* Kintsugi Gold Fill line */}
        <div
          className="workflow-track-gold"
          style={{ width: `${fillPercent}%` }}
        >
          <span className="gold-spark" />
        </div>
      </div>

      <div className="workflow-nodes">
        {steps.map((step, index) => {
          const stepProgress = index / 3;
          const isReached = progress >= stepProgress || stage >= index;
          const isCurrent = stage === index;

          return (
            <div
              key={step.id}
              className={`workflow-node-item ${
                isReached ? "reached" : ""
              } ${isCurrent ? "current" : ""}`}
            >
              <div className="workflow-node-bullet">
                {isReached && index < stage ? (
                  <Icon name="check" size={13} />
                ) : (
                  <span>{index + 1}</span>
                )}
              </div>
              <div className="workflow-node-text">
                <strong>{step.label}</strong>
                <small>{step.desc}</small>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
