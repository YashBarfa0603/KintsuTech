"use client";

import React, { useState, useEffect } from "react";
import { Project, Screen, GraphData } from "@/types";
import { Button, Badge, Field } from "@/components/ui/Primitives";
import { Icon } from "@/components/ui/Icons";

export function ProjectsScreen({
  projects,
  setProjects,
  setCurrentProject,
  navigate,
  dependencies,
  setDependencies,
  graphData,
  setGraphData,
}: {
  projects: Project[];
  setProjects: (projects: Project[]) => void;
  setCurrentProject: (name: string) => void;
  navigate: (screen: Screen) => void;
  dependencies: string[][];
  setDependencies: (dependencies: string[][]) => void;
  graphData: GraphData;
  setGraphData: (graphData: GraphData) => void;
}) {
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<Project | null>(null);
  const [showWizard, setShowWizard] = useState(false);
  const [wizardStep, setWizardStep] = useState(1);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [repository, setRepository] = useState("");
  const [owner, setOwner] = useState("");
  const [apiHost, setApiHost] = useState("");
  const [dependencyName, setDependencyName] = useState("Initial API");
  const [applicationName, setApplicationName] = useState("Web App");
  const [applicationType, setApplicationType] = useState("Web application");
  const [testSuite, setTestSuite] = useState("Contract, integration, and regression checks");
  const [baseline, setBaseline] = useState(`{\n  "id": "string",\n  "status": "string"\n}`);
  const [wizardTest, setWizardTest] = useState<"idle" | "running" | "passed">("idle");
  const [error, setError] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<Project | null>(null);
  const [toast, setToast] = useState("");

  const visible = projects.filter((item) =>
    `${item.name} ${item.description} ${item.owner} ${item.repository}`
      .toLowerCase()
      .includes(search.toLowerCase())
  );

  const steps = [
    "Create Project",
    "Register Application",
    "Add Dependency",
    "Define Relationships",
    "Import Contract",
    "Configure Tests",
    "Verify Setup",
    "Open Overview",
  ];

  const continueWizard = () => {
    setError("");
    if (wizardStep === 1 && (!name.trim() || !description.trim() || !owner.trim())) {
      setError("Project name, description, and owner are required.");
      return;
    }
    if (wizardStep === 2 && !applicationName.trim()) {
      setError("Register at least one application before continuing.");
      return;
    }
    if (wizardStep === 3 && (!dependencyName.trim() || !apiHost.includes(".") || !repository.includes("."))) {
      setError("Enter a dependency name, valid API host, and repository link.");
      return;
    }
    if (wizardStep === 5 && !baseline.trim().startsWith("{")) {
      setError("Expected behaviour must be a JSON-shaped object for this demo.");
      return;
    }
    if (wizardStep === 7 && wizardTest !== "passed") {
      setError("Run the simulated connection test before continuing.");
      return;
    }
    if (wizardStep < 8) {
      setWizardStep(wizardStep + 1);
      return;
    }

    const newProject: Project = {
      id: `project-${Date.now()}`,
      name: name.trim(),
      description: description.trim(),
      repository: repository.trim(),
      owner: owner.trim(),
      apis: 1,
      services: 1,
      health: "Unknown",
      incidents: 0,
      members: 1,
    };

    setProjects([...projects, newProject]);
    const normalizedHost = apiHost.trim().replace(/^https?:\/\//, "");
    setDependencies([
      ...dependencies,
      [
        dependencyName.trim(),
        normalizedHost,
        "GET /",
        "Unknown",
        "Monitoring unavailable",
        "—",
        "—",
        "Expected-response baseline saved · unverified",
        "1",
        newProject.name,
        "Staging",
        "API",
        JSON.stringify({ method: "GET", requestConfig: "Secure reference required", baseline, specification: "Project setup input" }),
      ],
    ]);

    const suffix = newProject.id;
    const applicationId = `app-${suffix}`;
    const dependencyId = `api-${suffix}`;
    const componentId = `dep-${suffix}`;

    setGraphData({
      nodes: [
        ...graphData.nodes,
        { id: applicationId, kind: "application", subtype: applicationType, name: applicationName.trim(), detail: repository.trim(), status: "unknown", project: newProject.name, environment: "Staging", evidence: "Registered during project setup", source: "user" },
        { id: dependencyId, kind: "api", subtype: "API", name: dependencyName.trim(), detail: normalizedHost, status: "unknown", project: newProject.name, environment: "Staging", provider: dependencyName.trim(), method: "GET", evidence: "Expected baseline supplied during setup; monitoring unverified", source: "user" },
        { id: componentId, kind: "dependency", subtype: "Endpoint", name: "Initial endpoint", detail: "GET /", status: "unknown", project: newProject.name, environment: "Staging", evidence: "Developer-defined setup relationship", source: "user" },
      ],
      edges: [
        ...graphData.edges,
        { id: `edge-${applicationId}-${dependencyId}`, from: applicationId, to: dependencyId, label: "uses", evidence: "confirmed", source: "Project setup", status: "healthy" },
        { id: `edge-${dependencyId}-${componentId}`, from: dependencyId, to: componentId, label: "calls", evidence: "confirmed", source: "Project setup", status: "healthy" },
      ],
    });

    setCurrentProject(newProject.name);
    setShowWizard(false);
    setWizardStep(1);
    setToast(`${newProject.name} was created successfully.`);
    window.setTimeout(() => setToast(""), 3000);
    navigate("overview");
  };

  const updateSelected = () => {
    if (!selected || !selected.name.trim()) return;
    setProjects(projects.map((item) => (item.id === selected.id ? selected : item)));
    setCurrentProject(selected.name);
    setToast("Project details saved.");
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
              <span>PROJECTS</span>
              <span className="ml-1"><Badge tone="neutral">STAGING API</Badge></span>
            </div>
            <h1>Projects</h1>
            <p>Manage the applications protected by KintsuTech.</p>
          </div>
        </div>
        <div className="page-actions">
          <Button icon="plus" onClick={() => setShowWizard(true)}>
            Create project
          </Button>
        </div>
      </div>

      <div className="project-toolbar panel">
        <Field
          value={search}
          onChange={setSearch}
          placeholder="Search protected applications"
          icon="search"
        />
        <span>{visible.length} protected applications</span>
      </div>

      {visible.length === 0 ? (
        <div className="panel empty-state">
          <Icon name="shield" />
          <h3>No projects match</h3>
          <p>Create the first protected application or clear the current search.</p>
          <Button variant="secondary" onClick={() => setSearch("")}>
            Clear search
          </Button>
        </div>
      ) : (
        <div className="project-grid">
          {visible.map((item) => (
            <article key={item.id} className="project-card panel">
              <div className="project-card-head">
                <span className="project-avatar">{item.name.slice(0, 2).toUpperCase()}</span>
                <Badge tone={item.health === "Healthy" ? "success" : item.health === "Degraded" ? "warning" : "neutral"}>
                  {item.health}
                </Badge>
              </div>
              <h2>{item.name}</h2>
              <p>{item.description}</p>
              <code>{item.repository}</code>
              <dl>
                <div>
                  <dt>Registered APIs</dt>
                  <dd>{item.name === "Pulse API" ? 11 : item.apis}</dd>
                </div>
                <div>
                  <dt>Services</dt>
                  <dd>{item.services}</dd>
                </div>
                <div>
                  <dt>Open incidents</dt>
                  <dd>{item.incidents}</dd>
                </div>
                <div>
                  <dt>Team</dt>
                  <dd>{item.members}</dd>
                </div>
              </dl>
              <div className="project-card-actions">
                <Button variant="secondary" onClick={() => setSelected(item)}>
                  Project details
                </Button>
                <Button
                  onClick={() => {
                    setCurrentProject(item.name);
                    navigate("overview");
                  }}
                  icon="arrow"
                >
                  Open project
                </Button>
              </div>
            </article>
          ))}
        </div>
      )}

      {selected && (
        <div className="drawer-scrim" onClick={() => setSelected(null)}>
          <aside className="drawer" onClick={(e) => e.stopPropagation()}>
            <div className="drawer-head">
              <button className="page-back" onClick={() => setSelected(null)}>
                <Icon name="arrow" className="rotate-180" size={14} /> Back
              </button>
              <h2>{selected.name} project details</h2>
              <Button variant="icon" icon="close" onClick={() => setSelected(null)} />
            </div>
            <div className="drawer-status">
              <Badge tone={selected.health === "Healthy" ? "success" : selected.health === "Degraded" ? "warning" : "neutral"}>
                {selected.health}
              </Badge>
              <span>{selected.incidents} open incidents · {selected.members} members</span>
            </div>
            <div className="form-row">
              <label className="form-label">
                Project name
                <input
                  value={selected.name}
                  onChange={(e) => setSelected({ ...selected, name: e.target.value })}
                />
              </label>
              <label className="form-label">
                Owner
                <input
                  value={selected.owner}
                  onChange={(e) => setSelected({ ...selected, owner: e.target.value })}
                />
              </label>
            </div>
            <label className="form-label">
              Description
              <textarea
                value={selected.description}
                onChange={(e) => setSelected({ ...selected, description: e.target.value })}
              />
            </label>
            <label className="form-label">
              Repository
              <input
                value={selected.repository}
                onChange={(e) => setSelected({ ...selected, repository: e.target.value })}
              />
            </label>
            <div className="detail-block">
              <h3>Environment configuration</h3>
              <div className="detail-list-row">
                <span>Development</span>
                <Badge tone="success">Enabled</Badge>
              </div>
              <div className="detail-list-row">
                <span>Staging</span>
                <Badge tone="success">Enabled</Badge>
              </div>
              <div className="detail-list-row">
                <span>Production</span>
                <Badge tone="gold">Approval protected</Badge>
              </div>
            </div>
            <div className="drawer-actions">
              <Button variant="secondary" onClick={() => navigate("dependencies")}>
                Open dependencies
              </Button>
              <Button variant="secondary" onClick={() => navigate("changes")}>
                Open incidents
              </Button>
              <Button onClick={updateSelected}>Save project</Button>
            </div>
            <Button variant="danger" onClick={() => setDeleteTarget(selected)}>
              Delete project
            </Button>
          </aside>
        </div>
      )}

      {showWizard && (
        <div className="modal-scrim" onClick={() => setShowWizard(false)}>
          <section className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="drawer-head">
              <button className="page-back" onClick={() => setShowWizard(false)}>
                <Icon name="arrow" className="rotate-180" size={14} /> Back
              </button>
              <h2>Project setup · {wizardStep} of 8</h2>
              <Button variant="icon" icon="close" onClick={() => setShowWizard(false)} />
            </div>

            <div className="flex gap-2 mb-4 overflow-x-auto py-1">
              {steps.map((step, index) => (
                <span
                  key={step}
                  className={`text-xs px-2 py-1 rounded whitespace-nowrap ${
                    index + 1 <= wizardStep ? "bg-emerald-100 text-emerald-800 font-semibold" : "bg-slate-100 text-slate-500"
                  }`}
                >
                  {index + 1}. {step}
                </span>
              ))}
            </div>

            {wizardStep === 1 && (
              <>
                <p className="modal-intro">Create the protected project and accountable ownership record.</p>
                <label className="form-label">
                  Project name
                  <input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Merchant Console" />
                </label>
                <label className="form-label">
                  Description
                  <textarea value={description} onChange={(e) => setDescription(e.target.value)} placeholder="What workflows does this protect?" />
                </label>
                <label className="form-label">
                  Owner
                  <input value={owner} onChange={(e) => setOwner(e.target.value)} placeholder="Platform Engineering" />
                </label>
              </>
            )}

            {wizardStep === 2 && (
              <>
                <p className="modal-intro">Register the first application that depends on an external service.</p>
                <div className="form-row">
                  <label className="form-label">
                    Application name
                    <input value={applicationName} onChange={(e) => setApplicationName(e.target.value)} placeholder="Web App" />
                  </label>
                  <label className="form-label">
                    Application type
                    <select value={applicationType} onChange={(e) => setApplicationType(e.target.value)}>
                      <option>Web application</option>
                      <option>Mobile application</option>
                      <option>Admin application</option>
                      <option>Backend service</option>
                    </select>
                  </label>
                </div>
              </>
            )}

            {wizardStep === 3 && (
              <>
                <p className="modal-intro">Add an initial API dependency.</p>
                <label className="form-label">
                  Dependency name
                  <input value={dependencyName} onChange={(e) => setDependencyName(e.target.value)} placeholder="Payments API" />
                </label>
                <label className="form-label">
                  API host
                  <input value={apiHost} onChange={(e) => setApiHost(e.target.value)} placeholder="api.example.com" />
                </label>
                <label className="form-label">
                  Repository reference
                  <input value={repository} onChange={(e) => setRepository(e.target.value)} placeholder="github.com/organization/repo" />
                </label>
              </>
            )}

            {wizardStep === 4 && (
              <>
                <p className="modal-intro">Confirm the explicit relationship.</p>
                <div className="p-3 bg-stone-50 rounded border border-stone-200 text-sm flex items-center justify-between">
                  <span><strong>{applicationName}</strong> ({applicationType})</span>
                  <span>→</span>
                  <span><strong>{dependencyName}</strong> ({apiHost})</span>
                  <span>→</span>
                  <span><strong>Initial endpoint</strong> (GET /)</span>
                </div>
              </>
            )}

            {wizardStep === 5 && (
              <>
                <p className="modal-intro">Import or provide the expected response baseline JSON.</p>
                <label className="form-label">
                  Expected response JSON
                  <textarea value={baseline} onChange={(e) => setBaseline(e.target.value)} className="font-mono text-xs" />
                </label>
              </>
            )}

            {wizardStep === 6 && (
              <>
                <p className="modal-intro">Choose independent validation checks required for future repairs.</p>
                <label className="form-label">
                  Required test suite
                  <select value={testSuite} onChange={(e) => setTestSuite(e.target.value)}>
                    <option>Contract, integration, and regression checks</option>
                    <option>Contract and type checks</option>
                    <option>Payload schema and delivery checks</option>
                  </select>
                </label>
              </>
            )}

            {wizardStep === 7 && (
              <div className="text-center py-4">
                <Icon name={wizardTest === "passed" ? "check" : "activity"} size={32} className="mx-auto mb-2 text-emerald-700" />
                <h3 className="font-bold text-base mb-1">
                  {wizardTest === "passed" ? "Setup verification passed" : "Verify the setup model"}
                </h3>
                <p className="text-sm text-slate-600 mb-4">
                  Checks the supplied project, application, and expected baseline locally.
                </p>
                <Button
                  variant="secondary"
                  disabled={wizardTest === "running"}
                  onClick={() => {
                    setWizardTest("running");
                    window.setTimeout(() => setWizardTest("passed"), 800);
                  }}
                >
                  {wizardTest === "running" ? "Verifying…" : "Run deterministic verification"}
                </Button>
              </div>
            )}

            {wizardStep === 8 && (
              <div className="text-center py-4">
                <Icon name="check" size={36} className="mx-auto mb-2 text-emerald-700" />
                <h3 className="font-bold text-lg mb-1">Project setup is ready</h3>
                <p className="text-sm text-slate-600">
                  {applicationName} and {dependencyName} will be registered in your protected workspace.
                </p>
              </div>
            )}

            {error && <p className="text-xs text-red-600 font-semibold">{error}</p>}

            <div className="modal-actions">
              <Button
                variant="ghost"
                onClick={() => (wizardStep === 1 ? setShowWizard(false) : setWizardStep(wizardStep - 1))}
              >
                {wizardStep === 1 ? "Cancel" : "Back"}
              </Button>
              <Button onClick={continueWizard}>
                {wizardStep === 8 ? "Create and open Overview" : "Continue"}
              </Button>
            </div>
          </section>
        </div>
      )}

      {deleteTarget && (
        <div className="modal-scrim" onClick={() => setDeleteTarget(null)}>
          <section className="modal" onClick={(e) => e.stopPropagation()}>
            <h2>Delete {deleteTarget.name}?</h2>
            <p className="modal-intro">This removes the project from local workspace state.</p>
            <div className="modal-actions">
              <Button variant="ghost" onClick={() => setDeleteTarget(null)}>
                Cancel
              </Button>
              <Button
                variant="danger"
                onClick={() => {
                  setProjects(projects.filter((p) => p.id !== deleteTarget.id));
                  setDeleteTarget(null);
                  setSelected(null);
                  setCurrentProject(projects.find((p) => p.id !== deleteTarget.id)?.name || "Pulse API");
                }}
              >
                Delete project
              </Button>
            </div>
          </section>
        </div>
      )}

      {toast && (
        <div className="toast">
          <Icon name="check" />
          <span>
            <strong>Project updated</strong>
            <small>{toast}</small>
          </span>
          <Button variant="icon" icon="close" onClick={() => setToast("")} />
        </div>
      )}
    </>
  );
}
