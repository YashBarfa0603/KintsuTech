"use client";

import React, { useState } from "react";
import { Screen } from "@/types";
import { Button, Badge, Field, Select } from "@/components/ui/Primitives";
import { Icon } from "@/components/ui/Icons";

export function HistoryScreen({
  caseStatus = "Pending review",
  validationState = "done",
  navigate,
}: {
  caseStatus?: string;
  validationState?: string;
  navigate: (s: Screen) => void;
}) {
  const [search, setSearch] = useState("");
  const [decision, setDecision] = useState("All decisions");
  const [severity, setSeverity] = useState("All severities");
  const [dependencyKind, setDependencyKind] = useState("All dependency types");
  const [sort, setSort] = useState("Newest first");
  const [limit, setLimit] = useState(3);
  const [selectedReport, setSelectedReport] = useState<string | null>(null);

  const allIncidents = [
    [
      "KIN-2841",
      "Stripe",
      "GET /v1/payment_intents/:id",
      "Today, 14:14",
      "name → display_name",
      "3",
      validationState === "done" ? "14 / 14 passed" : "Validation running",
      caseStatus === "approved" ? "Approved" : "Pending review",
      "Critical",
      "API",
    ],
    [
      "KIN-2794",
      "SendGrid",
      "POST /v3/mail/send",
      "May 22, 09:42",
      "Rate limit header changed",
      "1",
      "8 / 8 passed",
      "Monitoring",
      "Medium",
      "API",
    ],
    [
      "KIN-SDK-102",
      "Stripe SDK",
      "confirmPayment · npm",
      "Today, 11:48",
      "Method signature changed",
      "1",
      "Infrastructure unavailable",
      "Pending review",
      "High",
      "SDK",
    ],
    [
      "KIN-MCP-104",
      "Travel Tools MCP",
      "search_flights tool",
      "Today, 10:32",
      "Input schema changed",
      "1",
      "Infrastructure unavailable",
      "Pending review",
      "Medium",
      "MCP Server",
    ],
    [
      "KIN-WHK-108",
      "Stripe Payment Webhook",
      "payment.succeeded",
      "Today, 09:18",
      "Reported payload field renamed",
      "2",
      "Infrastructure unavailable",
      "Pending review",
      "High",
      "Webhook",
    ],
    [
      "KIN-2711",
      "GitHub",
      "GET /repos/:owner/:repo",
      "May 18, 16:08",
      "Nullability changed",
      "3",
      "12 / 12 passed",
      "Recovered",
      "High",
      "API",
    ],
    [
      "KIN-2689",
      "Mapbox",
      "GET /geocoding/v5",
      "May 14, 11:22",
      "Default locale changed",
      "1",
      "5 / 6 failed",
      "Rejected",
      "Low",
      "API",
    ],
    [
      "KIN-2632",
      "Twilio",
      "POST /Messages.json",
      "May 09, 08:10",
      "Error payload expanded",
      "1",
      "6 / 6 passed",
      "Recovered",
      "Medium",
      "API",
    ],
  ];

  const incidents = allIncidents
    .filter(
      (x) =>
        x.join(" ").toLowerCase().includes(search.toLowerCase()) &&
        (dependencyKind === "All dependency types" || x[9] === dependencyKind) &&
        (decision === "All decisions" || x[7] === decision) &&
        (severity === "All severities" || x[8] === severity)
    )
    .sort((a, b) => {
      if (sort === "Incident ID") return a[0].localeCompare(b[0]);
      if (sort === "Service") return a[1].localeCompare(b[1]);
      return 0;
    });

  const current = allIncidents.find((incident) => incident[0] === selectedReport);

  const exportReport = (incident = current) => {
    const reportText = incident
      ? `KintsuTech Incident Report\n\nIncident: ${incident[0]}\nService: ${incident[1]}\nEndpoint: ${incident[2]}\nChange: ${incident[4]}\nSeverity: ${incident[8]}\nValidation: ${incident[6]}\nDecision: ${incident[7]}\n`
      : `KintsuTech Recovery History\n\n${incidents.map((r) => `${r[0]} | ${r[1]} | ${r[4]} | ${r[7]}`).join("\n")}`;

    const blob = new Blob([reportText], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = incident ? `${incident[0]}-report.txt` : "kintsutech-history.txt";
    link.click();
    URL.revokeObjectURL(url);
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
              <span>RECOVERY HISTORY</span>
              <span className="ml-1"><Badge tone="neutral">STAGING API</Badge></span>
            </div>
            <h1>Recovery History</h1>
            <p>Review recovery decisions, evidence, and audit history.</p>
          </div>
        </div>
        <div className="page-actions">
          <Button variant="secondary" icon="download" onClick={() => exportReport(undefined)}>
            Export filtered history
          </Button>
        </div>
      </div>

      <section className="panel table-panel">
        <div className="table-tools">
          <Field
            value={search}
            onChange={setSearch}
            placeholder="Search incidents"
            icon="search"
          />
          <Select value={dependencyKind} onChange={setDependencyKind}>
            <option>All dependency types</option>
            <option>API</option>
            <option>SDK</option>
            <option>MCP Server</option>
            <option>Webhook</option>
          </Select>
          <Select value={decision} onChange={setDecision}>
            <option>All decisions</option>
            <option>Pending review</option>
            <option>Monitoring</option>
            <option>Approved</option>
            <option>Recovered</option>
            <option>Rejected</option>
          </Select>
          <Select value={severity} onChange={setSeverity}>
            <option>All severities</option>
            <option>Critical</option>
            <option>High</option>
            <option>Medium</option>
            <option>Low</option>
          </Select>
          <Select value={sort} onChange={setSort}>
            <option>Newest first</option>
            <option>Incident ID</option>
            <option>Service</option>
          </Select>
        </div>

        {incidents.length === 0 ? (
          <div className="empty-state">
            <Icon name="history" />
            <h3>No recovery records found</h3>
            <p>Clear filters or broaden the search query.</p>
            <Button
              variant="secondary"
              onClick={() => {
                setSearch("");
                setDecision("All decisions");
                setSeverity("All severities");
                setDependencyKind("All dependency types");
              }}
            >
              Clear filters
            </Button>
          </div>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  {[
                    "Incident",
                    "Type",
                    "Dependency & component",
                    "Detected",
                    "Change",
                    "Severity",
                    "Workflows",
                    "Validation",
                    "Decision",
                    "",
                  ].map((x) => (
                    <th key={x}>{x}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {incidents.slice(0, limit).map((r) => (
                  <tr key={r[0]} onClick={() => setSelectedReport(r[0])}>
                    <td>
                      <strong className="font-mono">{r[0]}</strong>
                    </td>
                    <td>
                      <Badge tone="neutral">{r[9]}</Badge>
                    </td>
                    <td>
                      <strong>{r[1]}</strong>
                      <small className="font-mono">{r[2]}</small>
                    </td>
                    <td>{r[3]}</td>
                    <td>
                      <code className="text-xs">{r[4]}</code>
                    </td>
                    <td>
                      <Badge
                        tone={
                          r[8] === "Critical"
                            ? "danger"
                            : r[8] === "High"
                            ? "warning"
                            : r[8] === "Medium"
                            ? "warning"
                            : "neutral"
                        }
                      >
                        {r[8]}
                      </Badge>
                    </td>
                    <td>{r[5]}</td>
                    <td>
                      <Badge
                        tone={
                          r[6].includes("passed")
                            ? "success"
                            : r[6].includes("failed")
                            ? "danger"
                            : "neutral"
                        }
                      >
                        {r[6]}
                      </Badge>
                    </td>
                    <td>
                      <Badge
                        tone={
                          r[7] === "Approved" || r[7] === "Recovered"
                            ? "success"
                            : r[7] === "Rejected"
                            ? "danger"
                            : "warning"
                        }
                      >
                        {r[7]}
                      </Badge>
                    </td>
                    <td>
                      <Icon name="chevron" size={14} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <div className="table-footer">
          <span>
            Showing {Math.min(limit, incidents.length)} of {incidents.length} matching records
          </span>
          {limit < incidents.length && (
            <Button variant="secondary" onClick={() => setLimit(limit + 3)}>
              Load more
            </Button>
          )}
        </div>
      </section>

      {current && (
        <div className="drawer-scrim" onClick={() => setSelectedReport(null)}>
          <aside className="drawer" onClick={(e) => e.stopPropagation()}>
            <div className="drawer-head">
              <button className="page-back" onClick={() => setSelectedReport(null)}>
                <Icon name="arrow" className="rotate-180" size={14} /> Back
              </button>
              <h2>{current[0]} incident audit report</h2>
              <Button variant="icon" icon="close" onClick={() => setSelectedReport(null)} />
            </div>

            <div className="drawer-status">
              <Badge tone={current[7] === "Approved" ? "success" : "warning"}>{current[7]}</Badge>
              <span>{current[3]} · Audit record</span>
            </div>

            <div className="detail-block">
              <h3>Observed change</h3>
              <code>{current[4]}</code>
              <p className="text-sm text-slate-700 mt-1">
                {current[1]} · {current[2]}
              </p>
            </div>

            <div className="detail-block">
              <h3>Audit assessment</h3>
              <dl>
                <div>
                  <dt>Severity</dt>
                  <dd>{current[8]}</dd>
                </div>
                <div>
                  <dt>Workflows affected</dt>
                  <dd>{current[5]}</dd>
                </div>
                <div>
                  <dt>Validation evidence</dt>
                  <dd>{current[6]}</dd>
                </div>
                <div>
                  <dt>Decision status</dt>
                  <dd>{current[7]}</dd>
                </div>
              </dl>
            </div>

            <div className="drawer-actions">
              <Button variant="secondary" icon="download" onClick={() => exportReport(current)}>
                Export report
              </Button>
              <Button
                onClick={() => {
                  setSelectedReport(null);
                  navigate("recovery");
                }}
                icon="arrow"
              >
                Open recovery case
              </Button>
            </div>
          </aside>
        </div>
      )}
    </>
  );
}
