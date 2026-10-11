export type Screen =
  | "overview"
  | "projects"
  | "dependencies"
  | "changes"
  | "graph"
  | "recovery"
  | "validation"
  | "history"
  | "integrations"
  | "settings";

export type Project = {
  id: string;
  name: string;
  description: string;
  repository: string;
  owner: string;
  apis: number;
  services: number;
  health: "Healthy" | "Degraded" | "Unknown";
  incidents: number;
  members: number;
};

export type DependencyType = "API" | "SDK" | "MCP Server" | "Webhook";

export type ChangeRecord = {
  id: string;
  dependencyType: DependencyType;
  service: string;
  endpoint: string;
  category: string;
  severity: "Critical" | "High" | "Medium" | "Low";
  confidence: number;
  status: "New" | "Acknowledged" | "Investigating" | "Dismissed" | "Recovery open";
  summary: string;
  observed: string;
  evidence: string;
  breaking: boolean;
};

export type GraphNodeKind = "application" | "api" | "dependency";
export type GraphStatus = "healthy" | "affected" | "failed" | "unknown";

export type GraphNode = {
  id: string;
  kind: GraphNodeKind;
  subtype: string;
  name: string;
  detail: string;
  status: GraphStatus;
  project: string;
  environment: string;
  provider?: string;
  method?: string;
  evidence?: string;
  source?: "demo" | "inventory" | "user";
};

export type GraphEdge = {
  id: string;
  from: string;
  to: string;
  label: string;
  evidence: "confirmed" | "inferred" | "unknown";
  confidence?: number;
  source: string;
  status: "healthy" | "affected" | "failed";
};

export type GraphData = {
  nodes: GraphNode[];
  edges: GraphEdge[];
};

export type IncidentWorkspaceRecord = {
  id: string;
  dependencyType: DependencyType;
  title: string;
  api: string;
  endpoint: string;
  detected: string;
  environment: string;
  severity: "Critical" | "High" | "Medium";
  state: string;
  applications: string[];
  workflows: string[];
  baseline: Record<string, string | number | boolean | null>;
  current: Record<string, string | number | boolean | null>;
  proposalTitle: string;
  problem: string;
  expected: string;
  operation: string;
  originalCode: string;
  proposedCode: string;
  supported: boolean;
  evidence: string[];
  operations?: ["permitted" | "rejected" | "review", string, string, string][];
  tests?: [string, string, string][];
  assumptions?: string[];
};

export type IncidentEvent = {
  id: string;
  incidentId: string;
  time: string;
  label: string;
  description: string;
  status: string;
  target: string;
};

export type IconName =
  | "activity"
  | "alert"
  | "api"
  | "arrow"
  | "bell"
  | "back"
  | "check"
  | "chevron"
  | "clock"
  | "close"
  | "code"
  | "dependency"
  | "download"
  | "graph"
  | "history"
  | "home"
  | "menu"
  | "mic"
  | "play"
  | "plus"
  | "recovery"
  | "search"
  | "settings"
  | "shield"
  | "spark"
  | "test"
  | "user"
  | "x";
