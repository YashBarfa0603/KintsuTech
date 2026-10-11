"use client";

import React, { useState } from "react";
import { Screen, DependencyType } from "@/types";
import { Button, Badge, Select } from "@/components/ui/Primitives";
import { Icon } from "@/components/ui/Icons";
import { incidentWorkspaceRecords } from "@/lib/data";

export function ValidationLabScreen({
  validationState,
  runValidation,
  navigate,
}: {
  validationState: string;
  runValidation: (outcome?: "success" | "failure") => void;
  navigate: (s: Screen) => void;
}) {
  const [selectedCase, setSelectedCase] = useState("KIN-2841");
  const [kind, setKind] = useState<DependencyType>("API");

  const tests = [
    ["Contract shape conformance", "Contract", "24 ms", "Passed"],
    ["Adapter unit mapping", "Unit", "82 ms", "Passed"],
    ["Production replay scenario", "Integration", "8.4 sec", "Passed"],
    ["Checkout regression test", "Regression", "1.2 sec", validationState === "failed" ? "Failed" : "Passed"],
    ["Missing field fallback check", "Error handling", "860 ms", "Passed"],
  ];

  return (
    <>
      <div className="page-header">
        <div className="page-heading-wrap">
          <button className="page-back" onClick={() => navigate("overview")}>
            <Icon name="arrow" className="rotate-180" size={14} /> Back
          </button>
          <div>
            <div className="breadcrumbs">
              <span>PULSE API</span>
              <Icon name="chevron" size={10} />
              <span>STAGING</span>
              <Icon name="chevron" size={10} />
              <span>VALIDATION LAB</span>
              <span className="ml-1"><Badge tone="neutral">SANDBOX</Badge></span>
            </div>
            <h1>Validation Lab</h1>
            <p>Verify generated adaptations in an isolated execution sandbox.</p>
          </div>
        </div>
        <div className="page-actions">
          <Button variant="secondary" onClick={() => runValidation("failure")}>
            Run failure demo
          </Button>
          <Button
            variant="primary"
            icon="play"
            onClick={() => runValidation("success")}
            disabled={validationState === "running"}
          >
            {validationState === "running" ? "Running suite…" : "Run Validation Suite"}
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-4 gap-3 mb-6">
        {(["API", "SDK", "MCP Server", "Webhook"] as DependencyType[]).map((t) => (
          <button
            key={t}
            onClick={() => setKind(t)}
            className={`p-3 rounded border text-left flex items-center justify-between ${
              kind === t
                ? "bg-stone-900 text-white border-stone-900"
                : "bg-white border-stone-200 text-stone-700 hover:bg-stone-50"
            }`}
          >
            <span className="font-semibold text-xs">{t}</span>
            <Badge tone={t === "API" ? "success" : "neutral"}>
              {t === "API" ? "Configured" : "Unavailable"}
            </Badge>
          </button>
        ))}
      </div>

      <section className="panel p-5">
        <div className="flex items-center justify-between pb-3 border-b border-stone-200 mb-4">
          <div>
            <h3 className="font-bold text-base text-stone-900">Deterministic Test Suite Execution</h3>
            <p className="text-xs text-stone-500">Target case: {selectedCase}</p>
          </div>
          <Badge tone={validationState === "done" ? "success" : validationState === "failed" ? "danger" : "warning"}>
            {validationState === "done" ? "All 14 checks passed" : validationState === "failed" ? "Check failed" : "Ready"}
          </Badge>
        </div>

        <div className="divide-y divide-stone-200">
          {tests.map(([name, cat, time, res]) => (
            <div key={name} className="py-3 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <span className={`p-1.5 rounded ${res === "Passed" ? "bg-emerald-100 text-emerald-700" : "bg-red-100 text-red-700"}`}>
                  <Icon name={res === "Passed" ? "check" : "close"} size={14} />
                </span>
                <div>
                  <strong className="text-sm text-stone-900">{name}</strong>
                  <div className="text-xs text-stone-500">{cat}</div>
                </div>
              </div>
              <div className="flex items-center gap-4 text-xs font-mono">
                <span className="text-stone-400">{time}</span>
                <Badge tone={res === "Passed" ? "success" : "danger"}>{res}</Badge>
              </div>
            </div>
          ))}
        </div>
      </section>
    </>
  );
}
