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
    id: "CHG-842",
    dependencyType: "API",
    service: "Weather Intelligence API",
    endpoint: "GET /api/v1/mock/weather",
    category: "Renamed response field",
    severity: "Critical",
    confidence: 99.4,
    status: "Investigating",
    summary: "Response field temperature was migrated to temp_c.",
    observed: "Today, 14:35 UTC",
    evidence: "Myers diff detected on live GET /api/v1/mock/weather; downstream trip_planner and severe alert failures",
    breaking: true,
  },
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
    // Column 1: Applications & Consumers
    { id: "app-checkout", kind: "application", subtype: "Core Business Service", name: "Checkout Order Service", detail: "backend/app/checkout_service.py · POST /api/v1/checkout/process", status: "affected", project: "Pulse API", environment: "Production", evidence: "412 Precondition Failed when reading paymentIntent.name", source: "inventory" },
    { id: "app-console", kind: "application", subtype: "SPA Web Dashboard", name: "Kintsu Admin Console", detail: "Incident triage & developer studio (http://localhost:3000)", status: "healthy", project: "Pulse API", environment: "Production", evidence: "Active operator session", source: "inventory" },
    { id: "app-scheduler", kind: "application", subtype: "Escalation Engine", name: "Persistent Alert Scheduler", detail: "backend/app/scheduler.py · Telephony claim daemon", status: "healthy", project: "Pulse API", environment: "Production", evidence: "Idempotent claim & quiet hours guard active", source: "inventory" },
    { id: "app-mobile", kind: "application", subtype: "Mobile Client", name: "Client Mobile Experience", detail: "apps/mobile/weather_widget.tsx", status: "healthy", project: "Pulse API", environment: "Production", evidence: "Observed 200 OK traffic", source: "inventory" },

    // Column 2: External APIs & Gateways (Real KintsuTech APIs)
    { id: "api-products", kind: "api", subtype: "Internal REST API", name: "Product Catalog API", detail: "GET /api/v1/products", status: "healthy", project: "Pulse API", environment: "Production", provider: "Kintsu Catalog Service", method: "GET", evidence: "OpenAPI 3.1 contract active", source: "inventory" },
    { id: "api-stripe", kind: "api", subtype: "Payment & Webhooks", name: "Stripe Payment Gateway", detail: "POST /v1/payment_intents/:id · POST /webhooks/stripe", status: "affected", project: "Pulse API", environment: "Production", provider: "Stripe Inc.", method: "POST", evidence: "Incident KIN-2841: display_name -> name field mismatch", source: "inventory" },
    { id: "api-supabase", kind: "api", subtype: "Auth & GoTrue Gateway", name: "Supabase Identity Gateway", detail: "https://djmgakxzxqyquvmkhkxo.supabase.co/auth/v1", status: "healthy", project: "Pulse API", environment: "Production", provider: "Supabase Cloud", method: "POST", evidence: "Verified URL & anon key in frontend/.env.local", source: "inventory" },
    { id: "api-vapi", kind: "api", subtype: "Telephony & Voice AI", name: "Vapi Voice Agent Gateway", detail: "POST https://api.vapi.ai/call/phone · POST /api/vapi/webhook", status: "healthy", project: "Pulse API", environment: "Production", provider: "Vapi Voice Platform", method: "POST", evidence: "Assistant asst_kintsu_voice_v1; caller +12025550199", source: "inventory" },
    { id: "api-weather", kind: "api", subtype: "External REST API", name: "Weather Intelligence API", detail: "GET /api/v1/mock/weather", status: "affected", project: "Pulse API", environment: "Production", provider: "OpenWeather Mock", method: "GET", evidence: "Myers schema drift detected: temperature (removed) -> temp_c (added)", source: "inventory" },

    // Column 3: Dependent Services & Components
    { id: "dep-catalog", kind: "dependency", subtype: "Search & Cache", name: "Catalog Search Service", detail: "backend/app/catalog_service.py", status: "healthy", project: "Pulse API", environment: "Production", evidence: "In-memory cache warmed", source: "inventory" },
    { id: "dep-inventory", kind: "dependency", subtype: "Warehouse Datastore", name: "Warehouse Inventory", detail: "GET /api/v1/inventory", status: "healthy", project: "Pulse API", environment: "Production", evidence: "Stock synchronization active", source: "inventory" },
    { id: "dep-ledger", kind: "dependency", subtype: "Accounting Pipeline", name: "Billing Ledger Sync", detail: "services/ledger_sync.ts", status: "affected", project: "Pulse API", environment: "Production", evidence: "Awaiting schema repair mapping proposal", source: "inventory" },
    { id: "dep-rbac", kind: "dependency", subtype: "Security Middleware", name: "JWT RBAC Security Guard", detail: "backend/app/auth.py · HS256 verify", status: "healthy", project: "Pulse API", environment: "Production", evidence: "Validates HS256 JWT signatures on protected routes", source: "inventory" },
    { id: "dep-voice-logger", kind: "dependency", subtype: "Audit & Compliance", name: "Telephony Audit Logger", detail: "backend/app/storage.py (AlertDeliveryModel)", status: "healthy", project: "Pulse API", environment: "Production", evidence: "Verified webhook signature callbacks and delivery logs", source: "inventory" },
    { id: "dep-trip", kind: "dependency", subtype: "Core Workflow", name: "Trip Planner Engine", detail: "services/weather.ts:42", status: "affected", project: "Pulse API", environment: "Production", evidence: "Direct consumer of weather.temperature; unhandled 412 in parser", source: "inventory" },
    { id: "dep-alert", kind: "dependency", subtype: "Incident Pipeline", name: "Severe Alert Service", detail: "backend/app/scheduler.py:78", status: "affected", project: "Pulse API", environment: "Production", evidence: "Trigger threshold calculation failed on missing temperature float", source: "inventory" },
  ],
  edges: [
    // Column 1 (Applications) -> Column 2 (APIs)
    { id: "edge-checkout-products", from: "app-checkout", to: "api-products", label: "GET /api/v1/products", evidence: "confirmed", source: "Order Checkout Service", status: "healthy" },
    { id: "edge-checkout-stripe", from: "app-checkout", to: "api-stripe", label: "processes checkout (display_name)", evidence: "confirmed", source: "Incident KIN-2841", status: "affected" },
    { id: "edge-console-supabase", from: "app-console", to: "api-supabase", label: "Bearer token auth session", evidence: "confirmed", source: "Auth Middleware", status: "healthy" },
    { id: "edge-scheduler-vapi", from: "app-scheduler", to: "api-vapi", label: "outbound escalation dispatch", evidence: "confirmed", source: "Escalation Scheduler", status: "healthy" },
    { id: "edge-mobile-weather", from: "app-mobile", to: "api-weather", label: "GET /weather (cached widget)", evidence: "confirmed", source: "Application Registration", status: "affected" },

    // Column 2 (APIs) -> Column 3 (Dependencies)
    { id: "edge-products-catalog", from: "api-products", to: "dep-catalog", label: "GET /api/v1/products", evidence: "confirmed", source: "Catalog Service", status: "healthy" },
    { id: "edge-products-inventory", from: "api-products", to: "dep-inventory", label: "reserves warehouse stock", evidence: "confirmed", source: "Inventory Service", status: "healthy" },
    { id: "edge-stripe-ledger", from: "api-stripe", to: "dep-ledger", label: "payment.succeeded event", evidence: "confirmed", source: "Webhook Subscription", status: "affected" },
    { id: "edge-supabase-rbac", from: "api-supabase", to: "dep-rbac", label: "HS256 JWT claim verify", evidence: "confirmed", source: "Auth Middleware", status: "healthy" },
    { id: "edge-vapi-logger", from: "api-vapi", to: "dep-voice-logger", label: "call-report webhook callbacks", evidence: "confirmed", source: "Webhook Ingest", status: "healthy" },
    { id: "edge-weather-trip", from: "api-weather", to: "dep-trip", label: "GET /forecast (temp_c drift)", evidence: "confirmed", source: "Observed Myers Diff", status: "affected" },
    { id: "edge-weather-alert", from: "api-weather", to: "dep-alert", label: "evaluates freeze thresholds", evidence: "confirmed", source: "Scheduler Pipeline", status: "affected" },
  ],
};

export const incidentWorkspaceRecords: IncidentWorkspaceRecord[] = [
  {
    id: "KIN-2842",
    dependencyType: "API",
    title: "Weather API temperature field migrated to temp_c",
    api: "Weather Intelligence API",
    endpoint: "GET /api/v1/mock/weather",
    detected: "Today, 14:35",
    environment: "Staging",
    severity: "Critical",
    state: "Pending review",
    applications: ["Client Mobile Experience", "Trip Planner Engine", "Severe Alert Service"],
    workflows: ["Travel Weather Advisory", "Freeze Alert Evaluation"],
    baseline: { city: "San Francisco", condition: "Sunny", humidity: 65, temperature: 21.5, status: "active" },
    current: { city: "San Francisco", condition: "Sunny", humidity: 65, temp_c: 21.5, status: "active" },
    proposalTitle: "Preserve the internal temperature contract with temp_c fallback",
    problem: "Upstream mock weather provider renamed 'temperature' to 'temp_c'. Downstream trip planner and alert scheduler fail with 412 unhandled key errors.",
    expected: "Downstream travel workflows and severe alert evaluation receive a normalized temperature field without runtime failure.",
    operation: "map_field(temp_c → temperature) with legacy fallback and unit preservation",
    originalCode: `export function parseWeatherData(payload: RawWeatherResponse) {\n  return {\n    city: payload.city,\n    temperature: payload.temperature,\n    condition: payload.condition\n  };\n}`,
    proposedCode: `export function parseWeatherData(payload: RawWeatherResponse) {\n  return {\n    city: payload.city,\n    temperature: payload.temp_c ?? payload.temperature,\n    sourceField: payload.temp_c !== undefined ? "temp_c" : "temperature",\n    condition: payload.condition\n  };\n}`,
    supported: true,
    evidence: ["Myers diff score: 98.4% confidence", "Endpoint GET /api/v1/mock/weather live probe", "Downstream failure at services/weather.ts:42", "Scheduler freeze alert calculation regression"],
  },
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

export const incidentIdForChange = (change: ChangeRecord) => {
  if (change.id === "CHG-842" || change.service?.toLowerCase().includes("weather") || change.endpoint?.includes("weather")) {
    return "KIN-2842";
  }
  if (change.dependencyType === "SDK") return "KIN-SDK-102";
  if (change.dependencyType === "MCP Server") return "KIN-MCP-104";
  if (change.dependencyType === "Webhook") return "KIN-WHK-108";
  if (change.id === "CHG-838" || change.service?.toLowerCase().includes("sendgrid")) return "KIN-2794";
  return "KIN-2841";
};

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
  chat: ["AI Agent Chat", "Grounded conversational diagnostics, change analysis, and voice interaction."],
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
