import json
import os
from collections.abc import Mapping
from datetime import date
from typing import Any

import anyio
from python_a2a import (
    A2AServer,
    Task,
    TaskState,
    TaskStatus,
    agent,
    run_server,
    skill,
)

from app.mcp.client import MCP_SERVER_URL, PolicyAgentMCPClient


def _as_mapping(value: object, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"MCP response field {field_name!r} was not an object")
    return value


def _as_records(value: object, field_name: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        raise ValueError(f"MCP response field {field_name!r} was not a list")
    return [_as_mapping(item, field_name) for item in value]


@agent(
    name="Insurance Policy and Eligibility Agent",
    description=(
        "Checks customer and policy records, incident dates, listed perils, "
        "and customer claim history using the insurance MCP server."
    ),
    version="1.0.0",
)
class PolicyAgent(A2AServer):
    """A2A agent that returns evidence-based policy and eligibility findings."""

    def __init__(
        self,
        mcp_server_url: str = MCP_SERVER_URL,
    ) -> None:
        host = os.getenv("POLICY_AGENT_HOST", "127.0.0.1")
        port = int(os.getenv("POLICY_AGENT_PORT", "5001"))
        self.url = os.getenv("POLICY_AGENT_URL", f"http://{host}:{port}")
        super().__init__(url=self.url)
        self._mcp_server_url = mcp_server_url

    @skill(
        name="Check policy eligibility facts",
        description=(
            "Check a customer's policy against an incident. Send a JSON object "
            "with customer_id, incident_date (YYYY-MM-DD), incident_type, and "
            "optional policy_id."
        ),
        tags=["insurance", "policy", "eligibility", "claims"],
        examples=[
            '{"customer_id":"CUST-001","policy_id":"POL-1001",'
            '"incident_date":"2026-02-14","incident_type":"COLLISION"}'
        ],
    )
    def assess_claim(self, claim_data: dict[str, Any]) -> dict[str, Any]:
        """Check customer, policy, incident, and claim-history facts through MCP."""
        return anyio.run(self._assess_claim_async, claim_data)

    async def _assess_claim_async(
        self,
        claim_data: dict[str, Any],
    ) -> dict[str, Any]:
        customer_id = claim_data.get("customer_id")
        incident_date = claim_data.get("incident_date")
        incident_type = claim_data.get("incident_type")
        policy_id = claim_data.get("policy_id")

        missing_information = [
            field
            for field, value in (
                ("customer_id", customer_id),
                ("incident_date", incident_date),
                ("incident_type", incident_type),
            )
            if not isinstance(value, str) or not value.strip()
        ]
        if missing_information:
            return {
                "status": "needs_information",
                "missing_information": missing_information,
            }

        customer_id = customer_id.strip()
        incident_date = incident_date.strip()
        incident_type = incident_type.strip()
        if policy_id is not None and (
            not isinstance(policy_id, str) or not policy_id.strip()
        ):
            return {
                "status": "needs_information",
                "missing_information": ["valid policy_id"],
            }

        try:
            parsed_date = date.fromisoformat(incident_date)
        except ValueError:
            return {
                "status": "needs_information",
                "missing_information": ["incident_date in YYYY-MM-DD format"],
            }
        if parsed_date.isoformat() != incident_date:
            return {
                "status": "needs_information",
                "missing_information": ["incident_date in YYYY-MM-DD format"],
            }

        selected_policy_id = policy_id.strip() if isinstance(policy_id, str) else None

        async with PolicyAgentMCPClient(self._mcp_server_url) as client:
            customer_response = _as_mapping(
                await client.find_customer(customer_id),
                "customer lookup",
            )
            if customer_response.get("found") is not True:
                return {
                    "status": "customer_not_found",
                    "customer_id": customer_id,
                    "missing_information": [],
                }
            customer = _as_mapping(customer_response.get("customer"), "customer")

            policies_response = _as_mapping(
                await client.get_customer_policies(customer_id),
                "customer policies",
            )
            if policies_response.get("customer_found") is not True:
                return {
                    "status": "customer_not_found",
                    "customer_id": customer_id,
                    "missing_information": [],
                }
            policies = _as_records(policies_response.get("policies"), "policies")

            if selected_policy_id is not None:
                selected = [
                    policy
                    for policy in policies
                    if policy.get("policy_id") == selected_policy_id
                ]
                if not selected:
                    return {
                        "status": "policy_not_found_for_customer",
                        "customer_id": customer_id,
                        "policy_id": selected_policy_id,
                        "candidate_policy_ids": [
                            policy.get("policy_id") for policy in policies
                        ],
                        "missing_information": [],
                    }
                selected_policy = selected[0]
            elif len(policies) == 1:
                selected_policy = policies[0]
                selected_policy_id = str(selected_policy["policy_id"])
            elif not policies:
                return {
                    "status": "no_policy_found",
                    "customer_id": customer_id,
                    "missing_information": [],
                }
            else:
                return {
                    "status": "needs_information",
                    "customer_id": customer_id,
                    "candidate_policy_ids": [
                        policy.get("policy_id") for policy in policies
                    ],
                    "missing_information": ["policy_id"],
                }

            policy_response = _as_mapping(
                await client.check_policy_for_incident(
                    selected_policy_id,
                    incident_date,
                    incident_type,
                ),
                "policy check",
            )
            if policy_response.get("found") is not True:
                return {
                    "status": "policy_not_found",
                    "customer_id": customer_id,
                    "policy_id": selected_policy_id,
                    "missing_information": [],
                }
            policy_facts = _as_mapping(policy_response.get("policy"), "policy details")

            history_response = _as_mapping(
                await client.get_customer_claim_history(customer_id),
                "claim history",
            )
            claim_history = _as_records(
                history_response.get("claims"),
                "claim history records",
            )

        date_matches = policy_facts.get("incident_within_policy_period") is True
        peril_matches = (
            policy_facts.get("incident_type_listed_as_covered_peril") is True
        )
        return {
            "status": (
                "facts_match_for_review"
                if date_matches and peril_matches
                else "manual_review_required"
            ),
            "customer": {
                "customer_id": customer.get("customer_id"),
                "full_name": customer.get("full_name"),
                "kyc_status": customer.get("kyc_status"),
            },
            "policy": {
                "policy_id": selected_policy_id,
                "policy_status": selected_policy.get("status"),
                "start_date": policy_facts.get("start_date"),
                "end_date": policy_facts.get("end_date"),
                "covered_perils": policy_facts.get("covered_perils"),
                "coverage_limit": policy_facts.get("coverage_limit"),
                "deductible": policy_facts.get("deductible"),
            },
            "incident": {
                "incident_date": incident_date,
                "incident_type": incident_type,
                "within_policy_period": date_matches,
                "type_listed_as_covered_peril": peril_matches,
            },
            "claim_history": [dict(claim) for claim in claim_history],
            "missing_information": [],
            "conflicts": [],
            "eligibility_decision": None,
            "decision_note": (
                "These are database facts and matching indicators, not a final "
                "coverage or eligibility decision."
            ),
        }

    def handle_task(self, task: Task) -> Task:
        """Accept a JSON claim context in A2A text and return JSON findings."""
        message = task.message or {}
        content = message.get("content", {})
        text = content.get("text", "") if isinstance(content, dict) else ""
        try:
            request_data = json.loads(text)
        except json.JSONDecodeError:
            result: dict[str, Any] = {
                "status": "needs_information",
                "missing_information": [
                    "A JSON object with customer_id, incident_date, and incident_type"
                ],
            }
        else:
            if not isinstance(request_data, dict):
                result = {
                    "status": "needs_information",
                    "missing_information": [
                        "A JSON object with customer_id, incident_date, and incident_type"
                    ],
                }
            else:
                result = self.assess_claim(request_data)

        task.artifacts = [
            {"parts": [{"type": "text", "text": json.dumps(result)}]}
        ]
        task.status = TaskStatus(state=TaskState.COMPLETED)
        return task


if __name__ == "__main__":
    policy_agent = PolicyAgent()
    run_server(
        policy_agent,
        host=os.getenv("POLICY_AGENT_HOST", "127.0.0.1"),
        port=int(os.getenv("POLICY_AGENT_PORT", "5001")),
    )
