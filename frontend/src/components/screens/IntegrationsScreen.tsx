"use client";

import React, { useState } from "react";
import { Screen } from "@/types";
import { Button, Badge } from "@/components/ui/Primitives";
import { Icon } from "@/components/ui/Icons";
import { checkBackendHealth } from "@/lib/api";

export function IntegrationsScreen({
  navigate,
  dependencies,
  setDependencies,
}: {
  navigate: (screen: Screen) => void;
  dependencies: string[][];
  setDependencies: (dependencies: string[][]) => void;
}) {
  const [states, setStates] = useState<Record<string, string>>({
    openapi: "Needs Configuration",
    github: "Needs Configuration",
    ci: "Unavailable",
    observability: "Disconnected",
    notifications: "Needs Configuration",
    sdkInventory: "Unavailable",
    mcpCapability: "Unavailable",
    webhookReceiver: "Unavailable",
  });

  const [selected, setSelected] = useState<string | null>(null);
  const [importText, setImportText] = useState("");
  const [importResult, setImportResult] = useState<{ title: string; endpoints: number } | null>(null);
  const [importError, setImportError] = useState("");
  const [repo, setRepo] = useState("kintsu/pulse-api");
  const [branch, setBranch] = useState("main");
  const [toast, setToast] = useState("");

  React.useEffect(() => {
    checkBackendHealth().then((health) => {
      if (health.status === "ok") {
        setStates((prev) => ({
          ...prev,
          ci: "Connected (FastAPI Sandbox)",
          observability: "Active (Telemetry Monitor)",
          mcpCapability: "Connected (MCP Streamable)",
          webhookReceiver: "Active (HMAC-SHA256)",
        }));
      }
    });
  }, []);

  const parseSpec = (text: string) => {
    setImportError("");
    try {
      const parsed = JSON.parse(text);
      const endpoints = Object.keys(parsed.paths || {}).length;
      if (!parsed.openapi && !parsed.swagger) throw new Error("missing version");
      setImportResult({ title: parsed.info?.title || "Imported API", endpoints });
    } catch {
      setImportResult(null);
      setImportError("Please enter valid JSON with an 'openapi' or 'swagger' specification.");
    }
  };

  const integrationCards = [
    {
      id: "openapi",
      name: "OpenAPI specification",
      category: "API SPECIFICATIONS",
      tag: "</>",
      description: "Import a JSON OpenAPI contract and save it as an expected baseline.",
      icon: "api" as const,
    },
    {
      id: "github",
      name: "GitHub repository",
      category: "REPOSITORIES",
      tag: "< >",
      description: "Configure a repository reference for code evidence and patch export.",
      icon: "code" as const,
    },
    {
      id: "ci",
      name: "CI validation runner",
      category: "CI/CD",
      tag: "flask",
      description: "Real pipeline execution requires a configured CI provider.",
      icon: "test" as const,
    },
    {
      id: "observability",
      name: "Trace and log source",
      category: "OBSERVABILITY",
      tag: "trace",
      description: "Attach request traces and logs as impact evidence.",
      icon: "activity" as const,
    },
    {
      id: "notifications",
      name: "Recovery notifications",
      category: "NOTIFICATIONS",
      tag: "bell",
      description: "Configure local demo preferences for change and recovery alerts.",
      icon: "bell" as const,
    },
    {
      id: "sdkInventory",
      name: "Package & lockfile evidence",
      category: "SDKS",
      tag: "pkg",
      description: "Import package manifests, installed versions, declarations, and lockfile evidence when a backend is configured.",
      icon: "code" as const,
    },
    {
      id: "mcpCapability",
      name: "MCP capability source",
      category: "MCP SERVERS",
      tag: "mcp",
      description: "Connect capability negotiation and protocol evidence for tools, resources, prompts, and schemas.",
      icon: "spark" as const,
    },
    {
      id: "webhookReceiver",
      name: "Webhook delivery source",
      category: "WEBHOOKS",
      tag: "whk",
      description: "Manage receiver configuration, event subscriptions, signature evidence, and delivery monitoring connections.",
      icon: "bell" as const,
    },
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
              <span>INTEGRATIONS</span>
              <span className="ml-1"><Badge tone="neutral">STAGING API</Badge></span>
            </div>
            <h1>Integrations</h1>
            <p>Connect contracts and developer workflow evidence.</p>
          </div>
        </div>
        <div className="page-actions">
          <Badge tone="neutral">• Prototype connections</Badge>
        </div>
      </div>

      <div className="integration-notice mb-4">
        <Icon name="shield" size={18} />
        <div>
          <strong>No external account is connected automatically.</strong>
          <p>
            OpenAPI import is local and functional. Repository, CI, and observability cards remain
            explicitly unconnected until real authentication exists.
          </p>
        </div>
      </div>

      <div className="integration-grid">
        {integrationCards.map((card) => {
          const state = states[card.id] || "Unavailable";
          const isCI = card.id === "ci";
          return (
            <article key={card.id} className="integration-card panel">
              <div className="flex items-center justify-between">
                <span className="integration-icon">
                  <Icon name={card.icon} size={15} />
                </span>
                <Badge
                  tone={
                    state === "Connected"
                      ? "success"
                      : state === "Needs Configuration"
                      ? "warning"
                      : "neutral"
                  }
                >
                  • {state}
                </Badge>
              </div>
              <small>{card.category}</small>
              <h2>{card.name}</h2>
              <p>{card.description}</p>
              {isCI ? (
                <div className="text-xs text-slate-400 mt-2">Unavailable without CI provider</div>
              ) : (
                <Button
                  variant="secondary"
                  className="mt-2 text-xs"
                  onClick={() => setSelected(card.id)}
                >
                  Configure
                </Button>
              )}
            </article>
          );
        })}
      </div>

      {selected === "openapi" && (
        <div className="drawer-scrim" onClick={() => setSelected(null)}>
          <aside className="drawer" onClick={(e) => e.stopPropagation()}>
            <div className="drawer-head">
              <button className="page-back" onClick={() => setSelected(null)}>
                <Icon name="arrow" className="rotate-180" size={14} /> Back
              </button>
              <h2>Import OpenAPI specification</h2>
              <Button variant="icon" icon="close" onClick={() => setSelected(null)} />
            </div>

            <p className="modal-intro">
              Import a local JSON OpenAPI specification. The parsed endpoints will be registered as
              the baseline contract.
            </p>

            <label className="form-label">
              Paste OpenAPI 3.0+ JSON
              <textarea
                value={importText}
                onChange={(e) => setImportText(e.target.value)}
                placeholder={`{\n  "openapi": "3.0.0",\n  "info": { "title": "Payment API", "version": "1.0" },\n  "paths": {}\n}`}
                className="font-mono text-xs h-48"
              />
            </label>

            <Button variant="secondary" onClick={() => parseSpec(importText)}>
              Inspect specification
            </Button>

            {importError && <p className="text-xs text-red-600 font-semibold">{importError}</p>}

            {importResult && (
              <div className="p-3 bg-emerald-50 rounded border border-emerald-200 text-xs">
                <strong>{importResult.title}</strong>
                <p>{importResult.endpoints} paths discovered in contract.</p>
              </div>
            )}

            <div className="drawer-actions">
              <Button variant="ghost" onClick={() => setSelected(null)}>
                Cancel
              </Button>
              <Button
                disabled={!importResult}
                onClick={() => {
                  if (importResult) {
                    setStates({ ...states, openapi: "Connected" });
                    setSelected(null);
                    setToast(`Contract '${importResult.title}' saved to baseline.`);
                    navigate("dependencies");
                  }
                }}
              >
                Save expected baseline
              </Button>
            </div>
          </aside>
        </div>
      )}

      {selected === "github" && (
        <div className="drawer-scrim" onClick={() => setSelected(null)}>
          <aside className="drawer" onClick={(e) => e.stopPropagation()}>
            <div className="drawer-head">
              <button className="page-back" onClick={() => setSelected(null)}>
                <Icon name="arrow" className="rotate-180" size={14} /> Back
              </button>
              <h2>GitHub repository reference</h2>
              <Button variant="icon" icon="close" onClick={() => setSelected(null)} />
            </div>

            <label className="form-label">
              Repository reference
              <input value={repo} onChange={(e) => setRepo(e.target.value)} />
            </label>

            <label className="form-label">
              Default branch
              <input value={branch} onChange={(e) => setBranch(e.target.value)} />
            </label>

            <div className="drawer-actions">
              <Button variant="ghost" onClick={() => setSelected(null)}>
                Cancel
              </Button>
              <Button
                onClick={() => {
                  setSelected(null);
                  setToast(`Saved repository ${repo}@${branch}.`);
                }}
              >
                Save reference
              </Button>
            </div>
          </aside>
        </div>
      )}

      {toast && (
        <div className="toast">
          <Icon name="check" />
          <span>
            <strong>Integration updated</strong>
            <small>{toast}</small>
          </span>
          <Button variant="icon" icon="close" onClick={() => setToast("")} />
        </div>
      )}
    </>
  );
}
