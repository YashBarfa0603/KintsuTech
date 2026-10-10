
import json

import ollama

from rag_engine import retrieve_incidents
from schemas import RepairProposal


MODEL_NAME = "qwen2.5:3b"


def analyze_api_change(
    baseline: dict,
    current: dict,
    change_report: dict | None = None,
) -> RepairProposal:
    # Step 1: Include detector findings in the retrieval query.
    query = (
        f"Original API response: {json.dumps(baseline)}\n"
        f"Current API response: {json.dumps(current)}\n"
        f"Detected changes: {json.dumps(change_report or {})}"
    )

    # Step 2: Retrieve similar historical incidents.
    similar_incidents = retrieve_incidents(query, top_k=2)

    incident_context = json.dumps(
        [
            {
                "id": incident["id"],
                "title": incident["title"],
                "change": incident["change"],
                "symptoms": incident["symptoms"],
                "repair_guidance": incident["verified_repair"],
                "verification": incident["verification"],
                "similarity": incident["similarity"],
            }
            for incident in similar_incidents
        ],
        indent=2,
    )

    # Step 3: Prepare the reasoning prompt.
    prompt = f"""
You are the cautious API compatibility analyst for KintsuTech.

Analyze the original and current API responses using the evidence below.

STRICT RULES:
1. Treat the detector report as the record of detected changes.
2. Distinguish detected facts from your hypotheses.
3. Do not infer a field's meaning or unit from its name alone.
4. Equal values do not prove that two fields are equivalent.
5. Explain possible impact on existing API consumers.
6. Use historical incidents as reference material, not as proof.
7. Do not invent a safe mapping when evidence is insufficient.
8. Recommend investigation if additional evidence is required.
9. Confidence must reflect the quality of available evidence.
10. Never claim a repair has been tested or activated.
11. Every proposal must require validation.

Return a JSON object matching the required schema.

Required fields:
- change_summary: string
- evidence: array of strings
- potential_impact: string
- proposed_repair: string
- confidence: number from 0 to 1
- requires_validation: true

DETERMINISTIC CHANGE REPORT:
{json.dumps(change_report or {}, indent=2)}

ORIGINAL API RESPONSE:
{json.dumps(baseline, indent=2)}

CURRENT API RESPONSE:
{json.dumps(current, indent=2)}

RELEVANT HISTORICAL INCIDENTS:
{incident_context}
"""

    # Step 4: Ask Qwen for structured output.
    response = ollama.chat(
        model=MODEL_NAME,
        messages=[
            {
                "role": "user",
                "content": prompt,
            }
        ],
        format=RepairProposal.model_json_schema(),
        options={"temperature": 0},
    )

    # Step 5: Parse and validate the response.
    data = json.loads(response["message"]["content"])
    return RepairProposal.model_validate(data)


if __name__ == "__main__":
    baseline = {
        "temperature": 28,
        "humidity": 60,
    }

    current = {
        "temp_c": 28,
        "humidity": 60,
    }

    demo_report = {
        "has_changes": True,
        "change_count": 2,
        "breaking_change_count": 1,
        "changes": [
            {
                "type": "field_removed",
                "path": "temperature",
            },
            {
                "type": "field_added",
                "path": "temp_c",
            },
        ],
    }

    proposal = analyze_api_change(
        baseline=baseline,
        current=current,
        change_report=demo_report,
    )

    print("\nAI Repair Proposal:\n")
    print(proposal.model_dump_json(indent=2))
