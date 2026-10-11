# KintsuTech Frontend

KintsuTech is an API change detection, impact analysis, AI-assisted repair, validation, and recovery platform.

> **Tagline:** Detect. Adapt. Recover.

---

## Technology Stack

- **Framework:** Next.js (App Router)
- **Language:** TypeScript
- **Styling:** Tailwind CSS & custom design tokens
- **Icons:** Lucide React & custom Japanese Kintsugi SVG icons
- **State Management:** React hooks with persistent localStorage sync
- **Auth Integration:** Supabase Client (`@supabase/supabase-js`) & FastAPI backend JWT verification

---

## Features & Screens

1. **Editorial Landing Page:**
   - Brand overview ("When APIs break, connections heal")
   - Simulated interactive connection & recovery animation
   - Interactive JSON before/after demonstration
2. **Projects View (`/projects`):**
   - 2-column card grid for protected applications (**Pulse API** & **Atlas Commerce**)
   - Real-time search, status indicators, and 4-metric statistics summary
   - 8-step Create Project wizard
   - Project details drawer
3. **Dependencies View (`/dependencies`):**
   - Multi-type filter bar (Search, Status, Dependency Type, Severity, Sort)
   - Table view and card view toggle
   - Type-specific monitoring for APIs, SDKs, MCP servers, and Webhooks
   - Multi-tab details drawer (Overview, Components, Observed Behaviour, Change History, Configuration)
   - Add Dependency modal with connection testing
4. **Change Detection (`/changes` under Investigate):**
   - Evidence filters for categories, severities, and states
   - Observation cards with confidence scores and breaking status
   - Centered empty-state view matching reference designs
   - Myers diff comparison viewer and observation dismissal modal
5. **AI Dependency Graph (`/graph` under Investigate):**
   - 3-column architecture (Applications, External Dependencies, Dependency Components)
   - SVG Bezier curves with dynamic fracture styling for affected paths
   - Interactive zoom & pan controls
   - Impact tracing and node detail panel
6. **Recovery Studio (`/recovery` under Repair):**
   - 9-stage guided recovery workflow:
     - 00 Summary
     - 01 What Changed (Myers diff JSON comparison)
     - 02 Similar Incidents
     - 03 AI Analysis
     - 04 Safety Check (Supported operations checklist)
     - 05 Proposed Fix (Code diff editor and export)
     - 06 Test Results (14 deterministic checks with failure scenario)
     - 07 Review & Approve (Human platform engineer approval gate)
     - 08 Activity Timeline
7. **Validation Lab (`/validation` under Repair):**
   - Deterministic test execution sandbox across API, SDK, MCP, and Webhook categories
8. **Recovery History (`/history`):**
   - Comprehensive audit log with incident codes, diff summaries, and decisions
   - Report export download
   - Historical report drawer
9. **Integrations (`/settings/integrations`):**
   - 8 integration cards with exact badge states (OpenAPI, GitHub, CI, Observability, Notifications, SDKs, MCP, Webhooks)
   - Built-in JSON OpenAPI specification parser and baseline saver
10. **Kintsu Copilot:**
    - AI assistant drawer accessible from anywhere in the workspace
    - Contextual Q&A grounded in active case evidence
    - Simulated voice input toggle
11. **Autonomous AI Agent Chat & Voice Integration (`/chat`):**
    - Full-page dedicated AI Agent conversation interface
    - Grounded responses backed by live FastAPI backend tools (`POST /api/v1/agent/chat`)
    - Real-time diagnostic tool calling (system health, service telemetry, dependency blast radius, repair proposals, rollback assessment)
    - Web Speech API **Speech-to-Text** voice input (Microphone button, recording pulse, permission handling)
    - Web Speech API **Text-to-Speech** voice output (Listen button on assistant bubbles, pause/resume/stop, voice rate and language settings)
    - Hands-free auto-send speech mode and starter prompt chips
    - Conversation history persisted with clear confirmation
12. **Supabase Authentication:**
    - Modal for sign in / sign up
    - Role-based identity display and token verification

---

## Local Development

```bash
# Install dependencies
npm install

# Run development server
npm run dev

# Run type check
npx tsc --noEmit

# Run linter
npm run lint

# Build production bundle
npm run build
```

The frontend will be available at [http://localhost:3000](http://localhost:3000).

---

## Environment Variables

Copy `.env.example` to `.env.local`:

```bash
cp .env.example .env.local
```

Set the public environment variables:
- `NEXT_PUBLIC_API_URL`: URL of the FastAPI backend (default: `http://localhost:8000`)
- `NEXT_PUBLIC_SUPABASE_URL`: Supabase project URL
- `NEXT_PUBLIC_SUPABASE_ANON_KEY`: Supabase public anon key

> **Security Note:** Private API keys, JWT secrets, and Supabase service-role keys are never exposed in the frontend.
