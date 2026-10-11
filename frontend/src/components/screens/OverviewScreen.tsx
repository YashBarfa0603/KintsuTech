"use client";

import React, { useState } from "react";
import { ChangeRecord, DependencyType, GraphData, Project, Screen } from "@/types";
import { Button, Badge, Select } from "@/components/ui/Primitives";
import { Icon } from "@/components/ui/Icons";
import { dependencyType, dependencyMeta, incidentIdForChange } from "@/lib/data";

export function OverviewScreen({
  navigate,
  caseStatus,
  validationState,
  dependencies,
  changes,
  graphData,
  projects,
  currentProject = "Pulse API",
  currentEnv = "Staging",
}: {
  navigate: (s: Screen) => void;
  caseStatus: string;
  validationState: string;
  dependencies: string[][];
  changes: ChangeRecord[];
  graphData: GraphData;
  projects: Project[];
  currentProject?: string;
  currentEnv?: string;
}) {
  const [activityFilter, setActivityFilter] = useState("All activity");

  const envDeps = dependencies.filter(
    (row) => (row[9] || "Pulse API") === currentProject && (row[10] || dependencyMeta(row[0]).environment) === currentEnv
  );
  const healthy = envDeps.filter((row) => row[3] === "Healthy").length;
  const degraded = envDeps.filter((row) => row[3] === "Degraded" || row[3] === "Watching").length;
  const unknown = envDeps.filter((row) => row[3] === "Unknown").length;

  const activeChanges = changes.filter((c) => c.status !== "Dismissed");

  const recoveryStages = [
    "Change Detected",
    "Impact Analysed",
    "Proposal Generated",
    "Operations Checked",
    "Testing",
    "Awaiting Review",
    "Approved",
    "Deployed",
  ];
  const stageIndex =
    caseStatus === "approved"
      ? 6
      : validationState === "done"
      ? 5
      : validationState === "running" || validationState === "failed"
      ? 4
      : 3;

  return (
    <>
      <div className="page-header">
        <div className="page-heading-wrap">
          <div>
            <div className="breadcrumbs">
              <span>{currentProject.toUpperCase()}</span>
              <Icon name="chevron" size={10} />
              <span>{currentEnv.toUpperCase()}</span>
              <Icon name="chevron" size={10} />
              <span>OVERVIEW</span>
              <span className="ml-1"><Badge tone="neutral">MONITORED</Badge></span>
            </div>
            <h1>Overview</h1>
            <p>
              Monitor your dependencies, investigate changes, and track recovery · {currentProject} · {currentEnv}
            </p>
          </div>
        </div>
        <div className="page-actions">
          <Badge tone="neutral">Protected Workspace</Badge>
        </div>
      </div>

      <div className="p-3 bg-white border border-stone-200 rounded-md mb-6 flex items-center justify-between">
        <span className="text-xs font-bold text-stone-500 tracking-wider">QUICK ACTIONS</span>
        <div className="flex gap-2">
          <Button variant="secondary" icon="plus" onClick={() => navigate("dependencies")}>
            Add Dependency
          </Button>
          <Button variant="secondary" icon="activity" onClick={() => navigate("changes")}>
            Review Changes
          </Button>
          <Button variant="secondary" icon="graph" onClick={() => navigate("graph")}>
            Explore AI Dependency Graph
          </Button>
          <Button variant="secondary" icon="test" onClick={() => navigate("validation")}>
            Run Validation
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-4 gap-4 mb-6">
        <div
          onClick={() => navigate("dependencies")}
          className="p-4 bg-white border border-stone-200 rounded-md cursor-pointer hover:border-stone-400 transition-colors"
        >
          <div className="text-xs text-stone-500 mb-1">Monitored Dependencies</div>
          <div className="text-2xl font-bold text-stone-900">{envDeps.length}</div>
          <div className="text-xs text-stone-400 mt-1">{currentEnv} active endpoints</div>
        </div>
        <div
          onClick={() => navigate("dependencies")}
          className="p-4 bg-white border border-stone-200 rounded-md cursor-pointer hover:border-stone-400 transition-colors"
        >
          <div className="text-xs text-stone-500 mb-1">Healthy / At Risk / Unknown</div>
          <div className="text-2xl font-bold text-stone-900">
            {healthy} / {degraded} / {unknown}
          </div>
          <div className="text-xs text-stone-400 mt-1">Operational snapshot</div>
        </div>
        <div
          onClick={() => navigate("changes")}
          className="p-4 bg-white border border-stone-200 rounded-md cursor-pointer hover:border-stone-400 transition-colors"
        >
          <div className="text-xs text-stone-500 mb-1">Changes Detected</div>
          <div className="text-2xl font-bold text-amber-700">{activeChanges.length}</div>
          <div className="text-xs text-stone-400 mt-1">1 potentially breaking</div>
        </div>
        <div
          onClick={() => navigate("history")}
          className="p-4 bg-white border border-stone-200 rounded-md cursor-pointer hover:border-stone-400 transition-colors"
        >
          <div className="text-xs text-stone-500 mb-1">Pending Reviews</div>
          <div className="text-2xl font-bold text-stone-900">
            {caseStatus === "approved" ? 0 : 1}
          </div>
          <div className="text-xs text-stone-400 mt-1">Developer decision gate</div>
        </div>
      </div>

      <section className="panel mb-6">
        <div className="p-4 border-b border-stone-200 flex items-center justify-between">
          <div>
            <div className="text-xs font-bold text-stone-500 uppercase tracking-wider">OPERATIONS</div>
            <h2 className="text-base font-bold text-stone-900">Needs Attention</h2>
          </div>
          <Button variant="ghost" onClick={() => navigate("changes")}>
            View all changes
          </Button>
        </div>
        <div className="divide-y divide-stone-200">
          {activeChanges.map((change) => (
            <div
              key={change.id}
              onClick={() => navigate("recovery")}
              className="p-4 flex items-center justify-between hover:bg-stone-50 cursor-pointer"
            >
              <div className="flex items-start gap-3">
                <span className="p-2 bg-red-100 text-red-700 rounded mt-0.5">
                  <Icon name="alert" size={16} />
                </span>
                <div>
                  <div className="text-xs text-stone-500">
                    {change.id} · {change.category}
                  </div>
                  <strong className="text-sm text-stone-900">
                    {change.service} · {change.summary}
                  </strong>
                  <div className="text-xs text-stone-600 font-mono mt-0.5">{change.endpoint}</div>
                </div>
              </div>
              <div className="flex items-center gap-4">
                <Badge tone={change.breaking ? "danger" : "warning"}>{change.severity}</Badge>
                <Badge tone={caseStatus === "approved" ? "success" : "gold"}>
                  {caseStatus === "approved" ? "Approved" : "Awaiting review"}
                </Badge>
                <Icon name="chevron" size={14} />
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="panel p-5 mb-6">
        <div className="flex items-center justify-between mb-4">
          <div>
            <div className="text-xs font-bold text-stone-500 uppercase tracking-wider">
              ACTIVE RECOVERY · KIN-2841
            </div>
            <h2 className="text-base font-bold text-stone-900">
              Payment API compatibility repair
            </h2>
          </div>
          <Badge tone={caseStatus === "approved" ? "success" : "gold"}>
            {caseStatus === "approved" ? "Approved · not deployed" : "Awaiting developer review"}
          </Badge>
        </div>

        <div className="grid grid-cols-8 gap-2 mb-4">
          {recoveryStages.map((stg, i) => (
            <div
              key={stg}
              className={`p-2 rounded text-center text-xs ${
                i < stageIndex
                  ? "bg-emerald-100 text-emerald-800 font-semibold"
                  : i === stageIndex
                  ? "bg-amber-100 text-amber-800 font-bold border border-amber-300"
                  : "bg-stone-100 text-stone-400"
              }`}
            >
              <div className="mb-1">{i < stageIndex ? "✓" : i + 1}</div>
              <div className="truncate">{stg}</div>
            </div>
          ))}
        </div>

        <div className="flex justify-end">
          <Button onClick={() => navigate("recovery")} icon="arrow">
            Continue recovery
          </Button>
        </div>
      </section>
    </>
  );
}
