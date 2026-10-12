"use client";

import React, { useState } from "react";
import { DependencyType, Screen } from "@/types";
import { Button, Badge, Field, Select } from "@/components/ui/Primitives";
import { Icon } from "@/components/ui/Icons";
import { dependencyType, dependencyMeta, dependencyDetails, dependencyIcon } from "@/lib/data";

export function DependenciesScreen({
  navigate,
  dependencies,
  setDependencies,
  currentProject = "Pulse API",
  currentEnv = "Staging",
}: {
  navigate: (s: Screen) => void;
  dependencies: string[][];
  setDependencies: (rows: string[][]) => void;
  currentProject?: string;
  currentEnv?: string;
}) {
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("All status");
  const [typeFilter, setTypeFilter] = useState("All types");
  const [severityFilter, setSeverityFilter] = useState("All severities");
  const [sort, setSort] = useState("Name");
  const [view, setView] = useState<"table" | "cards">("table");
  const [selected, setSelected] = useState<string | null>(null);
  const [detailTab, setDetailTab] = useState("Overview");
  const [showAdd, setShowAdd] = useState(false);
  const [addStep, setAddStep] = useState(1);
  const [newDependencyType, setNewDependencyType] = useState<DependencyType>("API");
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [endpoint, setEndpoint] = useState("");
  const [httpMethod, setHttpMethod] = useState("GET");
  const [requestConfig, setRequestConfig] = useState("Bearer token · JSON");
  const [baselineShape, setBaselineShape] = useState(`{ "id": "string", "status": "string" }`);
  const [ecosystem, setEcosystem] = useState("npm");
  const [version, setVersion] = useState("");
  const [source, setSource] = useState("");
  const [components, setComponents] = useState("");
  const [formError, setFormError] = useState("");
  const [testing, setTesting] = useState<"idle" | "running" | "success" | "failed">("idle");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [toast, setToast] = useState("");

  const showToast = (message: string) => {
    setToast(message);
    window.setTimeout(() => setToast(""), 3000);
  };

  const environmentDependencies = dependencies.filter(
    (row) => (row[9] || "Pulse API") === currentProject && (row[10] || dependencyMeta(row[0]).environment) === currentEnv
  );

  const selectedRow = environmentDependencies.find((row) => row[0] === selected);
  const selectedType = dependencyType(selectedRow);
  const selectedDetails = dependencyDetails(selectedRow);

  const filtered = [...environmentDependencies]
    .filter((r) => {
      const meta = dependencyMeta(r[0]);
      return (
        (filter === "All status" || r[3] === filter) &&
        (typeFilter === "All types" || dependencyType(r) === typeFilter) &&
        (severityFilter === "All severities" || meta.severity === severityFilter) &&
        r.join(" ").toLowerCase().includes(search.toLowerCase())
      );
    })
    .sort((a, b) => {
      if (sort === "Latency") return Number.parseInt(a[5]) - Number.parseInt(b[5]);
      if (sort === "Status") return a[3].localeCompare(b[3]);
      if (sort === "Last activity") return a[4].localeCompare(b[4]);
      return a[0].localeCompare(b[0]);
    });

  const addDependency = () => {
    if (!name.trim()) {
      setFormError("Name is required.");
      return;
    }

    const identity = url.trim().replace(/^https?:\/\//, "");
    const componentSummary = `${httpMethod} ${endpoint.trim() || "/"}`;
    const details = { method: httpMethod, requestConfig, baseline: baselineShape };

    setDependencies([
      ...dependencies,
      [
        name.trim(),
        identity,
        componentSummary,
        testing === "success" ? "Healthy" : "Unknown",
        "Just now",
        "198 ms",
        "0.1%",
        "Baseline created",
        "1",
        currentProject,
        currentEnv,
        newDependencyType,
        JSON.stringify(details),
      ],
    ]);

    setShowAdd(false);
    setAddStep(1);
    setName("");
    setUrl("");
    setEndpoint("");
    setFormError("");
    showToast(`${name.trim()} was added.`);
  };

  const removeDependency = () => {
    if (!selected) return;
    setDependencies(dependencies.filter((row) => row[0] !== selected));
    showToast(`${selected} was removed.`);
    setConfirmDelete(false);
    setSelected(null);
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
              <span>DEPENDENCIES</span>
              <span className="ml-1"><Badge tone="neutral">STAGING API</Badge></span>
            </div>
            <h1>Dependencies</h1>
            <p>Manage APIs, SDK packages, MCP servers, and webhooks with type-specific evidence.</p>
          </div>
        </div>
        <div className="page-actions">
          <Button variant="secondary" icon="graph" onClick={() => navigate("graph")}>
            AI Dependency Graph
          </Button>
          <Button variant="secondary" icon="download" onClick={() => navigate("integrations")}>
            Import evidence
          </Button>
          <Button variant="secondary" onClick={() => setView(view === "table" ? "cards" : "table")}>
            {view === "table" ? "Card view" : "Table view"}
          </Button>
          <Button icon="plus" onClick={() => setShowAdd(true)}>
            Add Dependency
          </Button>
        </div>
      </div>

      <section className="panel table-panel">
        <div className="table-tools">
          <Field
            value={search}
            onChange={setSearch}
            placeholder="Search API, package, server, webhook, event..."
            icon="search"
          />
          <Select value={filter} onChange={setFilter}>
            <option>All status</option>
            <option>Healthy</option>
            <option>Degraded</option>
            <option>Watching</option>
            <option>Unknown</option>
          </Select>
          <Select value={typeFilter} onChange={setTypeFilter}>
            <option value="All types">APIs</option>
            <option value="API">API</option>
            <option value="SDK">SDK</option>
            <option value="MCP Server">MCP Server</option>
            <option value="Webhook">Webhook</option>
          </Select>
          <Select value={severityFilter} onChange={setSeverityFilter}>
            <option>All severities</option>
            <option>Critical</option>
            <option>Medium</option>
            <option>None</option>
          </Select>
          <Select value={sort} onChange={setSort}>
            <option>Name</option>
            <option>Latency</option>
            <option>Status</option>
            <option>Last activity</option>
          </Select>
        </div>

        {filtered.length === 0 ? (
          <div className="empty-state">
            <Icon name="search" />
            <h3>No dependencies match</h3>
            <p>Adjust the search or filters to see configured dependencies in {currentEnv}.</p>
            <Button
              variant="secondary"
              onClick={() => {
                setSearch("");
                setFilter("All status");
                setTypeFilter("All types");
                setSeverityFilter("All severities");
              }}
            >
              Clear filters
            </Button>
          </div>
        ) : view === "table" ? (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  {[
                    "Dependency",
                    "Component / configuration",
                    "Type",
                    "Status",
                    "Last activity",
                    "Latency",
                    "Error rate",
                    "Latest evidence",
                    "Relationships",
                    "",
                  ].map((h) => (
                    <th key={h}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filtered.map((r) => (
                  <tr key={r[0]} onClick={() => setSelected(r[0])}>
                    <td>
                      <div className="flex items-center gap-2">
                        <span className="w-7 h-7 rounded bg-slate-800 text-white flex items-center justify-center font-mono text-xs font-bold">
                          {r[0].slice(0, 2).toUpperCase()}
                        </span>
                        <div>
                          <strong>{r[0]}</strong>
                          <small>{r[1]}</small>
                        </div>
                      </div>
                    </td>
                    <td>
                      <code>{r[2]}</code>
                    </td>
                    <td>
                      <Badge tone="neutral">{dependencyType(r)}</Badge>
                    </td>
                    <td>
                      <Badge
                        tone={
                          r[3] === "Healthy"
                            ? "success"
                            : r[3] === "Degraded"
                            ? "danger"
                            : r[3] === "Unknown"
                            ? "neutral"
                            : "warning"
                        }
                      >
                        {r[3]}
                      </Badge>
                    </td>
                    <td>{r[4]}</td>
                    <td>{r[5]}</td>
                    <td>{r[6]}</td>
                    <td>{r[7]}</td>
                    <td>{r[8]}</td>
                    <td>
                      <Icon name="chevron" size={14} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="p-4 grid grid-cols-2 gap-4">
            {filtered.map((r) => (
              <button
                key={r[0]}
                onClick={() => setSelected(r[0])}
                className="p-4 bg-white border border-stone-200 rounded-md text-left flex flex-col gap-2 hover:border-stone-400"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="w-6 h-6 rounded bg-slate-800 text-white flex items-center justify-center text-xs font-bold">
                      {r[0].slice(0, 2)}
                    </span>
                    <strong className="text-sm">{r[0]}</strong>
                  </div>
                  <Badge tone={r[3] === "Healthy" ? "success" : "warning"}>{r[3]}</Badge>
                </div>
                <code>{r[2]}</code>
                <div className="flex items-center justify-between text-xs text-slate-500 mt-2">
                  <span>Latency: {r[5]}</span>
                  <span>{r[4]}</span>
                </div>
              </button>
            ))}
          </div>
        )}

        <div className="table-footer">
          <span>
            Showing {filtered.length} of {environmentDependencies.length} dependencies in {currentEnv}
          </span>
          <span className="flex items-center gap-2">
            SDK, MCP, and webhook monitoring <Badge tone="neutral">Backend required</Badge>
          </span>
        </div>
      </section>

      {selected && selectedRow && (
        <div className="drawer-scrim" onClick={() => setSelected(null)}>
          <aside className="drawer" onClick={(e) => e.stopPropagation()}>
            <div className="drawer-head">
              <button className="page-back" onClick={() => setSelected(null)}>
                <Icon name="arrow" className="rotate-180" size={14} /> Back
              </button>
              <h2>{selected} · {selectedType} details</h2>
              <Button variant="icon" icon="close" onClick={() => setSelected(null)} />
            </div>

            <div className="drawer-status">
              <Badge tone={selectedRow[3] === "Healthy" ? "success" : "warning"}>
                {selectedRow[3]}
              </Badge>
              <span>{selectedRow[4]} · {selectedType}</span>
            </div>

            <div className="flex gap-2 border-b border-stone-200 pb-2 overflow-x-auto text-xs font-medium">
              {["Overview", "Components", "Observed Behaviour", "Change History", "Configuration"].map((tab) => (
                <button
                  key={tab}
                  className={`px-2 py-1 rounded whitespace-nowrap ${
                    detailTab === tab ? "bg-stone-800 text-white" : "text-stone-600 hover:bg-stone-100"
                  }`}
                  onClick={() => setDetailTab(tab)}
                >
                  {tab}
                </button>
              ))}
            </div>

            {detailTab === "Overview" && (
              <>
                <div className="detail-block">
                  <h3>Observed endpoint</h3>
                  <code>{selectedRow[2]}</code>
                  <p className="text-xs text-slate-500 mt-1">Host: {selectedRow[1]}</p>
                </div>
                <div className="detail-block">
                  <h3>Telemetry baseline</h3>
                  <dl>
                    <div>
                      <dt>P95 Latency</dt>
                      <dd>{selectedRow[5]}</dd>
                    </div>
                    <div>
                      <dt>Error rate</dt>
                      <dd>{selectedRow[6]}</dd>
                    </div>
                    <div>
                      <dt>Relationships</dt>
                      <dd>{selectedRow[8]}</dd>
                    </div>
                    <div>
                      <dt>Monitoring</dt>
                      <dd>{selectedRow[3]}</dd>
                    </div>
                  </dl>
                </div>
              </>
            )}

            {detailTab === "Components" && (
              <div className="detail-block">
                <h3>Registered components</h3>
                <div className="detail-list-row">
                  <code>{selectedRow[2]}</code>
                  <Badge tone="success">Active</Badge>
                </div>
              </div>
            )}

            {detailTab === "Observed Behaviour" && (
              <div className="detail-block">
                <h3>Available evidence</h3>
                <p className="text-sm text-slate-700">{selectedRow[7]}</p>
              </div>
            )}

            {detailTab === "Change History" && (
              <div className="detail-block">
                <h3>Change records</h3>
                <div className="detail-list-row">
                  <span>{selectedRow[7]}</span>
                  <strong>{selectedRow[4]}</strong>
                </div>
              </div>
            )}

            {detailTab === "Configuration" && (
              <div className="detail-block">
                <h3>Monitoring configuration</h3>
                <p className="text-sm text-slate-600">Simulated configuration for demo workspace.</p>
                <Button variant="secondary" onClick={() => navigate("integrations")}>
                  Open Integrations
                </Button>
              </div>
            )}

            <div className="drawer-actions">
              <Button
                variant="secondary"
                icon="activity"
                onClick={() => {
                  setTesting("running");
                  window.setTimeout(() => setTesting("success"), 800);
                }}
              >
                {testing === "running" ? "Testing…" : "Test connection"}
              </Button>
              <Button onClick={() => navigate("graph")} icon="arrow">
                Open AI Dependency Graph
              </Button>
            </div>

            {testing === "success" && (
              <p className="text-xs text-emerald-700 font-medium">Connection verified successfully.</p>
            )}

            <Button variant="danger" onClick={() => setConfirmDelete(true)}>
              Delete dependency
            </Button>
          </aside>
        </div>
      )}

      {showAdd && (
        <div className="modal-scrim" onClick={() => setShowAdd(false)}>
          <section className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="drawer-head">
              <button className="page-back" onClick={() => setShowAdd(false)}>
                <Icon name="arrow" className="rotate-180" size={14} /> Back
              </button>
              <h2>Add Dependency · {addStep} of 2</h2>
              <Button variant="icon" icon="close" onClick={() => setShowAdd(false)} />
            </div>

            {addStep === 1 && (
              <>
                <p className="modal-intro">Configure the external API and monitored endpoint.</p>
                <label className="form-label">
                  Service name
                  <input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Mapbox" />
                </label>
                <label className="form-label">
                  Base URL
                  <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="api.mapbox.com" />
                </label>
                <div className="form-row">
                  <label className="form-label">
                    HTTP method
                    <select value={httpMethod} onChange={(e) => setHttpMethod(e.target.value)}>
                      <option>GET</option>
                      <option>POST</option>
                      <option>PUT</option>
                      <option>DELETE</option>
                    </select>
                  </label>
                  <label className="form-label">
                    Endpoint path
                    <input value={endpoint} onChange={(e) => setEndpoint(e.target.value)} placeholder="/geocoding/v5" />
                  </label>
                </div>
              </>
            )}

            {addStep === 2 && (
              <>
                <p className="modal-intro">Review dependency settings and baseline.</p>
                <div className="p-3 bg-stone-50 rounded border border-stone-200 text-xs">
                  <div><strong>Name:</strong> {name}</div>
                  <div><strong>Endpoint:</strong> {httpMethod} {url}{endpoint}</div>
                </div>
              </>
            )}

            {formError && <p className="text-xs text-red-600 font-semibold">{formError}</p>}

            <div className="modal-actions">
              <Button variant="ghost" onClick={() => (addStep === 1 ? setShowAdd(false) : setAddStep(1))}>
                {addStep === 1 ? "Cancel" : "Back"}
              </Button>
              <Button onClick={() => (addStep === 1 ? setAddStep(2) : addDependency())}>
                {addStep === 2 ? "Add dependency" : "Continue"}
              </Button>
            </div>
          </section>
        </div>
      )}

      {confirmDelete && (
        <div className="modal-scrim" onClick={() => setConfirmDelete(false)}>
          <section className="modal" onClick={(e) => e.stopPropagation()}>
            <h2>Delete {selected}?</h2>
            <p className="modal-intro">This removes the dependency from local demo monitoring.</p>
            <div className="modal-actions">
              <Button variant="ghost" onClick={() => setConfirmDelete(false)}>
                Cancel
              </Button>
              <Button variant="danger" onClick={removeDependency}>
                Delete dependency
              </Button>
            </div>
          </section>
        </div>
      )}

      {toast && (
        <div className="toast">
          <Icon name="check" />
          <span>
            <strong>Dependency updated</strong>
            <small>{toast}</small>
          </span>
          <Button variant="icon" icon="close" onClick={() => setToast("")} />
        </div>
      )}
    </>
  );
}
