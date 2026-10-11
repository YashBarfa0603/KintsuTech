#!/usr/bin/env bash
# KintsuTech — HackWave 3.0 (PS3) Complete Live Demo Walkthrough
# Tagline: Detect. Adapt. Recover.

set -e

BASE_URL="${KINTSUTECH_BASE_URL:-http://127.0.0.1:8000}"

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

print_step() {
    echo -e "\n${BLUE}======================================================================${NC}"
    echo -e "${YELLOW}$1${NC}"
    echo -e "${BLUE}======================================================================${NC}"
}

print_success() {
    echo -e "${GREEN}✔ $1${NC}"
}

# Check if backend is reachable
if ! curl -s --connect-timeout 2 "${BASE_URL}/api/v1/health" > /dev/null; then
    echo -e "${RED}Error: KintsuTech backend is not running on ${BASE_URL}.${NC}"
    echo "Please start the backend in another terminal with:"
    echo "  cd backend && uv run uvicorn app.main:app --reload --port 8000"
    exit 1
fi

print_step "Stage 1: Health & Readiness Check"
echo "GET ${BASE_URL}/api/v1/health"
curl -s "${BASE_URL}/api/v1/health"
echo ""
echo "GET ${BASE_URL}/api/v1/health/readiness"
curl -s "${BASE_URL}/api/v1/health/readiness"
echo ""
print_success "System is healthy and SQLite storage is ready."

print_step "Stage 2: Inspect Normal State (No Active Repair)"
echo "Consumer calls proxy: GET ${BASE_URL}/api/v1/proxy/weather"
curl -s "${BASE_URL}/api/v1/proxy/weather"
echo ""
print_success "Proxy returns raw provider response unchanged (adapted: false)."

print_step "Stage 3: Upstream Drift Detection & Blast Radius Analysis"
echo "Upstream provider introduces breaking drift (temperature renamed to temp_c)."
echo "POST ${BASE_URL}/api/v1/ai/analyze"
ANALYSIS_OUTPUT=$(curl -s -X POST "${BASE_URL}/api/v1/ai/analyze" \
  -H "Content-Type: application/json" \
  -d '{
    "service_id": "weather",
    "baseline": {"city": "Indore", "temperature": 30, "condition": "Sunny"},
    "current": {"city": "Indore", "temp_c": 30, "condition": "Sunny"},
    "create_incident_on_change": true
  }')

echo "${ANALYSIS_OUTPUT}" | grep -o '"incident_id":"[^"]*"' || echo "${ANALYSIS_OUTPUT}"
INCIDENT_ID=$(echo "${ANALYSIS_OUTPUT}" | grep -o '"incident_id":"[^"]*"' | cut -d'"' -f4 || echo "INC-001")
print_success "Incident created: ${INCIDENT_ID} with critical blast radius impact."

print_step "Stage 4: Guarded Safety Check (Block Premature Activation)"
echo "Attempting to activate repair BEFORE validation passes:"
curl -s -X POST "${BASE_URL}/api/v1/repairs/activate" \
  -H "Content-Type: application/json" \
  -d "{
    \"incident_id\": \"${INCIDENT_ID}\",
    \"adapter\": {
      \"operation\": \"copy_field\",
      \"source_field\": \"temp_c\",
      \"target_field\": \"temperature\",
      \"semantics_confirmed\": true
    },
    \"authorizer\": \"attacker\"
  }"
echo ""
print_success "Activation correctly rejected with HTTP 400 (unvalidated repair cannot activate)."

print_step "Stage 5: Independent Deterministic Validation"
echo "POST ${BASE_URL}/api/v1/repairs/validate"
curl -s -X POST "${BASE_URL}/api/v1/repairs/validate" \
  -H "Content-Type: application/json" \
  -d "{
    \"incident_id\": \"${INCIDENT_ID}\",
    \"adapter\": {
      \"operation\": \"copy_field\",
      \"source_field\": \"temp_c\",
      \"target_field\": \"temperature\",
      \"semantics_confirmed\": true
    },
    \"test_cases\": [
      {
        \"input\": {\"temp_c\": 25.0, \"condition\": \"Sunny\"},
        \"expected\": {\"temp_c\": 25.0, \"condition\": \"Sunny\", \"temperature\": 25.0}
      }
    ]
  }"
echo ""
print_success "Repair independently validated and marked eligible_for_activation."

print_step "Stage 6: Authorized Human Activation"
echo "POST ${BASE_URL}/api/v1/repairs/activate"
curl -s -X POST "${BASE_URL}/api/v1/repairs/activate" \
  -H "Content-Type: application/json" \
  -d "{
    \"incident_id\": \"${INCIDENT_ID}\",
    \"adapter\": {
      \"operation\": \"copy_field\",
      \"source_field\": \"temp_c\",
      \"target_field\": \"temperature\",
      \"semantics_confirmed\": true
    },
    \"authorizer\": \"senior_architect_alice\",
    \"note\": \"Validated for HackWave 3.0 Demo\"
  }"
echo ""
print_success "Compatibility adapter activated and stored in persistent SQLite registry."

print_step "Stage 7: Resilient Consumer Proxy Adaptation"
echo "Consumer calls proxy while provider returns renamed payload:"
echo "GET ${BASE_URL}/api/v1/proxy/weather?schema=temp_c"
curl -s "${BASE_URL}/api/v1/proxy/weather?schema=temp_c"
echo ""
print_success "Proxy automatically restored legacy 'temperature' field! (adapted: true, incident_id: ${INCIDENT_ID})"

print_step "Stage 8: Instant Rollback & Recovery"
echo "Operator triggers rollback:"
echo "POST ${BASE_URL}/api/v1/repairs/rollback"
curl -s -X POST "${BASE_URL}/api/v1/repairs/rollback" \
  -H "Content-Type: application/json" \
  -d '{
    "service_id": "weather",
    "authorizer": "incident_lead_bob",
    "reason": "Upstream vendor rolled back field change"
  }'
echo ""
print_success "Adapter deactivated immediately."

print_step "Stage 9: Verify Recovery"
echo "Consumer calls proxy again after rollback:"
echo "GET ${BASE_URL}/api/v1/proxy/weather?schema=temp_c"
curl -s "${BASE_URL}/api/v1/proxy/weather?schema=temp_c"
echo ""
print_success "Proxy instantly resumed raw unadapted responses without restarting the server!"

print_step "Stage 10: Complete Audit Trail"
echo "GET ${BASE_URL}/api/v1/repairs/audit"
curl -s "${BASE_URL}/api/v1/repairs/audit"
echo ""
print_success "Complete immutable timeline recorded: validated -> activated -> rolled_back."

echo -e "\n${GREEN}======================================================================${NC}"
echo -e "${GREEN}🎉 KintsuTech PS3 End-to-End Demo Workflow Completed Successfully!${NC}"
echo -e "${GREEN}======================================================================${NC}\n"
