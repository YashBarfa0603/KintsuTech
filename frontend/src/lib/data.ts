import {
  ChangeRecord,
  DependencyType,
  GraphData,
  GraphNode,
  IncidentWorkspaceRecord,
  Project,
  Screen,
  IconName,
} from "@/types";

export const defaultProjects: Project[] = [
  {
    id: "pulse",
    name: "Pulse API",
    description: "Customer billing and subscription application.",
    repository: "github.com/kintsu/pulse-api",
    owner: "Platform Engineering",
    apis: 11,
    services: 12,
    health: "Degraded",
    incidents: 1,
    members: 6,
  },
  {
    id: "atlas",
    name: "Atlas Commerce",
    description: "Order management and merchant operations.",
    repository: "github.com/kintsu/atlas-commerce",
    owner: "Commerce Platform",
    apis: 5,
    services: 9,
    health: "Healthy",
    incidents: 0,
    members: 4,
  },
];

export const defaultChanges: ChangeRecord[] = [
  {
    id: "CHG-841",
    dependencyType: "API",
    service: "Stripe",
    endpoint: "GET /v1/payment_intents/:id",
    category: "Renamed response field",
    severity: "Critical",
    confidence: 98.7,
    status: "Investigating",
    summary: "Response field name was replaced by display_name.",
    observed: "Today, 14:14 UTC",
    evidence: "412 simulated observed responses + schema comparison",
    breaking: true,
  },
  {
    id: "CHG-838",
    dependencyType: "API",
    service: "SendGrid",
    endpoint: "POST /v3/mail/send",
    category: "Rate-limit change",
    severity: "Medium",
    confidence: 91.2,
    status: "Acknowledged",
    summary: "Rate-limit reset header changed from seconds to epoch time.",
    observed: "Today, 12:26 UTC",
    evidence: "Demonstration behavioural baseline across 86 responses",
    breaking: false,
  },
  {
    id: "CHG-836",
    dependencyType: "SDK",
    service: "Stripe SDK",
    endpoint: "@stripe/stripe-js · npm",
    category: "Method signature change",
    severity: "High",
    confidence: 88.4,
    status: "New",
    summary: "confirmPayment options changed in the imported package snapshot.",
    observed: "Today, 11:48 UTC",
    evidence: "Simulated package manifest and TypeScript declaration comparison; SDK monitoring backend unavailable",
    breaking: true,
  },
  {
    id: "CHG-833",
    dependencyType: "MCP Server",
    service: "Travel Tools MCP",
    endpoint: "search_flights tool",
    category: "Input schema change",
    severity: "Medium",
    confidence: 84.1,
    status: "New",
    summary: "The tool now requires a locale input property.",
    observed: "Today, 10:32 UTC",
    evidence: "Simulated capability snapshot comparison; live MCP monitoring unavailable",
    breaking: true,
  },
  {
    id: "CHG-828",
    dependencyType: "Webhook",
    service: "Stripe Payment Webhook",
    endpoint: "payment.succeeded",
    category: "Payload field rename",
    severity: "High",
    confidence: 93.6,
    status: "New",
    summary: "The saved event fixture contains customer_name while the reported payload uses customer_display_name.",
    observed: "Today, 09:18 UTC",
    evidence: "Provider-reported redacted payload fixture comparison; no live delivery receiver is connected",
    breaking: true,
  },
  {
    id: "CHG-829",
    dependencyType: "API",
    service: "GitHub",
    endpoint: "GET /repos/:owner/:repo",
    category: "Added response field",
    severity: "Low",
    confidence: 99.4,
    status: "Dismissed",
    summary: "Optional security_and_analysis field was added.",
    observed: "Yesterday, 16:08 UTC",
    evidence: "Schema comparison",
    breaking: false,
  },
];

export const dependencyRows = [
  ["Mapbox", "api.mapbox.com", "GET /geocoding/v5", "Healthy", "3 min ago", "198 ms", "0.1%", "None", "2", "Pulse API", "Staging", "API", JSON.stringify({ method: "GET", requestConfig: "Public API key · JSON", baseline: `{\n  "features": []\n}` })],
  ["Stripe", "api.stripe.com", "GET /v1/payment_intents/:id", "Degraded", "12 sec ago", "284 ms", "1.8%", "name → display_name", "4", "Pulse API", "Production", "API", JSON.stringify({ method: "GET", requestConfig: "Bearer token · JSON", baseline: `{\n  "id": "string",\n  "name": "string",\n  "amount": 12900\n}` })],
  ["GitHub", "api.github.com", "GET /repos/:owner/:repo", "Healthy", "34 sec ago", "142 ms", "0.1%", "None", "6", "Pulse API", "Production", "API", JSON.stringify({})],
  ["SendGrid", "api.sendgrid.com", "POST /v3/mail/send", "Watching", "1 min ago", "318 ms", "0.7%", "Rate-limit header", "3", "Pulse API", "Production", "API", JSON.stringify({})],
  ["Twilio", "api.twilio.com", "POST /Messages.json", "Healthy", "2 min ago", "231 ms", "0.2%", "None", "2", "Pulse API", "Production", "API", JSON.stringify({})],
  ["OpenAI", "api.openai.com", "POST /v1/responses", "Healthy", "16 sec ago", "842 ms", "0.4%", "None", "5", "Pulse API", "Production", "API", JSON.stringify({})],
  ["Slack", "slack.com/api", "POST /chat.postMessage", "Healthy", "44 sec ago", "176 ms", "0.1%", "None", "3", "Pulse API", "Production", "API", JSON.stringify({})],
  ["Salesforce", "api.salesforce.com", "GET /services/data/v60", "Healthy", "4 min ago", "390 ms", "0.3%", "None", "4", "Pulse API", "Production", "API", JSON.stringify({})],
  ["Stripe SDK", "@stripe/stripe-js", "npm · 4.2.0", "Unknown", "Monitoring unavailable", "—", "—", "Method signature snapshot", "2", "Pulse API", "Production", "SDK", JSON.stringify({ ecosystem: "npm", version: "4.2.0", source: "package.json", components: "confirmPayment, StripeElements" })],
  ["Travel Tools MCP", "local command configuration", "stdio · 3 declared tools", "Unknown", "Monitoring unavailable", "—", "—", "Capability snapshot only", "1", "Pulse API", "Production", "MCP Server", JSON.stringify({ transport: "stdio", connection: "npx travel-tools-mcp", components: "search_flights, get_itinerary, travel://policies" })],
  ["Stripe Payment Webhook", "Stripe · Incoming", "POST /webhooks/stripe · payment.succeeded", "Unknown", "Monitoring unavailable", "—", "—", "Reported payload field rename", "2", "Pulse API", "Production", "Webhook", JSON.stringify({ provider: "Stripe", description: "Receives payment lifecycle events.", direction: "Incoming", method: "POST", receiver: "https://example.invalid/webhooks/stripe", events: "payment.succeeded, payment.failed", schema: `{ "id": "string", "type": "payment.succeeded", "data": { "customer_name": "string" } }`, signature: "Secret reference: WEBHOOK_STRIPE_SIGNING_SECRET", retry: "Exponential · 3 attempts · 10s timeout", expectedDelivery: "2xx within 3 seconds", requiredFields: "id, type, created, data.object", idempotency: "Event id must be processed once", fixture: "fixtures/stripe-payment-succeeded.json", workflows: "Order confirmation, Receipt delivery", paused: "false" })],
];

export function dependencyMeta(service: string) {
  const rest =
    service === "Stripe"
      ? ["REST API", "Production", "Critical"]
      : service === "SendGrid"
      ? ["Webhook", "Production", "Medium"]
      : ["REST API", service === "Mapbox" ? "Staging" : "Production", "None"];
  return { type: rest[0], environment: rest[1], severity: rest[2] };
}

export const dependencyType = (row?: string[]): DependencyType =>
  row?.[11] === "SDK" || row?.[11] === "MCP Server" || row?.[11] === "Webhook"
    ? (row[11] as DependencyType)
    : "API";

export const dependencyDetails = (row?: string[]): Record<string, string> => {
  try {
    return row?.[12] ? JSON.parse(row[12]) : {};
  } catch {
    return {};
  }
};

export const dependencyIcon = (type: DependencyType): IconName =>
  type === "API" ? "api" : type === "SDK" ? "code" : type === "MCP Server" ? "spark" : "bell";

export const graphDependencyType = (node?: GraphNode): DependencyType =>
  node?.subtype.startsWith("SDK")
    ? "SDK"
    : node?.subtype.startsWith("MCP")
    ? "MCP Server"
    : node?.subtype.startsWith("Webhook")
    ? "Webhook"
    : "API";

export const defaultGraphData: GraphData = {
  nodes: [
    { id: "app-web", kind: "application", subtype: "Web application", name: "Web App", detail: "Customer checkout and travel planning", status: "affected", project: "Pulse API", environment: "Production", evidence: "Registered application", source: "demo" },
    { id: "app-mobile", kind: "application", subtype: "Mobile application", name: "Mobile App", detail: "iOS and Android customer experience", status: "healthy", project: "Pulse API", environment: "Production", evidence: "Registered application", source: "demo" },
    { id: "app-admin", kind: "application", subtype: "Internal application", name: "Admin Portal", detail: "Operations and inventory management", status: "healthy", project: "Pulse API", environment: "Production", evidence: "Registered application", source: "demo" },
    { id: "api-weather", kind: "api", subtype: "API", name: "Weather API", detail: "api.weather.example/v2", status: "healthy", project: "Pulse API", environment: "Production", provider: "Weather Co", method: "GET", evidence: "Developer-defined contract", source: "demo" },
    { id: "api-payment", kind: "api", subtype: "API", name: "Payment API", detail: "api.stripe.com/v1", status: "affected", project: "Pulse API", environment: "Production", provider: "Stripe", method: "GET", evidence: "Imported contract + observed responses", source: "demo" },
    { id: "api-inventory", kind: "api", subtype: "API", name: "Inventory API", detail: "inventory.example/v1", status: "healthy", project: "Pulse API", environment: "Production", provider: "Acme Inventory", method: "GET", evidence: "Developer-defined contract", source: "demo" },
    { id: "webhook-payment", kind: "api", subtype: "Webhook", name: "Stripe Payment Webhook", detail: "payment.succeeded · POST /webhooks/stripe", status: "affected", project: "Pulse API", environment: "Production", provider: "Stripe", method: "POST", evidence: "Configured receiver + reported payload fixture", source: "demo" },
    { id: "dep-weather", kind: "dependency", subtype: "Service", name: "Weather Service", detail: "services/weather.ts", status: "healthy", project: "Pulse API", environment: "Production", evidence: "Repository reference", source: "demo" },
    { id: "dep-travel", kind: "dependency", subtype: "Workflow", name: "Travel Planner", detail: "WF-TRAVEL-04", status: "healthy", project: "Pulse API", environment: "Production", evidence: "Developer-defined mapping", source: "demo" },
    { id: "dep-analytics", kind: "dependency", subtype: "Response field", name: "Analytics", detail: "payment.display_name", status: "affected", project: "Pulse API", environment: "Production", evidence: "Observed trace + repository usage", source: "demo" },
    { id: "dep-notifications", kind: "dependency", subtype: "Service", name: "Notification Service", detail: "services/notifications.ts", status: "affected", project: "Pulse API", environment: "Production", evidence: "Developer-defined mapping", source: "demo" },
    { id: "dep-payment-event", kind: "dependency", subtype: "Webhook event", name: "payment.succeeded", detail: "event handlers/payment-succeeded.ts", status: "affected", project: "Pulse API", environment: "Production", evidence: "Registered event subscription", source: "demo" },
    { id: "dep-webhook-customer", kind: "dependency", subtype: "Payload field", name: "customer_display_name", detail: "data.object.customer_display_name", status: "affected", project: "Pulse API", environment: "Production", evidence: "Reported redacted payload fixture", source: "demo" },
  ],
  edges: [
    { id: "edge-web-weather", from: "app-web", to: "api-weather", label: "uses forecast", evidence: "confirmed", source: "Application registration", status: "healthy" },
    { id: "edge-mobile-weather", from: "app-mobile", to: "api-weather", label: "uses forecast", evidence: "confirmed", source: "Application registration", status: "healthy" },
    { id: "edge-web-payment", from: "app-web", to: "api-payment", label: "processes checkout", evidence: "confirmed", source: "Developer-defined mapping", status: "affected" },
    { id: "edge-admin-payment", from: "app-admin", to: "api-payment", label: "views payments", evidence: "confirmed", source: "Repository configuration", status: "affected" },
    { id: "edge-admin-inventory", from: "app-admin", to: "api-inventory", label: "manages stock", evidence: "confirmed", source: "Application registration", status: "healthy" },
    { id: "edge-weather-service", from: "api-weather", to: "dep-weather", label: "GET /forecast", evidence: "confirmed", source: "Imported OpenAPI contract", status: "healthy" },
    { id: "edge-weather-travel", from: "api-weather", to: "dep-travel", label: "weather.condition", evidence: "inferred", confidence: 87, source: "Request traces", status: "healthy" },
    { id: "edge-payment-analytics", from: "api-payment", to: "dep-analytics", label: "display_name field", evidence: "confirmed", source: "Repository usage + 412 responses", status: "affected" },
    { id: "edge-payment-notify", from: "api-payment", to: "dep-notifications", label: "payment succeeded", evidence: "confirmed", source: "Developer-defined mapping", status: "affected" },
    { id: "edge-inventory-notify", from: "api-inventory", to: "dep-notifications", label: "low stock event", evidence: "inferred", confidence: 82, source: "Configuration trace", status: "healthy" },
    { id: "edge-web-webhook", from: "app-web", to: "webhook-payment", label: "receives payment events", evidence: "confirmed", source: "Webhook registration", status: "affected" },
    { id: "edge-webhook-event", from: "webhook-payment", to: "dep-payment-event", label: "routes payment.succeeded", evidence: "confirmed", source: "Configured subscription", status: "affected" },
    { id: "edge-webhook-field", from: "webhook-payment", to: "dep-webhook-customer", label: "reads payload field", evidence: "confirmed", source: "Reported fixture + handler reference", status: "affected" },
  ],
};

export const incidentWorkspaceRecords: IncidentWorkspaceRecord[] = [
  {
    id: "KIN-2841",
    dependencyType: "API",
    title: "Payment API response field changed",
    api: "Stripe",
    endpoint: "GET /v1/payment_intents/:id",
    detected: "Today, 14:14",
    environment: "Staging",
    severity: "Critical",
    state: "Pending review",
    applications: ["Web App", "Admin Portal"],
    workflows: ["Checkout", "Order Total", "Order Receipt"],
    baseline: { id: "pi_3P8k94L", amount: 12900, name: "Annual Pro Plan", currency: "usd", status: "succeeded" },
    current: { id: "pi_3P8k94L", amount: 12900, display_name: "Annual Pro Plan", currency: "usd", status: "succeeded" },
    proposalTitle: "Preserve the internal product-name contract",
    problem: "Downstream code reads paymentIntent.name, which is no longer present in observed responses.",
    expected: "Checkout and receipt workflows continue receiving the same human-readable plan descriptor.",
    operation: "map_field(display_name → name) with legacy fallback and source-field telemetry",
    originalCode: `export function normalizeIntent(input: StripeIntent) {\n  return {\n    name: input.name,\n    amount: input.amount,\n    currency: input.currency\n  };\n}`,
    proposedCode: `export function normalizeIntent(input: StripeIntent) {\n  return {\n    name: input.display_name ?? input.name,\n    sourceField: input.display_name ? "display_name" : "name",\n    amount: input.amount,\n    currency: input.currency\n  };\n}`,
    supported: true,
    evidence: ["412 observed responses", "Saved contract version 3", "Repository usage at src/adapters/stripe.ts:31", "1,248 redacted request replays"],
  },
  {
    id: "KIN-2794",
    dependencyType: "API",
    title: "SendGrid rate-limit reset format changed",
    api: "SendGrid",
    endpoint: "POST /v3/mail/send",
    detected: "May 22, 09:42",
    environment: "Staging",
    severity: "Medium",
    state: "Monitoring",
    applications: ["Notification Service"],
    workflows: ["Transactional Email"],
    baseline: { status: 202, rate_limit_remaining: 42, rate_limit_reset: "42" },
    current: { status: 202, rate_limit_remaining: 42, rate_limit_reset: 1717248060 },
    proposalTitle: "Normalize the rate-limit reset representation",
    problem: "The reset value changed from a relative string to a numeric timestamp.",
    expected: "Retry scheduling receives a normalized timestamp without assuming the provider's undocumented unit.",
    operation: "normalize_timestamp(rate_limit_reset) · semantic unit requires human confirmation",
    originalCode: `const retryAfter = Number(response.rate_limit_reset);`,
    proposedCode: `const retryAfter = normalizeResetTime(response.rate_limit_reset);`,
    supported: false,
    evidence: ["86 observed responses", "No updated provider contract", "No independent unit confirmation"],
  },
  {
    id: "KIN-SDK-102",
    dependencyType: "SDK",
    title: "Stripe SDK method signature changed",
    api: "Stripe SDK",
    endpoint: "confirmPayment · npm",
    detected: "Today, 11:48",
    environment: "Staging",
    severity: "High",
    state: "Pending review",
    applications: ["Web App"],
    workflows: ["Checkout"],
    baseline: { package: "@stripe/stripe-js", version: "4.1.0", signature: "confirmPayment(options)" },
    current: { package: "@stripe/stripe-js", version: "4.2.0", signature: "confirmPayment(elements, options)" },
    proposalTitle: "Introduce an explicit payment wrapper migration",
    problem: "The imported declaration snapshot shows a changed confirmPayment signature.",
    expected: "Checkout continues compiling against a stable internal wrapper while the package migration is reviewed.",
    operation: "wrapper_migration(confirmPayment) · requires project type checks and developer review",
    originalCode: `await stripe.confirmPayment(options);`,
    proposedCode: `await payments.confirm({ elements, options });`,
    supported: false,
    evidence: ["Simulated package manifest comparison", "Imported TypeScript declaration snapshot", "SDK monitoring backend unavailable"],
  },
  {
    id: "KIN-MCP-104",
    dependencyType: "MCP Server",
    title: "MCP tool input schema changed",
    api: "Travel Tools MCP",
    endpoint: "search_flights tool",
    detected: "Today, 10:32",
    environment: "Staging",
    severity: "Medium",
    state: "Pending review",
    applications: ["Travel Assistant"],
    workflows: ["Flight Search"],
    baseline: { tool: "search_flights", required: "origin,destination" },
    current: { tool: "search_flights", required: "origin,destination,locale" },
    proposalTitle: "Adapt the tool input through a reviewed compatibility wrapper",
    problem: "The imported capability snapshot adds locale as a required tool input.",
    expected: "The travel workflow supplies an explicit locale without invoking unsupported tools automatically.",
    operation: "adapt_tool_input(locale) · protocol and invocation tests required",
    originalCode: `callTool("search_flights", { origin, destination });`,
    proposedCode: `callTool("search_flights", { origin, destination, locale });`,
    supported: false,
    evidence: ["Simulated MCP capability snapshot", "No live server connection", "MCP monitoring backend unavailable"],
  },
  {
    id: "KIN-WHK-108",
    dependencyType: "Webhook",
    title: "Payment webhook payload field changed",
    api: "Stripe Payment Webhook",
    endpoint: "payment.succeeded",
    detected: "Today, 09:18",
    environment: "Staging",
    severity: "High",
    state: "Pending review",
    applications: ["Order Management App", "Notification Service"],
    workflows: ["Order Confirmation", "Receipt Delivery"],
    baseline: { event: "payment.succeeded", id: "evt_108", customer_name: "Annual Pro Plan", delivery_status: 200 },
    current: { event: "payment.succeeded", id: "evt_108", customer_display_name: "Annual Pro Plan", delivery_status: 200 },
    proposalTitle: "Normalize the reported webhook payload at the event boundary",
    problem: "A provider-reported redacted fixture replaces customer_name with customer_display_name. No live delivery failure is used to infer this change.",
    expected: "Configured event handlers continue receiving the stable customer_name field while idempotency and signature checks remain unchanged.",
    operation: "map_payload_field(customer_display_name → customer_name) · fixture replay and developer review required",
    originalCode: `const customerName = event.data.customer_name;`,
    proposedCode: `const customerName = event.data.customer_display_name ?? event.data.customer_name;`,
    supported: false,
    evidence: ["Provider-reported redacted fixture comparison", "Registered payment.succeeded subscription", "Handler reference at event-handlers/payment-succeeded.ts", "No live receiver, signature result, or delivery replay backend"],
  },
];

export const incidentIdForChange = (change: ChangeRecord) =>
  change.dependencyType === "SDK"
    ? "KIN-SDK-102"
    : change.dependencyType === "MCP Server"
    ? "KIN-MCP-104"
    : change.dependencyType === "Webhook"
    ? "KIN-WHK-108"
    : change.id === "CHG-838"
    ? "KIN-2794"
    : "KIN-2841";

export const navItems: { id: Screen; label: string; icon: IconName }[] = [
  { id: "overview", label: "Overview", icon: "home" },
  { id: "projects", label: "Projects", icon: "shield" },
  { id: "dependencies", label: "Dependencies", icon: "dependency" },
  { id: "changes", label: "Change Detection", icon: "activity" },
  { id: "graph", label: "AI Dependency Graph", icon: "graph" },
  { id: "recovery", label: "Recovery Studio", icon: "recovery" },
  { id: "validation", label: "Validation Lab", icon: "test" },
  { id: "history", label: "Recovery History", icon: "history" },
  { id: "integrations", label: "Integrations", icon: "api" },
  { id: "settings", label: "Settings", icon: "settings" },
];

export const screenMeta: Record<Screen, [string, string]> = {
  overview: ["Overview", "Monitor your dependencies, investigate changes, and track recovery."],
  projects: ["Projects", "Manage the applications protected by KintsuTech."],
  dependencies: ["Dependencies", "Manage APIs, SDK packages, MCP servers, and webhooks with type-specific evidence."],
  changes: ["Change Detection", "Review observed contract, behaviour, and protocol anomalies."],
  graph: ["AI Dependency Graph", "Explore applications, external dependencies, and established component relationships."],
  recovery: ["Recovery Studio", "Incident analysis, controlled repair, and evidence-based approval."],
  validation: ["Validation Lab", "Verify generated adaptations in an isolated environment."],
  history: ["Recovery History", "Review recovery decisions, evidence, and audit history."],
  integrations: ["Integrations", "Connect contracts and developer workflow evidence."],
  settings: ["Workspace settings", "Manage environments, policies, and team access."],
};

export function myersEditDistance(before: string[], after: string[]): number {
  const maximum = before.length + after.length;
  const furthest = new Map<number, number>([[1, 0]]);
  for (let depth = 0; depth <= maximum; depth += 1) {
    for (let diagonal = -depth; diagonal <= depth; diagonal += 2) {
      let x =
        diagonal === -depth ||
        (diagonal !== depth && (furthest.get(diagonal - 1) ?? -1) < (furthest.get(diagonal + 1) ?? -1))
          ? furthest.get(diagonal + 1) ?? 0
          : (furthest.get(diagonal - 1) ?? 0) + 1;
      let y = x - diagonal;
      while (x < before.length && y < after.length && before[x] === after[y]) {
        x += 1;
        y += 1;
      }
      furthest.set(diagonal, x);
      if (x >= before.length && y >= after.length) return depth;
    }
  }
  return maximum;
}
