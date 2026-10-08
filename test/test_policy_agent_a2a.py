import json
import os

from python_a2a import A2AClient


POLICY_AGENT_URL = os.getenv(
    "POLICY_AGENT_URL",
    "http://127.0.0.1:5001",
)


def test_policy_agent_a2a_request() -> None:
    """Send an A2A request to the running Policy Agent and validate its findings."""
    client = A2AClient(POLICY_AGENT_URL)
    response = client.ask(
        json.dumps(
            {
                "customer_id": "CUST-001",
                "policy_id": "POL-1001",
                "incident_date": "2026-02-14",
                "incident_type": "COLLISION",
            }
        )
    )
    result = json.loads(response)

    assert result["status"] == "facts_match_for_review"
    assert result["customer"]["full_name"] == "Avery Morgan"
    assert result["policy"]["policy_id"] == "POL-1001"
    assert result["incident"]["within_policy_period"] is True
    assert result["incident"]["type_listed_as_covered_peril"] is True
    assert result["eligibility_decision"] is None


if __name__ == "__main__":
    test_policy_agent_a2a_request()
    print("Policy Agent A2A integration check passed.")
