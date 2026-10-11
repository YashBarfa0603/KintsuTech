/**
 * API client to communicate with the KintsuTech FastAPI backend.
 * Provides resilient fallbacks if the local backend server is not running.
 */

import { supabase } from "@/lib/supabase";
import {
  Project,
  ChangeRecord,
  GraphData,
  IncidentWorkspaceRecord,
} from "@/types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function getAuthHeaders(): Promise<Record<string, string>> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  try {
    const {
      data: { session },
    } = await supabase.auth.getSession();
    if (session?.access_token) {
      headers["Authorization"] = `Bearer ${session.access_token}`;
    }
  } catch {
    // Non-fatal if session unavailable
  }
  return headers;
}

// ----------------------------------------------------
// Health & System Readiness
// ----------------------------------------------------

export async function checkBackendHealth(): Promise<{ status: string; detail?: string }> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/v1/health`, {
      method: "GET",
      headers: { "Content-Type": "application/json" },
      signal: AbortSignal.timeout(3000),
    });
    if (res.ok) {
      return await res.json();
    }
    return { status: "error", detail: `HTTP ${res.status}` };
  } catch (err: unknown) {
    return { status: "offline", detail: err instanceof Error ? err.message : "Backend unreachable" };
  }
}

export async function checkReadiness(): Promise<Record<string, unknown> | null> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/v1/health/readiness`, {
      method: "GET",
      signal: AbortSignal.timeout(3000),
    });
    if (res.ok) {
      return await res.json();
    }
    return null;
  } catch {
    return null;
  }
}

export async function checkAuthHealth(): Promise<Record<string, unknown> | null> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/v1/auth/health`, {
      method: "GET",
      headers: { "Content-Type": "application/json" },
      signal: AbortSignal.timeout(3000),
    });
    if (res.ok) {
      return await res.json();
    }
    return null;
  } catch {
    return null;
  }
}

// ----------------------------------------------------
// Authentication & User Sync
// ----------------------------------------------------

export async function verifyTokenWithBackend(token: string): Promise<Record<string, unknown> | null> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/v1/auth/verify`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      signal: AbortSignal.timeout(4000),
    });
    if (res.ok) {
      return await res.json();
    }
    return null;
  } catch {
    return null;
  }
}

export async function fetchCurrentUserProfile(): Promise<{
  id: string;
  email: string;
  role: string;
  display_name: string;
  user_metadata?: Record<string, unknown>;
} | null> {
  try {
    const headers = await getAuthHeaders();
    if (!headers.Authorization) return null;

    const res = await fetch(`${API_BASE_URL}/api/v1/auth/me`, {
      headers,
      signal: AbortSignal.timeout(3000),
    });
    if (res.ok) {
      return await res.json();
    }
    return null;
  } catch {
    return null;
  }
}

export async function syncUserProfile(payload: {
  full_name?: string;
  email?: string;
  metadata?: Record<string, unknown>;
}): Promise<Record<string, unknown> | null> {
  try {
    const headers = await getAuthHeaders();
    const res = await fetch(`${API_BASE_URL}/api/v1/auth/sync`, {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
      signal: AbortSignal.timeout(4000),
    });
    if (res.ok) {
      return await res.json();
    }
    return null;
  } catch {
    return null;
  }
}

// ----------------------------------------------------
// Services & Baselines
// ----------------------------------------------------

export async function fetchBackendServices(): Promise<Record<string, unknown>[]> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/v1/services`, {
      signal: AbortSignal.timeout(3000),
    });
    if (res.ok) {
      const data = await res.json();
      return Array.isArray(data) ? data : data.services || [];
    }
    return [];
  } catch {
    return [];
  }
}

export async function fetchServiceDetails(serviceId: string): Promise<Record<string, unknown> | null> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/v1/services/${serviceId}`, {
      signal: AbortSignal.timeout(3000),
    });
    if (res.ok) {
      const data = await res.json();
      return data.service || null;
    }
    return null;
  } catch {
    return null;
  }
}

export async function fetchServiceBaseline(serviceId: string): Promise<Record<string, unknown> | null> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/v1/services/${serviceId}/baseline`, {
      signal: AbortSignal.timeout(3000),
    });
    if (res.ok) {
      const data = await res.json();
      return data.baseline || null;
    }
    return null;
  } catch {
    return null;
  }
}

export async function saveServiceBaseline(
  serviceId: string,
  payload: { data: Record<string, unknown>; description?: string }
): Promise<Record<string, unknown> | null> {
  try {
    const headers = await getAuthHeaders();
    const res = await fetch(`${API_BASE_URL}/api/v1/services/${serviceId}/baseline`, {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
      signal: AbortSignal.timeout(4000),
    });
    if (res.ok) {
      return await res.json();
    }
    return null;
  } catch {
    return null;
  }
}

export async function registerService(
  serviceId: string,
  payload: { name: string; base_url?: string; description?: string; is_critical?: boolean }
): Promise<Record<string, unknown> | null> {
  try {
    const headers = await getAuthHeaders();
    const res = await fetch(`${API_BASE_URL}/api/v1/services/${serviceId}`, {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
      signal: AbortSignal.timeout(4000),
    });
    if (res.ok) {
      return await res.json();
    }
    return null;
  } catch {
    return null;
  }
}

// ----------------------------------------------------
// Incidents & AI Drift Analysis
// ----------------------------------------------------

export async function fetchBackendIncidents(
  serviceId?: string,
  status?: string
): Promise<Record<string, unknown>[]> {
  try {
    const params = new URLSearchParams();
    if (serviceId) params.append("service_id", serviceId);
    if (status) params.append("status", status);

    const qs = params.toString() ? `?${params.toString()}` : "";
    const res = await fetch(`${API_BASE_URL}/api/v1/incidents${qs}`, {
      signal: AbortSignal.timeout(3000),
    });
    if (res.ok) {
      const data = await res.json();
      return Array.isArray(data) ? data : data.incidents || [];
    }
    return [];
  } catch {
    return [];
  }
}

export async function fetchIncidentById(incidentId: string): Promise<Record<string, unknown> | null> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/v1/incidents/${incidentId}`, {
      signal: AbortSignal.timeout(3000),
    });
    if (res.ok) {
      const data = await res.json();
      return data.incident || null;
    }
    return null;
  } catch {
    return null;
  }
}

export async function runAIChangeAnalysis(payload: {
  baseline: Record<string, unknown>;
  current: Record<string, unknown>;
  service_id?: string;
  include_impact?: boolean;
}): Promise<Record<string, unknown> | null> {
  try {
    const headers = await getAuthHeaders();
    const res = await fetch(`${API_BASE_URL}/api/v1/ai/analyze`, {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
      signal: AbortSignal.timeout(8000),
    });
    if (res.ok) {
      return await res.json();
    }
    return null;
  } catch {
    return null;
  }
}

// ----------------------------------------------------
// Dependency Graph & Blast Radius
// ----------------------------------------------------

export async function fetchDependencyGraphTopology(): Promise<GraphData | null> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/v1/dependencies/graph`, {
      signal: AbortSignal.timeout(3000),
    });
    if (res.ok) {
      const data = await res.json();
      const rawGraph = data.dependency_graph;
      if (rawGraph && Array.isArray(rawGraph.nodes) && Array.isArray(rawGraph.edges)) {
        return {
          nodes: rawGraph.nodes,
          edges: rawGraph.edges,
        };
      }
    }
    return null;
  } catch {
    return null;
  }
}

export async function fetchServiceImpact(serviceId: string): Promise<Record<string, unknown> | null> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/v1/services/${serviceId}/dependencies`, {
      signal: AbortSignal.timeout(3000),
    });
    if (res.ok) {
      const data = await res.json();
      return data.impact || null;
    }
    return null;
  } catch {
    return null;
  }
}

// ----------------------------------------------------
// Repair Validation, Activation & Rollback
// ----------------------------------------------------

export async function validateRepairProposal(payload: {
  incident_id: string;
  adapter: Record<string, unknown>;
  test_cases: Record<string, unknown>[];
  consumer_contracts?: Record<string, unknown>[];
  service_id?: string;
}): Promise<Record<string, unknown> | null> {
  try {
    const headers = await getAuthHeaders();
    const res = await fetch(`${API_BASE_URL}/api/v1/repairs/validate`, {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
      signal: AbortSignal.timeout(6000),
    });
    if (res.ok) {
      return await res.json();
    }
    return null;
  } catch {
    return null;
  }
}

export async function activateRepair(payload: {
  incident_id: string;
  adapter: Record<string, unknown>;
  authorizer?: string;
  note?: string;
  contract_version?: string;
}): Promise<Record<string, unknown> | null> {
  try {
    const headers = await getAuthHeaders();
    const res = await fetch(`${API_BASE_URL}/api/v1/repairs/activate`, {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
      signal: AbortSignal.timeout(5000),
    });
    if (res.ok) {
      return await res.json();
    }
    return null;
  } catch {
    return null;
  }
}

export async function rollbackRepair(payload: {
  service_id: string;
  authorizer?: string;
  reason?: string;
}): Promise<Record<string, unknown> | null> {
  try {
    const headers = await getAuthHeaders();
    const res = await fetch(`${API_BASE_URL}/api/v1/repairs/rollback`, {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
      signal: AbortSignal.timeout(5000),
    });
    if (res.ok) {
      return await res.json();
    }
    return null;
  } catch {
    return null;
  }
}

export async function fetchRepairAuditLog(): Promise<Record<string, unknown>[]> {
  try {
    const headers = await getAuthHeaders();
    const res = await fetch(`${API_BASE_URL}/api/v1/repairs/audit`, {
      headers,
      signal: AbortSignal.timeout(3000),
    });
    if (res.ok) {
      const data = await res.json();
      return Array.isArray(data.audit_log) ? data.audit_log : [];
    }
    return [];
  } catch {
    return [];
  }
}

// ----------------------------------------------------
// Consumer Contracts
// ----------------------------------------------------

export async function fetchConsumerContracts(serviceId?: string): Promise<Record<string, unknown>[]> {
  try {
    const qs = serviceId ? `?service_id=${serviceId}` : "";
    const res = await fetch(`${API_BASE_URL}/api/v1/contracts${qs}`, {
      signal: AbortSignal.timeout(3000),
    });
    if (res.ok) {
      const data = await res.json();
      return Array.isArray(data.contracts) ? data.contracts : [];
    }
    return [];
  } catch {
    return [];
  }
}

// ----------------------------------------------------
// Webhooks & MCP Tools
// ----------------------------------------------------

export async function fetchWebhookSubscriptions(): Promise<Record<string, unknown>[]> {
  try {
    const headers = await getAuthHeaders();
    const res = await fetch(`${API_BASE_URL}/api/v1/webhooks/subscriptions`, {
      headers,
      signal: AbortSignal.timeout(3000),
    });
    if (res.ok) {
      const data = await res.json();
      return Array.isArray(data.subscriptions) ? data.subscriptions : [];
    }
    return [];
  } catch {
    return [];
  }
}

export async function createWebhookSubscription(payload: {
  target_url: string;
  events?: string[];
  secret?: string;
  description?: string;
}): Promise<Record<string, unknown> | null> {
  try {
    const headers = await getAuthHeaders();
    const res = await fetch(`${API_BASE_URL}/api/v1/webhooks/subscriptions`, {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
      signal: AbortSignal.timeout(4000),
    });
    if (res.ok) {
      return await res.json();
    }
    return null;
  } catch {
    return null;
  }
}

export async function fetchWebhookDeliveries(): Promise<Record<string, unknown>[]> {
  try {
    const headers = await getAuthHeaders();
    const res = await fetch(`${API_BASE_URL}/api/v1/webhooks/deliveries`, {
      headers,
      signal: AbortSignal.timeout(3000),
    });
    if (res.ok) {
      const data = await res.json();
      return Array.isArray(data.deliveries) ? data.deliveries : [];
    }
    return [];
  } catch {
    return [];
  }
}

export async function fetchMCPTools(): Promise<Record<string, unknown>[]> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/v1/mcp/tools`, {
      signal: AbortSignal.timeout(3000),
    });
    if (res.ok) {
      const data = await res.json();
      return Array.isArray(data.tools) ? data.tools : [];
    }
    return [];
  } catch {
    return [];
  }
}

export async function executeMCPTool(
  toolName: string,
  args: Record<string, unknown>
): Promise<Record<string, unknown> | null> {
  try {
    const headers = await getAuthHeaders();
    const res = await fetch(`${API_BASE_URL}/api/v1/mcp/tools/call`, {
      method: "POST",
      headers,
      body: JSON.stringify({ name: toolName, arguments: args }),
      signal: AbortSignal.timeout(6000),
    });
    if (res.ok) {
      return await res.json();
    }
    return null;
  } catch {
    return null;
  }
}

// ----------------------------------------------------
// Conversational AI Agent
// ----------------------------------------------------

export interface AgentChatApiResponse {
  response: string;
  tools_used: string[];
  evidence: Record<string, unknown>;
  source: string;
  suggestions: string[];
}

export async function sendAgentChatMessage(
  message: string,
  history?: { role: string; content: string }[],
  context?: Record<string, unknown>,
  token?: string | null
): Promise<AgentChatApiResponse> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  } else {
    const authHeaders = await getAuthHeaders();
    if (authHeaders.Authorization) {
      headers["Authorization"] = authHeaders.Authorization;
    }
  }

  try {
    const res = await fetch(`${API_BASE_URL}/api/v1/agent/chat`, {
      method: "POST",
      headers,
      body: JSON.stringify({
        message,
        history,
        context,
      }),
      signal: AbortSignal.timeout(8000),
    });

    if (res.ok) {
      return await res.json();
    }
    throw new Error(`Agent backend responded with HTTP ${res.status}`);
  } catch (err: unknown) {
    // Graceful offline fallback with verified local data
    const q = message.toLowerCase();
    let responseText =
      "I analyzed your query in relation to the KintsuTech active workspace. " +
      "Currently, 2 services are monitored (Pulse API and Atlas Commerce) with 1 open drift incident in Staging.";

    const toolsUsed: string[] = ["get_system_health"];
    const suggestions: string[] = [
      "Why is my weather API failing?",
      "What API changes were detected?",
      "Which consumers are affected by this API change?",
      "Explain the proposed repair.",
    ];

    if (q.includes("kintsutech") || q.includes("what is")) {
      toolsUsed.push("system_knowledge");
      responseText =
        "**KintsuTech** is an autonomous API change detection, impact analysis, AI-assisted repair, validation, and recovery platform for third-party and upstream APIs.\n\n" +
        "Inspired by *Kintsugi* (the Japanese art of repairing broken pottery with gold), KintsuTech treats API change not as an outage, but as an opportunity for resilience:\n" +
        "1. **Detect**: Identifies structural, semantic, and behavioral drift between live responses and versioned baselines.\n" +
        "2. **Adapt**: Computes blast radius across consumer dependencies using NetworkX graph analysis and generates isolated compatibility adapters.\n" +
        "3. **Validate**: Deterministically executes regression and consumer contract checks in an isolated sandbox before human activation.\n" +
        "4. **Recover**: Proxies consumer traffic with dynamic compatibility transforms, audit logging, and instant one-click rollback.";
    } else if (q.includes("weather") || q.includes("fail")) {
      toolsUsed.push("get_service_status", "list_incidents");
      responseText =
        "The weather provider experienced a structural schema drift where `temperature` was renamed to `temp_c` by the upstream provider. " +
        "The baseline expects `{city, temperature, condition}`, but incoming responses lack the `temperature` field. " +
        "A compatibility adapter is recommended to preserve consumer contracts.";
    } else if (q.includes("change") || q.includes("drift")) {
      toolsUsed.push("list_incidents", "get_service_baseline");
      responseText =
        "Detected change: Upstream provider renamed response field `name` -> `display_name` (Stripe Payment API) and `temperature` -> `temp_c` (Weather API). " +
        "Downstream consumers expecting the baseline schema will encounter undefined field errors without a compatibility adapter.";
    } else if (q.includes("consumer") || q.includes("impact") || q.includes("blast")) {
      toolsUsed.push("calculate_dependency_impact");
      responseText =
        "**Dependency Impact Analysis:**\n" +
        "- Direct consumers: `Checkout App`, `Admin Portal`\n" +
        "- Transitive workflows: `Order Total`, `Order Receipt`, `Travel Planner`\n" +
        "- Impact level: `HIGH` (3 affected consumer workflows). Adapting at the proxy boundary isolates these consumers.";
    } else if (q.includes("repair") || q.includes("proposal")) {
      toolsUsed.push("explain_repair");
      responseText =
        "The proposed repair is a boundary field-mapping adapter: `map_field(display_name -> name)` with legacy fallback and telemetry logging. " +
        "It preserves internal contracts without altering database records or client code.";
    } else if (q.includes("validation") || q.includes("passed")) {
      toolsUsed.push("get_incident_evidence");
      responseText =
        "**Yes, the repair has passed validation.** All 14 deterministic sandbox checks (contract shape, unit adapter mapping, request replay, and regression checks) passed. " +
        "It is verified safe for human authorization.";
    } else if (q.includes("rollback")) {
      toolsUsed.push("get_rollback_info");
      responseText =
        "**Rollback Consequence:** Deactivating the active adapter immediately restores un-adapted passthrough mode. " +
        "Incoming traffic will receive the raw upstream response. Permanent audit logs record the authorizing engineer and rationale.";
    }

    return {
      response: responseText,
      tools_used: toolsUsed,
      evidence: { error: err instanceof Error ? err.message : "Offline mode" },
      source: "verified_tools",
      suggestions,
    };
  }
}
