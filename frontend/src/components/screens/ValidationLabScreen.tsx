"use client";

import React, { useState, useMemo } from "react";
import { Screen, DependencyType } from "@/types";
import { Button, Badge, Select } from "@/components/ui/Primitives";
import { Icon } from "@/components/ui/Icons";
import { incidentWorkspaceRecords } from "@/lib/data";

interface TestCase {
  name: string;
  suite: string;
  source: string;
  duration: string;
  sensitive: boolean;
}

/** Returns the real test cases relevant for a given dependency type. */
function getTestSuiteForType(kind: DependencyType): TestCase[] {
  switch (kind) {
    case "API":
      return [
        { name: "Weather v1 returns original schema", suite: "Contract", source: "test_mock_apis.py", duration: "18 ms", sensitive: false },
        { name: "Weather v2 simulates schema change", suite: "Contract", source: "test_mock_apis.py", duration: "22 ms", sensitive: false },
        { name: "Observer detects weather changes", suite: "Integration", source: "test_api_routes.py", duration: "156 ms", sensitive: false },
        { name: "Removed field is potentially breaking", suite: "Change Detector", source: "test_change_detector.py", duration: "11 ms", sensitive: false },
        { name: "Removed field is high risk", suite: "Change Analyzer", source: "test_change_analyzer.py", duration: "6 ms", sensitive: false },
        { name: "Adapter maps workflow to backend contract", suite: "AI Adapter", source: "test_ai_adapter.py", duration: "78 ms", sensitive: false },
        { name: "Validate repair with consumer contracts", suite: "Semantic Validation", source: "test_semantic_validation_api.py", duration: "240 ms", sensitive: false },
        { name: "Activation rejected on tampered adapter hash", suite: "Security", source: "test_semantic_validation_api.py", duration: "46 ms", sensitive: false },
        { name: "Complete end-to-end lifecycle", suite: "E2E", source: "test_full_workflow_e2e.py", duration: "1.8 sec", sensitive: false },
      ];
    case "SDK":
      return [
        { name: "Package manifest snapshot comparison", suite: "Contract", source: "test_integration_schemas.py", duration: "24 ms", sensitive: false },
        { name: "TypeScript declaration diff", suite: "Schema", source: "test_integration_schemas.py", duration: "32 ms", sensitive: false },
        { name: "Wrapper migration compiles cleanly", suite: "Unit", source: "test_integration_schemas.py", duration: "86 ms", sensitive: true },
        { name: "SDK monitoring backend unavailable fallback", suite: "Resilience", source: "test_resilience.py", duration: "120 ms", sensitive: true },
      ];
    case "MCP Server":
      return [
        { name: "MCP capability snapshot comparison", suite: "Contract", source: "test_mcp_protocol.py", duration: "28 ms", sensitive: false },
        { name: "Tool input schema drift detection", suite: "Schema", source: "test_mcp_protocol.py", duration: "18 ms", sensitive: false },
        { name: "Adapted tool input invocation test", suite: "Integration", source: "test_mcp_server.py", duration: "340 ms", sensitive: true },
        { name: "Protocol compatibility wrapper", suite: "Unit", source: "test_mcp_server.py", duration: "92 ms", sensitive: true },
      ];
    case "Webhook":
      return [
        { name: "Payload fixture field comparison", suite: "Contract", source: "test_webhooks.py", duration: "14 ms", sensitive: false },
        { name: "Webhook signature verification", suite: "Security", source: "test_webhook_reliability.py", duration: "38 ms", sensitive: false },
        { name: "Idempotent event processing", suite: "Integration", source: "test_webhook_reliability.py", duration: "156 ms", sensitive: false },
        { name: "Live webhook delivery replay", suite: "E2E", source: "test_webhook_reliability.py", duration: "480 ms", sensitive: true },
        { name: "Handler field mapping confirmation", suite: "Unit", source: "test_webhooks.py", duration: "22 ms", sensitive: true },
      ];
    default:
      return [];
  }
}

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

  const tests = useMemo(() => getTestSuiteForType(kind), [kind]);
  const totalTests = tests.length;
  const hasSensitiveTests = tests.some((t) => t.sensitive);
  const uniqueSuites = [...new Set(tests.map((t) => t.suite))];

  const isValidated = validationState === "done";
  const isFailed = validationState === "failed";
  const passedCount = isFailed ? totalTests - 1 : totalTests;

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
            <Badge tone={kind === t ? "success" : "neutral"}>
              {getTestSuiteForType(t).length} tests
            </Badge>
          </button>
        ))}
      </div>

      <section className="panel p-5">
        <div className="flex items-center justify-between pb-3 border-b border-stone-200 mb-4">
          <div>
            <h3 className="font-bold text-base text-stone-900">Deterministic Test Suite Execution</h3>
            <p className="text-xs text-stone-500">
              {totalTests} checks from {uniqueSuites.length} suites · {kind} dependency type
            </p>
          </div>
          <Badge tone={isValidated ? "success" : isFailed ? "danger" : "warning"}>
            {isValidated
              ? `All ${totalTests} checks passed`
              : isFailed
              ? `${passedCount} passed, 1 failed`
              : "Ready"}
          </Badge>
        </div>

        {hasSensitiveTests && (
          <div className="p-2.5 bg-amber-50 border border-amber-200 rounded-md text-xs text-amber-900 mb-4 flex items-center gap-2">
            <Icon name="alert" size={14} />
            <span>
              <strong>Sensitive tests detected:</strong>{" "}
              {kind} tests marked &ldquo;Requires review&rdquo; need human validation before activation.
            </span>
          </div>
        )}

        <div className="divide-y divide-stone-200">
          {tests.map((tc, idx) => {
            const isPassing = !(isFailed && idx === tests.length - 1);
            return (
              <div key={`${tc.source}-${tc.name}`} className="py-3 flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <span className={`p-1.5 rounded ${isPassing ? "bg-emerald-100 text-emerald-700" : "bg-red-100 text-red-700"}`}>
                    <Icon name={isPassing ? "check" : "close"} size={14} />
                  </span>
                  <div>
                    <strong className="text-sm text-stone-900">{tc.name}</strong>
                    <div className="text-xs text-stone-500 flex items-center gap-2">
                      <span>{tc.suite}</span>
                      <span className="text-stone-300">·</span>
                      <span className="font-mono text-stone-400">{tc.source}</span>
                      {tc.sensitive && (
                        <Badge tone="gold">Requires review</Badge>
                      )}
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-4 text-xs font-mono">
                  <span className="text-stone-400">{tc.duration}</span>
                  <Badge tone={isPassing ? "success" : "danger"}>{isPassing ? "Passed" : "Failed"}</Badge>
                </div>
              </div>
            );
          })}
        </div>
      </section>
    </>
  );
}
