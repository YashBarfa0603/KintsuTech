"use client";

import React, { useState, useMemo } from "react";
import { GraphData, GraphNode, GraphNodeKind, Screen } from "@/types";
import { Button, Badge } from "@/components/ui/Primitives";
import { Icon } from "@/components/ui/Icons";

export function ImpactGraphScreen({
  navigate,
  caseStatus,
  validationState,
  graphData,
  setGraphData,
  currentProject = "Pulse API",
  currentEnv = "Production",
}: {
  navigate: (s: Screen) => void;
  caseStatus: string;
  validationState: string;
  graphData: GraphData;
  setGraphData: (data: GraphData) => void;
  currentProject?: string;
  currentEnv?: string;
}) {
  const [selectedId, setSelectedId] = useState<string | null>("app-console");
  const [tracing, setTracing] = useState(false);
  const [scale, setScale] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });

  // Group nodes into the 3 columns matching the design
  const columns = useMemo(() => {
    return {
      application: graphData.nodes.filter((n) => n.kind === "application"),
      api: graphData.nodes.filter((n) => n.kind === "api"),
      dependency: graphData.nodes.filter((n) => n.kind === "dependency"),
    };
  }, [graphData.nodes]);

  // Non-overlapping coordinates with balanced vertical alignment
  const positions = useMemo(() => {
    const map = new Map<string, { x: number; y: number }>();
    const columnX: Record<GraphNodeKind, number> = {
      application: 40,
      api: 410,
      dependency: 780,
    };

    const curatedY: Record<string, number> = {
      // Column 1: Applications
      "app-checkout": 145,
      "app-console": 335,
      "app-scheduler": 430,
      "app-mobile": 575,

      // Column 2: External APIs
      "api-products": 98,
      "api-stripe": 240,
      "api-supabase": 335,
      "api-vapi": 430,
      "api-weather": 575,

      // Column 3: Dependencies
      "dep-catalog": 50,
      "dep-inventory": 145,
      "dep-ledger": 240,
      "dep-rbac": 335,
      "dep-voice-logger": 430,
      "dep-trip": 525,
      "dep-alert": 620,
    };

    columns.application.forEach((node, index) => {
      const y = curatedY[node.id] !== undefined ? curatedY[node.id] : 64 + index * 110;
      map.set(node.id, { x: columnX.application, y });
    });

    columns.api.forEach((node, index) => {
      const y = curatedY[node.id] !== undefined ? curatedY[node.id] : 64 + index * 95;
      map.set(node.id, { x: columnX.api, y });
    });

    columns.dependency.forEach((node, index) => {
      const y = curatedY[node.id] !== undefined ? curatedY[node.id] : 50 + index * 95;
      map.set(node.id, { x: columnX.dependency, y });
    });

    return map;
  }, [columns]);

  const selectedNode = useMemo(() => {
    return graphData.nodes.find((n) => n.id === selectedId) || null;
  }, [graphData.nodes, selectedId]);

  // Find direct connected edges for the selected node
  const connectedEdges = useMemo(() => {
    if (!selectedId) return [];
    return graphData.edges.filter((e) => e.from === selectedId || e.to === selectedId);
  }, [selectedId, graphData.edges]);

  // Calculate transitive downstream blast radius
  const downstreamImpactIds = useMemo(() => {
    if (!selectedId) return new Set<string>();
    const set = new Set<string>();
    const queue = [selectedId];
    while (queue.length > 0) {
      const curr = queue.shift()!;
      graphData.edges
        .filter((e) => e.from === curr)
        .forEach((e) => {
          if (!set.has(e.to)) {
            set.add(e.to);
            queue.push(e.to);
          }
        });
    }
    return set;
  }, [selectedId, graphData.edges]);

  // Check if edge is active in current focus
  const isEdgeActive = (fromId: string, toId: string) => {
    if (!selectedId && !tracing) return false;
    if (selectedId && (fromId === selectedId || toId === selectedId)) return true;
    if (tracing && downstreamImpactIds.has(toId) && (fromId === selectedId || downstreamImpactIds.has(fromId))) return true;
    return false;
  };

  // Connected nodes count for the selected node
  const connectedNodesCount = useMemo(() => {
    if (!selectedId) return 0;
    const connected = new Set<string>();
    graphData.edges.forEach((e) => {
      if (e.from === selectedId) connected.add(e.to);
      if (e.to === selectedId) connected.add(e.from);
    });
    return connected.size;
  }, [selectedId, graphData.edges]);

  // Connected external dependencies count
  const connectedDepsCount = useMemo(() => {
    if (!selectedNode) return 0;
    if (selectedNode.kind === "application") {
      return graphData.edges.filter((e) => e.from === selectedNode.id).length;
    }
    return graphData.edges.filter((e) => e.from === selectedNode.id || e.to === selectedNode.id).length;
  }, [selectedNode, graphData.edges]);

  // Affected workflows count
  const affectedWorkflowsCount = useMemo(() => {
    if (!selectedId) return 0;
    let count = 0;
    downstreamImpactIds.forEach((id) => {
      const node = graphData.nodes.find((n) => n.id === id);
      if (node && node.status === "affected") count++;
    });
    return count;
  }, [selectedId, downstreamImpactIds, graphData.nodes]);

  // Canvas height to fit all cards with padding
  const canvasHeight = useMemo(() => {
    const maxNodes = Math.max(columns.application.length, columns.api.length, columns.dependency.length);
    return Math.max(760, maxNodes * 96 + 140);
  }, [columns]);

  return (
    <>
      {/* Top Legend and Controls Bar (Matches Image) */}
      <div className="bg-white border-b border-stone-200 px-4 py-2.5 flex items-center justify-between text-xs">
        {/* Left: Legend */}
        <div className="flex items-center gap-4 text-stone-600 flex-wrap">
          <span className="flex items-center gap-1.5 font-medium">
            <span className="w-2.5 h-2.5 rounded-sm border border-blue-500 bg-blue-50" /> Application
          </span>
          <span className="flex items-center gap-1.5 font-medium">
            <span className="w-2.5 h-2.5 rounded-sm border border-amber-500 bg-amber-50" /> API / SDK / MCP
          </span>
          <span className="flex items-center gap-1.5 font-medium">
            <span className="w-2.5 h-2.5 rounded-sm border border-teal-500 bg-teal-50" /> Dependency component
          </span>
          <span className="flex items-center gap-1.5 font-medium text-stone-500">
            <span className="w-4 h-0.5 bg-stone-400" /> Confirmed
          </span>
          <span className="flex items-center gap-1.5 font-medium text-stone-500">
            <span className="w-4 h-0.5 border-t border-dashed border-stone-400" /> Inferred
          </span>
          <span className="flex items-center gap-1.5 font-medium text-red-600">
            <span className="w-2 h-2 rounded-full bg-red-500" /> Affected
          </span>
        </div>

        {/* Right: Actions */}
        <div className="flex items-center gap-3">
          <button
            className="text-xs text-stone-500 hover:text-stone-800 transition-colors font-medium px-1"
            onClick={() => setSelectedId(null)}
          >
            Clear selection
          </button>
          <Button
            variant={tracing ? "primary" : "secondary"}
            className="text-xs h-7 px-3 font-medium"
            icon="graph"
            onClick={() => setTracing(!tracing)}
          >
            Trace Impact
          </Button>
          <button
            className="text-xs text-stone-500 hover:text-stone-800 transition-colors font-medium px-1"
            onClick={() => setTracing(false)}
          >
            Clear trace
          </button>
        </div>
      </div>

      {/* Main Canvas + Right Drawer Workspace */}
      <div className="flex h-[calc(100vh-140px)] min-h-[640px] bg-white overflow-hidden">
        {/* Graph Canvas */}
        <div className="flex-1 relative overflow-auto bg-[radial-gradient(#d1d5db_1.2px,transparent_1.2px)] [background-size:18px_18px] bg-stone-50/70 border-r border-stone-200">
          <div
            className="w-[1040px] relative transition-transform duration-75 origin-top-left"
            style={{
              height: `${canvasHeight}px`,
              transform: `translate(${pan.x}px, ${pan.y}px) scale(${scale})`,
            }}
          >
            {/* Column Headers matching image */}
            <div className="absolute left-[40px] top-4 text-xs">
              <div className="font-bold text-stone-900 tracking-tight">Applications</div>
              <div className="text-[11px] text-stone-500">{columns.application.length} nodes</div>
            </div>

            <div className="absolute left-[380px] top-4 text-xs">
              <div className="font-bold text-stone-900 tracking-tight">External Dependencies</div>
              <div className="text-[11px] text-stone-500">{columns.api.length} APIs, SDKs, MCP servers, or webhooks</div>
            </div>

            <div className="absolute left-[740px] top-4 text-xs">
              <div className="font-bold text-stone-900 tracking-tight">Dependency Components</div>
              <div className="text-[11px] text-stone-500">{columns.dependency.length} endpoints, methods, tools, or schemas</div>
            </div>

            {/* SVG Edges with Non-Overlapping Cubic Curves */}
            <svg className="absolute inset-0 w-full h-full pointer-events-none">
              <defs>
                <marker id="arrow-default" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
                  <path d="M0,0 L6,3 L0,6 z" fill="#94A3B8" />
                </marker>
                <marker id="arrow-active" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
                  <path d="M0,0 L6,3 L0,6 z" fill="#0284C7" />
                </marker>
                <marker id="arrow-affected" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
                  <path d="M0,0 L6,3 L0,6 z" fill="#EF4444" />
                </marker>
              </defs>

              {(() => {
                return graphData.edges.map((edge) => {
                  const from = positions.get(edge.from);
                  const to = positions.get(edge.to);
                  if (!from || !to) return null;

                  const isAffected = edge.status === "affected";
                  const isActive = isEdgeActive(edge.from, edge.to);

                  // Card center Y is y + 36 (cards are ~72px high)
                  const startX = from.x + 250;
                  const startY = from.y + 36;
                  const endX = to.x;
                  const endY = to.y + 36;

                  const dx = Math.max(50, endX - startX);
                  const controlX1 = startX + dx * 0.45;
                  const controlX2 = endX - dx * 0.45;

                  const pathData = `M ${startX} ${startY} C ${controlX1} ${startY}, ${controlX2} ${endY}, ${endX} ${endY}`;

                  // Opacity: if something is selected or tracing, dim non-active edges
                  const hasFocus = Boolean(selectedId || tracing);
                  const opacity = hasFocus ? (isActive ? 1 : 0.15) : 0.8;

                  return (
                    <g key={edge.id} opacity={opacity} className="transition-opacity duration-150">
                      <path
                        d={pathData}
                        fill="none"
                        stroke={isAffected ? "#EF4444" : isActive ? "#0284C7" : "#94A3B8"}
                        strokeWidth={isAffected || isActive ? 2.2 : 1.3}
                        strokeDasharray={edge.evidence === "inferred" ? "4 3" : undefined}
                        markerEnd={isAffected ? "url(#arrow-affected)" : isActive ? "url(#arrow-active)" : "url(#arrow-default)"}
                      />
                      {/* Edge Label on hover / active */}
                      {isActive && (
                        <text
                          x={(startX + endX) / 2}
                          y={(startY + endY) / 2 - 6}
                          fill={isAffected ? "#B91C1C" : "#0369A1"}
                          fontSize="9"
                          fontFamily="sans-serif"
                          textAnchor="middle"
                          className="font-medium"
                        >
                          <tspan
                            dy="0"
                            fill="white"
                            stroke="white"
                            strokeWidth="3"
                            paintOrder="stroke"
                          >
                            {edge.label}
                          </tspan>
                        </text>
                      )}
                    </g>
                  );
                });
              })()}
            </svg>

            {/* Column 1: Applications */}
            {columns.application.map((node) => {
              const pos = positions.get(node.id);
              if (!pos) return null;
              const isSelected = selectedId === node.id;
              const isAffected = node.status === "affected";
              const isConnected = selectedId ? isEdgeActive(node.id, selectedId) || isEdgeActive(selectedId, node.id) : true;
              const opacity = selectedId && !isSelected && !isConnected ? "opacity-45" : "opacity-100";

              return (
                <div
                  key={node.id}
                  onClick={() => setSelectedId(node.id)}
                  style={{ left: pos.x, top: pos.y }}
                  className={`absolute w-[250px] p-2.5 rounded bg-white border text-left cursor-pointer transition-all shadow-xs ${
                    isSelected
                      ? "border-blue-600 ring-2 ring-blue-200/80 shadow-sm"
                      : isAffected
                      ? "border-red-300 bg-red-50/40 hover:border-red-400"
                      : "border-stone-200 hover:border-stone-400"
                  } ${opacity}`}
                >
                  <div className="flex items-center gap-2">
                    <div className="w-6 h-6 rounded bg-blue-50 border border-blue-200 flex items-center justify-center text-blue-700 shrink-0">
                      <Icon name="home" size={13} />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="text-[9px] font-bold text-stone-400 uppercase tracking-wider truncate">
                        {node.subtype}
                      </div>
                      <div className="font-bold text-xs text-stone-900 truncate">
                        {node.name}
                      </div>
                      <div className="text-[10px] text-stone-500 truncate">
                        {node.detail}
                      </div>
                    </div>
                    {isAffected && (
                      <span className="w-2 h-2 rounded-full bg-red-500 shrink-0 self-start mt-0.5" />
                    )}
                  </div>
                </div>
              );
            })}

            {/* Column 2: External Dependencies */}
            {columns.api.map((node) => {
              const pos = positions.get(node.id);
              if (!pos) return null;
              const isSelected = selectedId === node.id;
              const isAffected = node.status === "affected";
              const isConnected = selectedId ? isEdgeActive(node.id, selectedId) || isEdgeActive(selectedId, node.id) : true;
              const opacity = selectedId && !isSelected && !isConnected ? "opacity-45" : "opacity-100";

              return (
                <div
                  key={node.id}
                  onClick={() => setSelectedId(node.id)}
                  style={{ left: pos.x, top: pos.y }}
                  className={`absolute w-[250px] p-2.5 rounded bg-white border text-left cursor-pointer transition-all shadow-xs ${
                    isSelected
                      ? "border-amber-600 ring-2 ring-amber-200/80 shadow-sm"
                      : isAffected
                      ? "border-red-300 bg-red-50/40 hover:border-red-400"
                      : "border-stone-200 hover:border-stone-400"
                  } ${opacity}`}
                >
                  <div className="flex items-center gap-2">
                    <div className="w-6 h-6 rounded bg-amber-50 border border-amber-200 flex items-center justify-center text-amber-700 shrink-0">
                      <Icon name="api" size={13} />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="text-[9px] font-bold text-stone-400 uppercase tracking-wider truncate">
                        {node.subtype}
                      </div>
                      <div className="font-bold text-xs text-stone-900 truncate">
                        {node.name}
                      </div>
                      <div className="text-[10px] text-stone-500 font-mono truncate">
                        {node.detail}
                      </div>
                    </div>
                    {isAffected && (
                      <span className="w-2 h-2 rounded-full bg-red-500 shrink-0 self-start mt-0.5 animate-pulse" />
                    )}
                  </div>
                </div>
              );
            })}

            {/* Column 3: Dependency Components */}
            {columns.dependency.map((node) => {
              const pos = positions.get(node.id);
              if (!pos) return null;
              const isSelected = selectedId === node.id;
              const isAffected = node.status === "affected";
              const isConnected = selectedId ? isEdgeActive(node.id, selectedId) || isEdgeActive(selectedId, node.id) : true;
              const opacity = selectedId && !isSelected && !isConnected ? "opacity-45" : "opacity-100";

              return (
                <div
                  key={node.id}
                  onClick={() => setSelectedId(node.id)}
                  style={{ left: pos.x, top: pos.y }}
                  className={`absolute w-[250px] p-2.5 rounded bg-white border text-left cursor-pointer transition-all shadow-xs ${
                    isSelected
                      ? "border-teal-600 ring-2 ring-teal-200/80 shadow-sm"
                      : isAffected
                      ? "border-red-300 bg-red-50/40 hover:border-red-400"
                      : "border-stone-200 hover:border-stone-400"
                  } ${opacity}`}
                >
                  <div className="flex items-center gap-2">
                    <div className="w-6 h-6 rounded bg-teal-50 border border-teal-200 flex items-center justify-center text-teal-700 shrink-0">
                      <Icon name="code" size={13} />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="text-[9px] font-bold text-stone-400 uppercase tracking-wider truncate">
                        {node.subtype}
                      </div>
                      <div className="font-bold text-xs text-stone-900 truncate">
                        {node.name}
                      </div>
                      <div className="text-[10px] text-stone-500 font-mono truncate">
                        {node.detail}
                      </div>
                    </div>
                    {isAffected && (
                      <span className="w-2 h-2 rounded-full bg-red-500 shrink-0 self-start mt-0.5" />
                    )}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Floating Pan & Zoom Dock at Bottom-Left matching image */}
          <div className="absolute left-4 bottom-4 flex items-center bg-white border border-stone-200 rounded-md shadow-sm p-0.5 gap-0.5 z-10 text-xs text-stone-600">
            <button
              className="w-7 h-7 flex items-center justify-center hover:bg-stone-100 rounded text-stone-700 font-bold"
              onClick={() => setScale(Math.max(0.6, scale - 0.1))}
              title="Zoom out"
            >
              −
            </button>
            <button
              className="w-7 h-7 flex items-center justify-center hover:bg-stone-100 rounded text-stone-700 font-bold"
              onClick={() => setPan({ ...pan, y: pan.y + 60 })}
              title="Pan up"
            >
              ↑
            </button>
            <button
              className="w-7 h-7 flex items-center justify-center hover:bg-stone-100 rounded text-stone-700 font-bold"
              onClick={() => setPan({ ...pan, y: pan.y - 60 })}
              title="Pan down"
            >
              ↓
            </button>
            <button
              className="w-7 h-7 flex items-center justify-center hover:bg-stone-100 rounded text-stone-700 font-bold"
              onClick={() => setScale(Math.min(1.4, scale + 0.1))}
              title="Zoom in"
            >
              +
            </button>
          </div>
        </div>

        {/* Right Drawer / Inspector Panel (Exact match to screenshot) */}
        {selectedNode && (
          <aside className="w-[360px] bg-white p-5 flex flex-col overflow-y-auto border-l border-stone-200">
            {/* Header: Subtype, Back, Title, Close */}
            <div className="text-[11px] text-stone-500 font-medium mb-1">
              {selectedNode.subtype}
            </div>

            <div className="flex items-start justify-between mb-3">
              <div className="flex items-center gap-2">
                <button
                  className="text-xs text-stone-500 hover:text-stone-900 flex items-center gap-1 font-medium"
                  onClick={() => setSelectedId(null)}
                >
                  ← Back
                </button>
                <h2 className="text-2xl font-bold text-stone-900 tracking-tight">
                  {selectedNode.name}
                </h2>
              </div>
              <button
                className="text-stone-400 hover:text-stone-700 p-1"
                onClick={() => setSelectedId(null)}
              >
                ✕
              </button>
            </div>

            {/* Status Pill Badge */}
            <div className="mb-4">
              <span
                className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium ${
                  selectedNode.status === "affected"
                    ? "bg-red-50 text-red-800 border border-red-200"
                    : "bg-stone-100 text-stone-700 border border-stone-200"
                }`}
              >
                <span
                  className={`w-1.5 h-1.5 rounded-full ${
                    selectedNode.status === "affected" ? "bg-red-600" : "bg-emerald-500"
                  }`}
                />
                {selectedNode.status}
              </span>
            </div>

            {/* Context 2x2 Grid Section */}
            <div className="border border-stone-200 rounded-md p-3.5 mb-5 bg-white">
              <h3 className="text-xs font-bold text-stone-900 uppercase tracking-wider mb-2.5">
                Context
              </h3>
              <div className="grid grid-cols-2 gap-y-3 gap-x-4 text-xs">
                <div className="border-r border-stone-200 pr-3">
                  <span className="text-stone-500 block text-[11px] mb-0.5">Project</span>
                  <strong className="text-stone-900 text-sm font-semibold">{currentProject}</strong>
                </div>
                <div>
                  <span className="text-stone-500 block text-[11px] mb-0.5">Environment</span>
                  <strong className="text-stone-900 text-sm font-semibold">{currentEnv}</strong>
                </div>
                <div className="border-r border-stone-200 pr-3 pt-2.5 border-t border-stone-100">
                  <span className="text-stone-500 block text-[11px] mb-0.5">Connected nodes</span>
                  <strong className="text-stone-900 text-sm font-semibold">{connectedNodesCount}</strong>
                </div>
                <div className="pt-2.5 border-t border-stone-100">
                  <span className="text-stone-500 block text-[11px] mb-0.5">Evidence</span>
                  <strong className="text-stone-900 text-xs font-semibold leading-tight block truncate">
                    {selectedNode.evidence || "Registered application"}
                  </strong>
                </div>
              </div>
            </div>

            {/* Application relationships / Details */}
            <div className="mb-5 text-xs text-stone-600">
              <h3 className="text-xs font-bold text-stone-900 uppercase tracking-wider mb-1.5">
                {selectedNode.kind === "application" ? "Application relationships" : "Dependency relationships"}
              </h3>
              <p className="text-stone-600 text-xs mb-3">{selectedNode.detail}</p>
              <div className="space-y-1 text-xs">
                <div className="flex justify-between py-1.5 border-b border-stone-100">
                  <span className="text-stone-500">Connected external dependencies</span>
                  <strong className="text-stone-900 font-semibold">{connectedDepsCount}</strong>
                </div>
                <div className="flex justify-between py-1.5 border-b border-stone-100">
                  <span className="text-stone-500">Affected workflows</span>
                  <strong
                    className={
                      affectedWorkflowsCount > 0
                        ? "text-red-600 font-bold"
                        : "text-stone-700 font-semibold"
                    }
                  >
                    {affectedWorkflowsCount > 0 ? `${affectedWorkflowsCount} affected` : "None known"}
                  </strong>
                </div>
              </div>
            </div>

            {/* Real Schema Myers Diff (for Weather API or Payment API) */}
            {selectedNode.status === "affected" && (
              <div className="p-3 bg-red-50 border border-red-200 rounded-md mb-4 text-xs">
                <div className="flex items-center justify-between mb-1 text-red-900 font-bold">
                  <span>Anomalous Schema Drift</span>
                  <Badge tone="danger">Myers Diff</Badge>
                </div>
                {selectedNode.id.includes("weather") ? (
                  <div className="bg-stone-900 text-stone-100 p-2 rounded font-mono text-[11px] my-1.5">
                    <div className="text-red-400">- &quot;temperature&quot;: 21.5</div>
                    <div className="text-emerald-400">+ &quot;temp_c&quot;: 21.5</div>
                  </div>
                ) : (
                  <div className="bg-stone-900 text-stone-100 p-2 rounded font-mono text-[11px] my-1.5">
                    <div className="text-red-400">- &quot;name&quot;: &quot;Annual Pro Plan&quot;</div>
                    <div className="text-emerald-400">+ &quot;display_name&quot;: &quot;Annual Pro Plan&quot;</div>
                  </div>
                )}
                <p className="text-red-800 text-[11px] mt-1">
                  Observed divergence in upstream service affects downstream workflows.
                </p>
              </div>
            )}

            {/* Action Buttons at the bottom matching image */}
            <div className="mt-auto pt-3 border-t border-stone-200 flex flex-col gap-2">
              <Button
                variant={tracing ? "primary" : "secondary"}
                icon="graph"
                className="w-full justify-center"
                onClick={() => setTracing(!tracing)}
              >
                {tracing ? "Clear Trace Impact" : "Trace Impact"}
              </Button>
              <div className="flex gap-2">
                <Button
                  variant="secondary"
                  className="flex-1 text-xs justify-center"
                  onClick={() => {
                    if (selectedNode.status === "affected") {
                      navigate("recovery");
                    } else {
                      alert(`Relationship confirmed for ${selectedNode.name}`);
                    }
                  }}
                >
                  {selectedNode.status === "affected" ? "Recovery Case" : "Add relationship"}
                </Button>
                <Button
                  variant="secondary"
                  className="flex-1 text-xs justify-center"
                  onClick={() => setSelectedId(null)}
                >
                  Remove node
                </Button>
              </div>
            </div>
          </aside>
        )}
      </div>
    </>
  );
}
