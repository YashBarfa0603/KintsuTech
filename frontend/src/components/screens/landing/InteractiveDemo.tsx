"use client";

import React, { useEffect, useRef, useState } from "react";
import { Button, Badge } from "@/components/ui/Primitives";
import { Icon } from "@/components/ui/Icons";

export function InteractiveDemo() {
  const sectionRef = useRef<HTMLElement>(null);
  const [demoStage, setDemoStage] = useState(0);
  const [demoPlaying, setDemoPlaying] = useState(false);
  const [buttonPressed, setButtonPressed] = useState(false);
  const hasAutoRunRef = useRef(false);

  // Auto-run on scroll when section enters view
  useEffect(() => {
    const el = sectionRef.current;
    if (!el) return;

    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setDemoStage(4);
      return;
    }

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting && !hasAutoRunRef.current) {
          hasAutoRunRef.current = true;
          // Simulate the button being invoked (pressed look briefly)
          setButtonPressed(true);
          const pressTimer = window.setTimeout(() => {
            setButtonPressed(false);
            setDemoStage(0);
            setDemoPlaying(true);
          }, 350);

          observer.disconnect();

          return () => window.clearTimeout(pressTimer);
        }
      },
      { threshold: 0.45 }
    );

    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  // Step through stages 0 -> 4 every 700ms
  useEffect(() => {
    if (!demoPlaying) return;
    if (demoStage >= 4) {
      setDemoPlaying(false);
      return;
    }
    const timer = window.setTimeout(() => {
      setDemoStage((stage) => stage + 1);
    }, 700);

    return () => window.clearTimeout(timer);
  }, [demoPlaying, demoStage]);

  const playDemo = () => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setDemoStage(4);
      return;
    }
    setDemoStage(0);
    setDemoPlaying(true);
  };

  const resetDemo = () => {
    setDemoPlaying(false);
    setDemoStage(0);
  };

  return (
    <section id="features" ref={sectionRef} className="editorial-demo">
      <div className="container editorial-demo-grid">
        <div className="editorial-demo-copy">
          <span className="eyebrow">INTERACTIVE DEMONSTRATION</span>
          <h2>A proposal is not proof.</h2>
          <p>
            A simulated response field changes from <code>temperature</code> to{" "}
            <code>temp_c</code>. The proposal remains unapproved until independent checks pass.
          </p>
          <div className="hero-actions">
            <Button
              onClick={playDemo}
              icon="play"
              className={buttonPressed ? "btn-simulated-press" : ""}
            >
              {demoStage ? "Replay" : "Run Demonstration"}
            </Button>
            <Button variant="secondary" onClick={resetDemo}>
              Reset
            </Button>
          </div>
          <small>Simulated data · no repository changes or deployment</small>
        </div>

        <div className="editorial-demo-right-column">
          {/* Response comparison card */}
          <div className="editorial-json-demo">
            <div className="json-demo-head">
              <strong>Response comparison</strong>
              <Badge
                tone={
                  demoStage === 4 ? "success" : demoStage >= 2 ? "gold" : "warning"
                }
              >
                {demoStage === 4
                  ? "Validated · Awaiting Developer Review"
                  : demoStage >= 2
                  ? "Validation in progress"
                  : "Simulated change"}
              </Badge>
            </div>
            <div className="json-demo-columns">
              <div>
                <span>BEFORE · SAVED BASELINE</span>
                <pre>{`{\n  "city": "Kyoto",\n  "temperature": 18.4,\n  "unit": "celsius"\n}`}</pre>
              </div>
              <div>
                <span>AFTER · OBSERVED</span>
                <pre>{`{\n  "city": "Kyoto",\n  "temp_c": 18.4,\n  "unit": "celsius"\n}`}</pre>
              </div>
            </div>
            <div className="demo-sequence">
              {["Detected", "Impact traced", "Proposal checked", "Tests passed"].map(
                (label, index) => (
                  <span
                    key={label}
                    className={
                      demoStage > index
                        ? "complete"
                        : demoStage === index
                        ? "active"
                        : ""
                    }
                  >
                    <i>
                      {demoStage > index ? (
                        <Icon name="check" size={12} />
                      ) : (
                        index + 1
                      )}
                    </i>
                    {label}
                  </span>
                )
              )}
            </div>
          </div>

          {/* Result Box directly below */}
          <div className="editorial-demo-result-box" aria-live="polite">
            <div className="result-box-head">
              <div className="result-box-title">
                <Icon name="activity" size={16} />
                <strong>Execution Result</strong>
              </div>
              <div className="result-box-status">
                {demoStage === 4 ? (
                  <Badge tone="success">14 / 14 Passed</Badge>
                ) : demoStage > 0 ? (
                  <Badge tone="gold">In Progress</Badge>
                ) : (
                  <Badge tone="neutral">Idle</Badge>
                )}
              </div>
            </div>

            {demoStage === 0 ? (
              <div className="result-placeholder">
                <span className="result-empty-dot" />
                <p>Run the demonstration to see the result</p>
              </div>
            ) : (
              <div className="result-progressive-list">
                {/* Stage 1 */}
                <div
                  className={`result-item ${
                    demoStage >= 1 ? "result-visible" : ""
                  }`}
                >
                  <span className="result-icon-tag tag-alert">
                    <Icon name="alert" size={13} />
                  </span>
                  <div className="result-item-content">
                    <strong>Change detected:</strong>{" "}
                    <code>temperature</code> → <code>temp_c</code>
                  </div>
                </div>

                {/* Stage 2 */}
                {demoStage >= 2 && (
                  <div className="result-item result-visible">
                    <span className="result-icon-tag tag-trace">
                      <Icon name="graph" size={13} />
                    </span>
                    <div className="result-item-content">
                      <strong>Impact traced:</strong> 3 affected workflows (Checkout, Forecast, Unit Converter)
                    </div>
                  </div>
                )}

                {/* Stage 3 */}
                {demoStage >= 3 && (
                  <div className="result-item result-visible">
                    <span className="result-icon-tag tag-proposal">
                      <Icon name="spark" size={13} />
                    </span>
                    <div className="result-item-content">
                      <strong>Proposal checked:</strong>{" "}
                      <code>map_field temp_c → temperature</code>, legacy fallback kept
                    </div>
                  </div>
                )}

                {/* Stage 4 */}
                {demoStage >= 4 && (
                  <div className="result-item result-visible result-final-stage">
                    <span className="result-icon-tag tag-success">
                      <Icon name="check" size={13} />
                    </span>
                    <div className="result-item-content">
                      <strong>14/14 deterministic checks passed</strong>
                      <div className="result-final-badge-wrap">
                        <Badge tone="success">
                          Validated · Awaiting Developer Review
                        </Badge>
                      </div>
                      <p className="result-footnote">
                        Simulated data · nothing is deployed until a developer approves.
                      </p>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
