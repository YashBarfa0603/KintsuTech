"use client";

import React, { useState } from "react";
import { GraphData, GraphNode, GraphNodeKind, Screen } from "@/types";
import { Button, Badge, Field, Select } from "@/components/ui/Primitives";
import { Icon } from "@/components/ui/Icons";
import { graphDependencyType, dependencyIcon } from "@/lib/data";

export function ImpactGraphScreen({
  navigate,
  caseStatus,
  validationState,
  graphData,
  setGraphData,
  currentProject = "Pulse API",
  currentEnv = "Staging",
}: {
  navigate: (s: Screen) => void;
  caseStatus: string;
  validationState: string;
  graphData: GraphData;
  setGraphData: (data: GraphData) => void;
  currentProject?: string;
  currentEnv?: string;
}) {
  const [selectedId, setSelectedId] = useState<string | null>("api-payment");
  const [tracing, setTracing] = useState(false);
  const [scale, setScale] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });

  const columns: Record<GraphNodeKind, GraphNode[]> = {
    application: graphData.nodes.filter((n) => n.kind === "application"),
    api: graphData.nodes.filter((n) => n.kind === "api"),
    dependency: graphData.nodes.filter((n) => n.kind === "dependency"),
  };

  const columnX: Record<GraphNodeKind, number> = { application: 50, api: 400, dependency: 780 };
  const positions = new Map<string, { x: number; y: number }>();

  (Object.keys(columns) as GraphNodeKind[]).forEach((kind) => {
    columns[kind].forEach((node, index) => {
      positions.set(node.id, { x: columnX[kind], y: 80 + index * 96 });
    });
  });

  const selectedNode = graphData.nodes.find((n) => n.id === selectedId);

  return (
    <>
      <div className="page-header">
        <div className="page-heading-wrap">
          <button className="page-back" onClick={() => navigate("overview")}>
            <Icon name="arrow" className="rotate-180" size={14} /> Back
          </button>
          <div>
            <div className="breadcrumbs">
              <span>{currentProject.toUpperCase()}</span>
              <Icon name="chevron" size={10} />
              <span>{currentEnv.toUpperCase()}</span>
              <Icon name="chevron" size={10} />
              <span>AI DEPENDENCY GRAPH</span>
              <span className="ml-1"><Badge tone="neutral">IMPACT MODEL</Badge></span>
            </div>
            <h1>AI Dependency Graph</h1>
            <p>
              Explore applications, external dependencies, and established component relationships.
            </p>
          </div>
        </div>
        <div className="page-actions">
          <Button variant="secondary" icon="graph" onClick={() => setTracing(!tracing)}>
            {tracing ? "Clear trace" : "Trace impact"}
          </Button>
          <Button variant="primary" icon="recovery" onClick={() => navigate("recovery")}>
            Open Recovery Case
          </Button>
        </div>
      </div>

      <div className="p-3 bg-white border border-stone-200 rounded-md mb-4 flex items-center justify-between text-xs text-stone-600">
        <div className="flex items-center gap-4">
          <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded bg-blue-600" /> Application</span>
          <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded bg-amber-600" /> External API</span>
          <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded bg-emerald-600" /> Component / Service</span>
          <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded bg-red-500" /> Affected by change</span>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="ghost" className="text-xs h-7 px-2" onClick={() => setScale(Math.max(0.6, scale - 0.1))}>−</Button>
          <span>{Math.round(scale * 100)}%</span>
          <Button variant="ghost" className="text-xs h-7 px-2" onClick={() => setScale(Math.min(1.5, scale + 0.1))}>+</Button>
          <Button variant="ghost" className="text-xs h-7 px-2" onClick={() => { setScale(1); setPan({ x: 0, y: 0 }); }}>Reset</Button>
        </div>
      </div>

      <div className="flex gap-4">
        <div className="flex-1 panel relative overflow-hidden bg-stone-50 border border-stone-200 rounded-md h-[600px]">
          <div
            className="w-[1050px] h-[580px] absolute"
            style={{ transform: `translate(${pan.x}px, ${pan.y}px) scale(${scale})`, transformOrigin: "top left" }}
          >
            {/* Headers */}
            <div className="absolute left-[50px] top-4 text-xs font-bold text-stone-500 uppercase">
              01 Applications ({columns.application.length})
            </div>
            <div className="absolute left-[400px] top-4 text-xs font-bold text-stone-500 uppercase">
              02 External Dependencies ({columns.api.length})
            </div>
            <div className="absolute left-[780px] top-4 text-xs font-bold text-stone-500 uppercase">
              03 Dependency Components ({columns.dependency.length})
            </div>

            {/* SVG Edges */}
            <svg className="absolute inset-0 w-full h-full pointer-events-none">
              <defs>
                <marker id="arrow" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
                  <path d="M0,0 L6,3 L0,6 z" fill="#94A3B8" />
                </marker>
              </defs>
              {graphData.edges.map((edge) => {
                const from = positions.get(edge.from);
                const to = positions.get(edge.to);
                if (!from || !to) return null;
                const d = `M ${from.x + 220} ${from.y + 30} C ${from.x + 300} ${from.y + 30}, ${to.x - 80} ${to.y + 30}, ${to.x} ${to.y + 30}`;
                const isAffected = edge.status === "affected";
                return (
                  <g key={edge.id}>
                    <path
                      d={d}
                      fill="none"
                      stroke={isAffected ? "#EF4444" : "#94A3B8"}
                      strokeWidth={isAffected ? 2.5 : 1.5}
                      strokeDasharray={isAffected ? "4 3" : undefined}
                      markerEnd="url(#arrow)"
                    />
                    <text
                      x={(from.x + 220 + to.x) / 2}
                      y={(from.y + to.y) / 2 + 20}
                      fill="#64748B"
                      fontSize="10"
                      textAnchor="middle"
                    >
                      {edge.label}
                    </text>
                  </g>
                );
              })}
            </svg>

            {/* Nodes */}
            {(Object.keys(columns) as GraphNodeKind[]).map((kind) =>
              columns[kind].map((node) => {
                const pos = positions.get(node.id)!;
                const isSelected = selectedId === node.id;
                const isAffected = node.status === "affected";

                return (
                  <button
                    key={node.id}
                    onClick={() => setSelectedId(node.id)}
                    style={{ left: pos.x, top: pos.y }}
                    className={`absolute w-[220px] p-3 rounded-md bg-white border text-left transition-all shadow-sm ${
                      isSelected
                        ? "border-amber-600 ring-2 ring-amber-200"
                        : isAffected
                        ? "border-red-300 bg-red-50/40"
                        : "border-stone-200 hover:border-stone-400"
                    }`}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-[10px] font-semibold text-stone-500 uppercase">{node.subtype}</span>
                      <Badge tone={isAffected ? "danger" : "success"}>{node.status}</Badge>
                    </div>
                    <div className="font-bold text-sm text-stone-900 truncate">{node.name}</div>
                    <code className="text-[11px] text-stone-500 font-mono block truncate">{node.detail}</code>
                  </button>
                );
              })
            )}
          </div>
        </div>

        {selectedNode && (
          <aside className="w-[340px] panel p-4 flex flex-col gap-3">
            <div className="flex items-center justify-between pb-2 border-b border-stone-200">
              <div>
                <span className="text-[10px] font-bold text-stone-500 uppercase">{selectedNode.kind}</span>
                <h3 className="text-base font-bold text-stone-900">{selectedNode.name}</h3>
              </div>
              <Badge tone={selectedNode.status === "affected" ? "danger" : "success"}>
                {selectedNode.status}
              </Badge>
            </div>

            <div className="text-xs text-stone-600">
              <strong>Detail:</strong> <code>{selectedNode.detail}</code>
            </div>

            <div className="p-3 bg-stone-50 rounded border border-stone-200 text-xs">
              <strong className="block mb-1 text-stone-800">Evidence</strong>
              <p className="text-stone-600">{selectedNode.evidence || "Developer-defined relationship"}</p>
            </div>

            {selectedNode.status === "affected" && (
              <div className="p-3 bg-red-50 border border-red-200 rounded text-xs text-red-800">
                <strong>Anomalous Impact</strong>
                <p className="mt-1">
                  Observed divergence in upstream service affects downstream workflows.
                </p>
              </div>
            )}

            <div className="mt-auto flex flex-col gap-2">
              <Button onClick={() => navigate("recovery")} icon="recovery">
                Open Recovery Case
              </Button>
              <Button variant="secondary" onClick={() => navigate("changes")}>
                View Change Details
              </Button>
            </div>
          </aside>
        )}
      </div>
    </>
  );
}
