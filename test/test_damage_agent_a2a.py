import json
import os

import anyio
from python_a2a import A2AClient, Message, MessageRole, Task, TextContent


DAMAGE_AGENT_URL = os.getenv(
    "DAMAGE_AGENT_URL",
    "http://127.0.0.1:5002",
)


def test_damage_agent_assesses_claim_evidence() -> None:
    """Send real PDF and image evidence through A2A, Ollama, MCP, and SQLite."""
    client = A2AClient(DAMAGE_AGENT_URL)
    response = client.ask(
        json.dumps(
            {
                "claim_id": "CLM-2001",
                "evidence_files": [
                    "01_GOOD_COMPLETE_CLAIM/INCIDENT/accident_report.pdf",
                    "01_GOOD_COMPLETE_CLAIM/DAMAGE_PHOTOS/front_damage.jpg",
                ],
            }
        )
    )
    result = json.loads(response)

    assert result["status"] == "assessed"
    assert result["claim"]["claim_id"] == "CLM-2001"
    assert any(
        check["estimate_id"] == "EST-3001"
        and check["status"] == "line_items_match_total"
        for check in result["estimate_checks"]
    )
    assert len(result["evidence_assessments"]) == 2
    assert all(
        assessment["assessment"]["confidence"] >= 0
        for assessment in result["evidence_assessments"]
    )
    assert "not a coverage" in result["decision_note"]


def test_damage_agent_task_protocol_requests_evidence() -> None:
    """Check the native A2A task endpoint without invoking the model."""
    client = A2AClient(DAMAGE_AGENT_URL)
    message = Message(
        content=TextContent(text=json.dumps({"claim_id": "CLM-2001"})),
        role=MessageRole.USER,
    )
    task = anyio.run(
        client.send_task_async,
        Task(message=message.to_dict()),
    )
    result_text = next(
        part["text"]
        for artifact in task.artifacts
        for part in artifact["parts"]
        if part.get("type") == "text"
    )
    result = json.loads(result_text)

    assert task.status.state.value == "completed"
    assert result == {
        "status": "needs_information",
        "missing_information": ["evidence_files or additional_context"],
    }


if __name__ == "__main__":
    test_damage_agent_task_protocol_requests_evidence()
    test_damage_agent_assesses_claim_evidence()
    print("Damage Agent A2A integration check passed.")
