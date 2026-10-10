
import json
import ollama

from rag_engine import retrieve_incidents
from schemas import RepairProposal


MODEL_NAME = "qwen2.5:3b"


def analyze_api_change(
    baseline: dict,
    current: dict,
) -> RepairProposal:
    # Step 1: Prepare a search query from the API change.
    query = (
        f"Original API response: {json.dumps(baseline)}\n"
        f"Current API response: {json.dumps(current)}"
    )

    # Step 2: Retrieve similar historical incidents using RAG.
    similar_incidents = retrieve_incidents(query, top_k=2)

    # Step 3: Build a compact context for the LLM.
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

    # Step 4: Ask Qwen to analyze the change using current evidence
    # and retrieved incidents without blindly trusting past repairs.
    prompt = f"""
You are the cautious API compatibility analyst for KintsuTech.

Analyze the original and current API responses.

STRICT RULES:
1. Report facts supported by the supplied evidence.
2. Do not infer a field's meaning or unit from its name alone.
3. Equal values do not prove that two fields are equivalent.
4. Identify fields that disappeared and fields that were added.
5. Explain how the change may affect existing API consumers.
6. Use historical incidents as reference material, not as proof.
7. Do not invent a safe mapping when evidence is insufficient.
8. If more information is needed, recommend investigation.
9. Confidence must reflect the quality of the available evidence.
10. Never claim a repair has been tested or activated.
11. Every proposal must require validation.
12. Propose a concrete repair only when the evidence supports it.

Return a JSON object matching the required schema.

Required fields:
- change_summary: string
- evidence: array of strings
- potential_impact: string
- proposed_repair: string
- confidence: number from 0 to 1
- requires_validation: true

Relevant historical incidents (reference material only):
{incident_context}

Original API response:
{json.dumps(baseline, indent=2)}

Current API response:
{json.dumps(current, indent=2)}
"""

    # Step 5: Generate structured output with the local Qwen model.
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

    # Step 6: Parse and validate the response.
    content = response["message"]["content"]
    data = json.loads(content)

    return RepairProposal.model_validate(data)


if __name__ == "__main__":
    baseline = {"temperature": 28}
    current = {"temp_c": 28}

    proposal = analyze_api_change(
        baseline=baseline,
        current=current,
    )

    print("\nAI Repair Proposal:\n")
    print(proposal.model_dump_json(indent=2))
