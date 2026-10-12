"use client";

import React, { useState } from "react";
import { ChangeRecord, Screen } from "@/types";
import { Button, Badge, Field, Select } from "@/components/ui/Primitives";
import { Icon } from "@/components/ui/Icons";
import { incidentIdForChange } from "@/lib/data";

export function ChangesScreen({
  changes,
  setChanges,
  navigate,
  setActiveIncidentId,
}: {
  changes: ChangeRecord[];
  setChanges: (changes: ChangeRecord[]) => void;
  navigate: (screen: Screen) => void;
  setActiveIncidentId?: (id: string) => void;
}) {
  const [search, setSearch] = useState("");
  const [severity, setSeverity] = useState("All severities");
  const [category, setCategory] = useState("All categories");
  const [dependencyFilter, setDependencyFilter] = useState("All dependency types");
  const [timeRange, setTimeRange] = useState("All observations");
  const [status, setStatus] = useState("All states");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [dismissReason, setDismissReason] = useState("");
  const [dismissing, setDismissing] = useState(false);
  const [toast, setToast] = useState("");

  const visible = changes.filter(
    (change) =>
      (dependencyFilter === "All dependency types" || change.dependencyType === dependencyFilter) &&
      (severity === "All severities" || change.severity === severity) &&
      (category === "All categories" || change.category === category) &&
      (timeRange === "All observations" ||
        (timeRange === "Today" ? change.observed.startsWith("Today") : !change.observed.startsWith("Today"))) &&
      (status === "All states" || change.status === status) &&
      `${change.dependencyType} ${change.service} ${change.endpoint} ${change.summary} ${change.category}`
        .toLowerCase()
        .includes(search.toLowerCase())
  );

  const selected = changes.find((c) => c.id === selectedId);

  const resetFilters = () => {
    setSearch("");
    setDependencyFilter("All dependency types");
    setSeverity("All severities");
    setCategory("All categories");
    setTimeRange("All observations");
    setStatus("All states");
  };

  const updateStatus = (id: string, nextStatus: ChangeRecord["status"]) => {
    setChanges(changes.map((c) => (c.id === id ? { ...c, status: nextStatus } : c)));
    setToast(`${id} updated to ${nextStatus}.`);
    window.setTimeout(() => setToast(""), 3000);
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
              <span>CHANGE DETECTION</span>
              <span className="ml-1"><Badge tone="neutral">STAGING API</Badge></span>
            </div>
            <h1>Change Detection</h1>
            <p>Review observed contract, behavior, and protocol anomalies.</p>
          </div>
        </div>
        <div className="page-actions">
          <Badge tone="neutral">
            {visible.filter((c) => c.status !== "Dismissed").length} active observations
          </Badge>
        </div>
      </div>

      <section className="panel table-panel">
        <div className="table-tools">
          <Field
            value={search}
            onChange={setSearch}
            placeholder="Search dependency, component, schema, or..."
            icon="search"
          />
          <Select value={dependencyFilter} onChange={setDependencyFilter}>
            <option>All dependency types</option>
            <option>API</option>
            <option>SDK</option>
            <option>MCP Server</option>
            <option>Webhook</option>
          </Select>
          <Select value={severity} onChange={setSeverity}>
            <option>All severities</option>
            <option>Critical</option>
            <option>High</option>
            <option>Medium</option>
            <option>Low</option>
          </Select>
          <Select value={category} onChange={setCategory}>
            <option>All categories</option>
            <option>Renamed response field</option>
            <option>Rate-limit change</option>
            <option>Method signature change</option>
            <option>Input schema change</option>
            <option>Payload field rename</option>
            <option>Added response field</option>
          </Select>
          <Select value={timeRange} onChange={setTimeRange}>
            <option>All observations</option>
            <option>Today</option>
            <option>Earlier observations</option>
          </Select>
          <Select value={status} onChange={setStatus}>
            <option>All states</option>
            <option>New</option>
            <option>Acknowledged</option>
            <option>Investigating</option>
            <option>Dismissed</option>
            <option>Recovery open</option>
          </Select>
        </div>

        {visible.length === 0 ? (
          <div className="empty-state">
            <svg
              className="w-10 h-10 text-amber-600 mb-2"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
            </svg>
            <h3>No observed changes match</h3>
            <p>
              Adjust the evidence filters or clear the query. SDK, MCP, and webhook monitoring remains
              unavailable unless configured.
            </p>
            <Button variant="secondary" onClick={resetFilters}>
              Clear filters
            </Button>
          </div>
        ) : (
          <div className="divide-y divide-stone-200">
            {visible.map((change) => (
              <button
                key={change.id}
                onClick={() => {
                  setSelectedId(change.id);
                  setActiveIncidentId?.(incidentIdForChange(change));
                }}
                className="w-full p-4 text-left flex items-center justify-between hover:bg-stone-50 transition-colors"
              >
                <div className="flex items-start gap-3">
                  <span
                    className={`mt-1 p-1.5 rounded ${
                      change.severity === "Critical"
                        ? "bg-red-100 text-red-700"
                        : change.severity === "High"
                        ? "bg-orange-100 text-orange-700"
                        : "bg-amber-100 text-amber-700"
                    }`}
                  >
                    <Icon name={change.breaking ? "alert" : "activity"} size={16} />
                  </span>
                  <div>
                    <div className="text-xs text-slate-500 font-medium">
                      {change.id} · {change.dependencyType} · {change.category}
                    </div>
                    <div className="font-semibold text-slate-900">
                      {change.service} · {change.summary}
                    </div>
                    <code className="text-xs text-slate-600">{change.endpoint}</code>
                  </div>
                </div>
                <div className="flex items-center gap-4">
                  <div className="text-right">
                    <Badge tone={change.breaking ? "danger" : "warning"}>{change.severity}</Badge>
                    <div className="text-xs text-slate-400 mt-1">{change.confidence}% confidence</div>
                  </div>
                  <div className="text-right">
                    <Badge tone={change.status === "Dismissed" ? "neutral" : "gold"}>{change.status}</Badge>
                    <div className="text-xs text-slate-400 mt-1">{change.observed}</div>
                  </div>
                  <Icon name="chevron" size={14} />
                </div>
              </button>
            ))}
          </div>
        )}
      </section>

      {selected && (
        <div className="drawer-scrim" onClick={() => setSelectedId(null)}>
          <aside className="drawer" onClick={(e) => e.stopPropagation()}>
            <div className="drawer-head">
              <button className="page-back" onClick={() => setSelectedId(null)}>
                <Icon name="arrow" className="rotate-180" size={14} /> Back
              </button>
              <h2>{selected.id} · {selected.dependencyType} change evidence</h2>
              <Button variant="icon" icon="close" onClick={() => setSelectedId(null)} />
            </div>

            <div className="drawer-status">
              <Badge tone={selected.breaking ? "danger" : "neutral"}>
                {selected.breaking ? "Potentially incompatible" : "Likely compatible"}
              </Badge>
              <span>{selected.confidence}% confidence · {selected.severity} severity</span>
            </div>

            <div className="detail-block">
              <h3>Observed change</h3>
              <code>{selected.endpoint}</code>
              <p className="text-sm text-slate-700 mt-1">{selected.summary}</p>
            </div>

            <div className="p-3 bg-stone-50 rounded border border-stone-200 text-xs">
              <div className="font-semibold text-slate-700 mb-2">Evidence & Uncertainty</div>
              <p className="text-slate-600">{selected.evidence}</p>
            </div>

            <div className="drawer-actions">
              <Button variant="secondary" onClick={() => updateStatus(selected.id, "Acknowledged")}>
                Acknowledge
              </Button>
              <Button
                variant="secondary"
                icon="graph"
                onClick={() => {
                  updateStatus(selected.id, "Investigating");
                  navigate("graph");
                }}
              >
                Investigate impact
              </Button>
              <Button
                onClick={() => {
                  const targetInc = incidentIdForChange(selected);
                  setActiveIncidentId?.(targetInc);
                  updateStatus(selected.id, "Recovery open");
                  navigate("recovery");
                }}
                icon="recovery"
              >
                Open Recovery Case ({incidentIdForChange(selected)})
              </Button>
            </div>

            <Button variant="danger" onClick={() => setDismissing(true)}>
              Dismiss observation
            </Button>
          </aside>
        </div>
      )}

      {dismissing && selected && (
        <div className="modal-scrim" onClick={() => setDismissing(false)}>
          <section className="modal" onClick={(e) => e.stopPropagation()}>
            <h2>Dismiss {selected.id}?</h2>
            <p className="modal-intro">Dismissal requires a reason and remains recorded in recovery history.</p>
            <label className="form-label">
              Reason
              <textarea
                value={dismissReason}
                onChange={(e) => setDismissReason(e.target.value)}
                placeholder="Explain why this observation is harmless"
              />
            </label>
            <div className="modal-actions">
              <Button variant="ghost" onClick={() => setDismissing(false)}>
                Cancel
              </Button>
              <Button
                variant="danger"
                disabled={!dismissReason.trim()}
                onClick={() => {
                  updateStatus(selected.id, "Dismissed");
                  setDismissing(false);
                  setSelectedId(null);
                  setDismissReason("");
                }}
              >
                Dismiss with reason
              </Button>
            </div>
          </section>
        </div>
      )}

      {toast && (
        <div className="toast">
          <Icon name="check" />
          <span>
            <strong>Change record updated</strong>
            <small>{toast}</small>
          </span>
          <Button variant="icon" icon="close" onClick={() => setToast("")} />
        </div>
      )}
    </>
  );
}
