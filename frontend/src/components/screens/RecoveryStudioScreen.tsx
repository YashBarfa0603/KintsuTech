"use client";

import React, { useState } from "react";
import { Screen, IncidentWorkspaceRecord } from "@/types";
import { Button, Badge, Select } from "@/components/ui/Primitives";
import { Icon } from "@/components/ui/Icons";
import { incidentWorkspaceRecords, myersEditDistance } from "@/lib/data";

export function RecoveryStudioScreen({
  caseStatus,
  setCaseStatus,
  validationState,
  runValidation,
  navigate,
}: {
  caseStatus: string;
  setCaseStatus: (s: "review" | "validated" | "approved" | "rejected") => void;
  validationState: string;
  runValidation: (outcome?: "success" | "failure") => void;
  navigate: (s: Screen) => void;
}) {
  const [selectedCase, setSelectedCase] = useState("KIN-2841");
  const incident = incidentWorkspaceRecords.find((i) => i.id === selectedCase) || incidentWorkspaceRecords[0];

  const [activeStage, setActiveStage] = useState("01 · What Changed");
  const [proposalCode, setProposalCode] = useState(incident.proposedCode);
  const [editingCode, setEditingCode] = useState(false);
  const [selectedField, setSelectedField] = useState<string | null>("name");
  const [statusMessage, setStatusMessage] = useState("");

  const stages = [
    "00 · Summary",
    "01 · What Changed",
    "02 · Similar Incidents",
    "03 · AI Analysis",
    "04 · Safety Check",
    "05 · Proposed Fix",
    "06 · Test Results",
    "07 · Review & Approve",
    "08 · Activity Timeline",
  ];

  const baselineKeys = Object.keys(incident.baseline);
  const currentKeys = Object.keys(incident.current);
  const removed = baselineKeys.filter((k) => !currentKeys.includes(k));
  const added = currentKeys.filter((k) => !baselineKeys.includes(k));
  const unchanged = baselineKeys.filter((k) => currentKeys.includes(k));

  const isApproved = caseStatus === "approved";
  const isValidated = validationState === "done";
  const isFailed = validationState === "failed";

  const handleApprove = () => {
    setCaseStatus("approved");
    setStatusMessage("Fix approved by Akira K. Ready for deployment pipeline.");
  };

  const handleReject = () => {
    setCaseStatus("rejected");
    setStatusMessage("Fix rejected. Sent back for revision.");
  };

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
              <span>RECOVERY STUDIO</span>
              <span className="ml-1"><Badge tone="neutral">INCIDENT WORKSPACE</Badge></span>
            </div>
            <h1>Recovery Studio</h1>
            <p>Incident analysis, controlled repair, and evidence-based approval.</p>
          </div>
        </div>
        <div className="page-actions">
          <Select value={selectedCase} onChange={setSelectedCase}>
            {incidentWorkspaceRecords.map((r) => (
              <option key={r.id} value={r.id}>
                {r.id} · {r.api}
              </option>
            ))}
          </Select>
          <Badge tone={isApproved ? "success" : isFailed ? "danger" : "warning"}>
            {isApproved ? "Approved" : isFailed ? "Testing failed" : "Awaiting review"}
          </Badge>
          <Button variant="secondary" icon="graph" onClick={() => navigate("graph")}>
            AI Dependency Graph
          </Button>
        </div>
      </div>

      {statusMessage && (
        <div className="p-3 bg-emerald-50 border border-emerald-200 text-emerald-800 rounded-md text-xs font-medium mb-4 flex items-center justify-between">
          <span>✓ {statusMessage}</span>
          <button onClick={() => setStatusMessage("")} className="text-emerald-600 font-bold">×</button>
        </div>
      )}

      {/* Stage Stepper */}
      <div className="flex gap-1.5 overflow-x-auto pb-3 mb-5 border-b border-stone-200">
        {stages.map((stg) => (
          <button
            key={stg}
            onClick={() => setActiveStage(stg)}
            className={`px-3 py-1.5 rounded text-xs font-semibold whitespace-nowrap transition-colors ${
              activeStage === stg
                ? "bg-stone-900 text-white"
                : "bg-white border border-stone-200 text-stone-600 hover:bg-stone-100"
            }`}
          >
            {stg}
          </button>
        ))}
      </div>

      {/* Summary Section */}
      <section className="panel p-5 mb-6">
        <div className="flex items-start justify-between">
          <div>
            <div className="text-xs font-bold text-stone-500 uppercase">INCIDENT SUMMARY · {incident.id}</div>
            <h2 className="text-xl font-bold text-stone-900 mt-1 mb-2">{incident.title}</h2>
            <p className="text-sm text-stone-600 max-w-3xl leading-relaxed">
              <strong>What changed:</strong> {incident.problem}{" "}
              <strong>Workflows affected:</strong> {incident.workflows.join(", ")}.{" "}
              <strong>Expected:</strong> {incident.expected}
            </p>
          </div>
          <div className="text-right flex flex-col items-end gap-1">
            <Badge tone={incident.severity === "Critical" ? "danger" : "warning"}>{incident.severity}</Badge>
            <div className="text-xs text-stone-400 mt-1">{incident.detected}</div>
          </div>
        </div>
      </section>

      {/* 01 · What Changed (Myers Diff Comparison) */}
      <section className="panel p-5 mb-6">
        <div className="flex items-center justify-between mb-4 pb-2 border-b border-stone-200">
          <div>
            <div className="text-xs font-bold text-stone-500 uppercase">01 · WHAT CHANGED</div>
            <h3 className="text-base font-bold text-stone-900">Before vs After Response Payload</h3>
          </div>
          <div className="flex gap-2">
            <Badge tone="danger">{removed.length} removed</Badge>
            <Badge tone="success">{added.length} added</Badge>
            <Badge tone="neutral">{unchanged.length} unchanged</Badge>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div className="p-4 bg-stone-900 text-stone-100 rounded-md font-mono text-xs overflow-x-auto">
            <div className="text-stone-400 font-sans text-xs font-semibold mb-2">BEFORE (Saved Baseline)</div>
            <pre>
              {`{\n  "id": "${incident.baseline.id}",\n  "amount": ${incident.baseline.amount},\n  `}
              <span className="bg-red-950 text-red-300 px-1 py-0.5 rounded font-bold">
                {`"name": "${incident.baseline.name}"`}
              </span>
              {`,\n  "currency": "${incident.baseline.currency}",\n  "status": "${incident.baseline.status}"\n}`}
            </pre>
          </div>

          <div className="p-4 bg-stone-900 text-stone-100 rounded-md font-mono text-xs overflow-x-auto">
            <div className="text-stone-400 font-sans text-xs font-semibold mb-2">AFTER (Observed Anomaly)</div>
            <pre>
              {`{\n  "id": "${incident.current.id}",\n  "amount": ${incident.current.amount},\n  `}
              <span className="bg-emerald-950 text-emerald-300 px-1 py-0.5 rounded font-bold">
                {`"display_name": "${incident.current.display_name}"`}
              </span>
              {`,\n  "currency": "${incident.current.currency}",\n  "status": "${incident.current.status}"\n}`}
            </pre>
          </div>
        </div>
      </section>

      {/* 05 · Proposed Fix (Adapter Code & Diff) */}
      <section className="panel p-5 mb-6">
        <div className="flex items-center justify-between mb-4 pb-2 border-b border-stone-200">
          <div>
            <div className="text-xs font-bold text-stone-500 uppercase">05 · PROPOSED FIX</div>
            <h3 className="text-base font-bold text-stone-900">{incident.proposalTitle}</h3>
          </div>
          <div className="flex gap-2">
            <Button
              variant="secondary"
              onClick={() => setEditingCode(!editingCode)}
            >
              {editingCode ? "Close editor" : "Edit proposal"}
            </Button>
            <Button
              variant="secondary"
              onClick={() => navigator.clipboard.writeText(proposalCode)}
            >
              Copy code
            </Button>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4 mb-4">
          <div>
            <div className="text-xs font-semibold text-stone-600 mb-1">Original Implementation</div>
            <pre className="p-4 bg-stone-100 text-stone-800 rounded font-mono text-xs border border-stone-200 h-44 overflow-y-auto">
              <code>{incident.originalCode}</code>
            </pre>
          </div>

          <div>
            <div className="text-xs font-semibold text-stone-600 mb-1">
              Proposed Compatibility Adapter (Isolated Boundary)
            </div>
            {editingCode ? (
              <textarea
                value={proposalCode}
                onChange={(e) => setProposalCode(e.target.value)}
                className="w-full h-44 p-3 bg-white border border-stone-300 rounded font-mono text-xs"
              />
            ) : (
              <pre className="p-4 bg-stone-900 text-stone-100 rounded font-mono text-xs border border-stone-700 h-44 overflow-y-auto">
                <code>{proposalCode}</code>
              </pre>
            )}
          </div>
        </div>
      </section>

      {/* 06 · Test Results */}
      <section className="panel p-5 mb-6">
        <div className="flex items-center justify-between mb-4 pb-2 border-b border-stone-200">
          <div>
            <div className="text-xs font-bold text-stone-500 uppercase">06 · TEST RESULTS</div>
            <h3 className="text-base font-bold text-stone-900">Isolated Validation Sandbox</h3>
          </div>
          <div className="flex gap-2">
            <Button
              variant="secondary"
              onClick={() => runValidation("failure")}
            >
              Run failure scenario
            </Button>
            <Button
              variant="primary"
              icon="play"
              onClick={() => runValidation("success")}
            >
              {validationState === "running" ? "Running suite…" : "Run Validation Suite"}
            </Button>
          </div>
        </div>

        <div className="p-3 bg-stone-50 rounded border border-stone-200 text-xs flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Icon name={isValidated ? "check" : isFailed ? "alert" : "activity"} size={16} />
            <span className="font-semibold text-stone-800">
              {isValidated
                ? "14 of 14 checks passed (Contract, unit, and replay suite)"
                : isFailed
                ? "13 passed, 1 regression check failed"
                : "Validation suite ready"}
            </span>
          </div>
          <Badge tone={isValidated ? "success" : isFailed ? "danger" : "warning"}>
            {isValidated ? "Passed" : isFailed ? "Failed" : "Ready"}
          </Badge>
        </div>
      </section>

      {/* 07 · Review & Approve */}
      <section className="panel p-5 mb-6">
        <div className="flex items-center justify-between mb-3 pb-2 border-b border-stone-200">
          <div>
            <div className="text-xs font-bold text-stone-500 uppercase">07 · REVIEW & APPROVE</div>
            <h3 className="text-base font-bold text-stone-900">Human Approval Gate</h3>
          </div>
          <Badge tone={isApproved ? "success" : "gold"}>
            {isApproved ? "Approved by Akira K." : "Approval required"}
          </Badge>
        </div>

        <p className="text-sm text-stone-600 mb-4">
          Approval authorizes the verified adapter proposal. KintsuTech never deploys to production
          without separate release pipeline authorization.
        </p>

        <div className="flex items-center justify-end gap-3">
          <Button variant="danger" onClick={handleReject}>
            Reject fix
          </Button>
          <Button variant="secondary" onClick={() => setCaseStatus("review")}>
            Request changes
          </Button>
          <Button
            variant="primary"
            icon="check"
            disabled={!isValidated || isApproved}
            onClick={handleApprove}
          >
            {isApproved ? "Fix approved" : "Approve fix"}
          </Button>
        </div>
      </section>
    </>
  );
}
