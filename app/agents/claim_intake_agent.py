import json
import os
from collections.abc import Mapping
from typing import Any, TypedDict

import httpx
from langgraph.graph import END, START, StateGraph
from python_a2a import Message, MessageRole, Task, TaskState, TextContent


POLICY_AGENT_URL = os.getenv("POLICY_AGENT_URL", "http://127.0.0.1:5001")
DAMAGE_AGENT_URL = os.getenv("DAMAGE_AGENT_URL", "http://127.0.0.1:5002")
A2A_TIMEOUT_SECONDS = int(os.getenv("CLAIM_INTAKE_A2A_TIMEOUT_SECONDS", "180"))

_CLAIM_FIELDS = (
    "claim_id",
    "customer_id",
    "policy_id",
    "incident_date",
    "incident_type",
)
_MISSING_QUESTIONS = {
    "claim_id": "What is the claim ID?",
    "customer_id": "What is the customer ID?",
    "policy_id": "Which policy ID should be checked?",
    "incident_date": "What was the incident date? Please use YYYY-MM-DD.",
    "incident_type": "What type of incident occurred?",
    "evidence_files or additional_context": (
        "Please provide supporting evidence files or a description of the "
        "damage and repair evidence."
    ),
}


class ClaimIntakeState(TypedDict, total=False):
    claim: dict[str, Any]
    claim_text: str
    evidence_files: list[str]
    policy_result: dict[str, Any]
    damage_result: dict[str, Any]
    report: dict[str, Any]


def _is_present(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


async def _call_agent_async(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    message = Message(
        content=TextContent(text=json.dumps(payload, ensure_ascii=False)),
        role=MessageRole.USER,
    )
    task_request = Task(message=message.to_dict())
    async with httpx.AsyncClient(timeout=A2A_TIMEOUT_SECONDS) as client:
        response = await client.post(
            f"{url.rstrip('/')}/tasks/send",
            json={
                "jsonrpc": "2.0",
                "id": task_request.id,
                "method": "tasks/send",
                "params": task_request.to_dict(),
            },
        )
        response.raise_for_status()
        response_data = response.json()
    if "error" in response_data:
        raise RuntimeError(f"A2A request to {url} failed: {response_data['error']}")
    task_data = response_data.get("result")
    if not isinstance(task_data, dict):
        raise ValueError(f"A2A agent at {url} returned no task result")
    task = Task.from_dict(task_data)
    if task.status.state == TaskState.FAILED:
        raise RuntimeError(f"A2A request to {url} failed: {task.status.message}")

    response_text = next(
        (
            part["text"]
            for artifact in task.artifacts
            for part in artifact.get("parts", [])
            if part.get("type") == "text" and isinstance(part.get("text"), str)
        ),
        None,
    )
    if response_text is None:
        raise ValueError(f"A2A agent at {url} returned no text result")
    try:
        response = json.loads(response_text)
    except json.JSONDecodeError as error:
        raise ValueError(f"A2A agent at {url} returned invalid JSON") from error
    if not isinstance(response, dict):
        raise ValueError(f"A2A agent at {url} returned a non-object response")
    return response


async def _call_policy_agent(state: ClaimIntakeState) -> dict[str, Any]:
    claim = state["claim"]
    required_fields = ("customer_id", "incident_date", "incident_type")
    missing = [field for field in required_fields if not _is_present(claim.get(field))]
    if missing:
        return {
            "policy_result": {
                "status": "needs_information",
                "missing_information": missing,
            }
        }

    payload = {field: claim.get(field) for field in required_fields}
    if _is_present(claim.get("policy_id")):
        payload["policy_id"] = claim["policy_id"]
    return {"policy_result": await _call_agent_async(POLICY_AGENT_URL, payload)}


async def _call_damage_agent(state: ClaimIntakeState) -> dict[str, Any]:
    claim = state["claim"]
    claim_id = claim.get("claim_id")
    claim_text = state.get("claim_text", "").strip()
    evidence_files = state.get("evidence_files", [])
    if not _is_present(claim_id):
        return {
            "damage_result": {
                "status": "needs_information",
                "missing_information": ["claim_id"],
            }
        }
    if not evidence_files and not claim_text:
        return {
            "damage_result": {
                "status": "needs_information",
                "missing_information": ["evidence_files or additional_context"],
            }
        }

    payload: dict[str, Any] = {"claim_id": claim_id}
    if evidence_files:
        payload["evidence_files"] = evidence_files
    if claim_text:
        payload["additional_context"] = claim_text
    return {"damage_result": await _call_agent_async(DAMAGE_AGENT_URL, payload)}


def _missing_questions(
    policy_result: Mapping[str, Any],
    damage_result: Mapping[str, Any],
) -> list[dict[str, str]]:
    questions: list[dict[str, str]] = []
    seen: set[str] = set()
    for result in (policy_result, damage_result):
        missing = result.get("missing_information", [])
        if not isinstance(missing, list):
            continue
        for item in missing:
            if not isinstance(item, str):
                continue
            question = _MISSING_QUESTIONS.get(
                item,
                (
                    "Please provide the incident date in YYYY-MM-DD format."
                    if item.startswith("incident_date")
                    else f"Please provide or confirm {item}."
                ),
            )
            if question not in seen:
                questions.append({"field": item, "question": question})
                seen.add(question)
    return questions


def _assemble_report(state: ClaimIntakeState) -> dict[str, Any]:
    policy_result = state.get("policy_result", {})
    damage_result = state.get("damage_result", {})
    missing_information = _missing_questions(policy_result, damage_result)
    next_steps: list[str] = []

    if missing_information:
        next_steps.append(
            "Collect the requested information and resubmit the claim for review."
        )
    else:
        if policy_result.get("status") != "facts_match_for_review":
            next_steps.append(
                "Have a claims reviewer verify the policy findings and resolve "
                "any conflicts."
            )
        if damage_result.get("status") != "assessed":
            next_steps.append(
                "Have a claims reviewer complete or review the damage assessment."
            )
        if damage_result.get("evidence_assessments"):
            flagged = any(
                assessment.get("assessment", {}).get("suspicious_indicators")
                for assessment in damage_result["evidence_assessments"]
                if isinstance(assessment, dict)
                and isinstance(assessment.get("assessment"), dict)
            )
            if flagged:
                next_steps.append(
                    "Review the damage assessment's suspicious indicators; they "
                    "are flags for investigation, not proof of fraud."
                )
        next_steps.append(
            "Review the findings and make any coverage or liability decision "
            "through the normal human claims process."
        )

    return {
        "report": {
            "status": "needs_information" if missing_information else "ready_for_review",
            "claim": state["claim"],
            "claim_text": state.get("claim_text", ""),
            "policy_review": policy_result,
            "damage_review": damage_result,
            "missing_information": missing_information,
            "next_steps": next_steps,
            "decision": None,
            "decision_note": (
                "The Policy and Damage agents provide review findings only. "
                "This intake agent does not make a coverage, liability, or "
                "fraud determination."
            ),
        }
    }


def _build_graph() -> Any:
    builder = StateGraph(ClaimIntakeState)
    builder.add_node("policy_review", _call_policy_agent)
    builder.add_node("damage_review", _call_damage_agent)
    builder.add_node("assemble_report", _assemble_report)
    builder.add_edge(START, "policy_review")
    builder.add_edge(START, "damage_review")
    builder.add_edge(["policy_review", "damage_review"], "assemble_report")
    builder.add_edge("assemble_report", END)
    return builder.compile()


claim_intake_graph = _build_graph()


def normalize_claim_intake_request(
    request_data: Mapping[str, Any],
) -> ClaimIntakeState:
    raw_claim = request_data.get("claim")
    if raw_claim is None:
        claim = {
            field: request_data[field]
            for field in _CLAIM_FIELDS
            if field in request_data
        }
    elif isinstance(raw_claim, dict):
        claim = dict(raw_claim)
    else:
        raise ValueError("claim must be a JSON object")

    raw_claim_text = request_data.get(
        "claim_text",
        request_data.get(
            "additional_context",
            claim.get("incident_description", ""),
        ),
    )
    if not isinstance(raw_claim_text, str):
        raise ValueError("claim_text must be a string")

    evidence_files = request_data.get("evidence_files", [])
    if not isinstance(evidence_files, list) or not all(
        isinstance(path, str) and path.strip() for path in evidence_files
    ):
        raise ValueError("evidence_files must be a list of non-empty path strings")

    return {
        "claim": claim,
        "claim_text": raw_claim_text,
        "evidence_files": evidence_files,
    }


async def run_claim_intake(request_data: Mapping[str, Any]) -> dict[str, Any]:
    """Run the LangGraph workflow for a validated claim-intake request."""
    state = normalize_claim_intake_request(request_data)
    result = await claim_intake_graph.ainvoke(state)
    report = result.get("report")
    if not isinstance(report, dict):
        raise RuntimeError("Claim Intake graph completed without a report")
    return report
