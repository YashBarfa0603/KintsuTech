
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from pydantic import ValidationError

from schemas import RepairProposal


def test_valid_proposal():
    proposal = RepairProposal(
        change_summary="An API field was removed and another was added.",
        evidence=[
            "The original response contains temperature.",
            "The current response contains temp_c.",
        ],
        potential_impact="Consumers expecting temperature may fail.",
        proposed_repair="Confirm field semantics and units before mapping.",
        confidence=0.5,
    )

    assert proposal.requires_validation is True


def test_confidence_above_one_is_rejected():
    with pytest.raises(ValidationError):
        RepairProposal(
            change_summary="Test",
            evidence=["Test evidence"],
            potential_impact="Unknown",
            proposed_repair="Investigate",
            confidence=1.5,
        )


def test_validation_cannot_be_disabled():
    with pytest.raises(ValidationError):
        RepairProposal(
            change_summary="Test",
            evidence=["Test evidence"],
            potential_impact="Unknown",
            proposed_repair="Investigate",
            confidence=0.5,
            requires_validation=False,
        )
