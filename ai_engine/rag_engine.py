
import json
import math
from pathlib import Path

import ollama


EMBEDDING_MODEL = "nomic-embed-text:latest"
INCIDENTS_FILE = Path(__file__).parent / "incidents.json"


def get_embedding(text: str) -> list[float]:
    """Convert text into a vector using the local Ollama model."""
    response = ollama.embed(
        model=EMBEDDING_MODEL,
        input=text,
    )

    return response["embeddings"][0]


def cosine_similarity(
    vector_a: list[float],
    vector_b: list[float],
) -> float:
    """Measure similarity between two embedding vectors."""
    dot_product = sum(a * b for a, b in zip(vector_a, vector_b))

    magnitude_a = math.sqrt(sum(a * a for a in vector_a))
    magnitude_b = math.sqrt(sum(b * b for b in vector_b))

    if magnitude_a == 0 or magnitude_b == 0:
        return 0.0

    return dot_product / (magnitude_a * magnitude_b)


def incident_text(incident: dict) -> str:
    """Combine incident fields into searchable text."""
    return " ".join(
        [
            incident["title"],
            incident["change"],
            incident["symptoms"],
            incident["root_cause"],
            incident["verified_repair"],
            incident["verification"],
        ]
    )


def retrieve_incidents(
    query: str,
    top_k: int = 2,
) -> list[dict]:
    """Return the most similar historical incidents."""
    if top_k < 1:
        raise ValueError("top_k must be at least 1")

    with INCIDENTS_FILE.open("r", encoding="utf-8") as file:
        incidents = json.load(file)

    query_embedding = get_embedding(query)
    ranked_incidents = []

    for incident in incidents:
        text = incident_text(incident)
        embedding = get_embedding(text)

        score = cosine_similarity(query_embedding, embedding)

        ranked_incidents.append(
            {
                **incident,
                "similarity": round(score, 4),
            }
        )

    ranked_incidents.sort(
        key=lambda item: item["similarity"],
        reverse=True,
    )

    return ranked_incidents[:top_k]


if __name__ == "__main__":
    query = (
        "The old API response had temperature, "
        "but the new response has temp_c. "
        "Older clients may fail because the expected field is missing."
    )

    results = retrieve_incidents(query, top_k=2)

    print("\nSimilar historical incidents:\n")

    for incident in results:
        print(json.dumps(incident, indent=2))
        print("-" * 50)
