import anyio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.mcp.client import (  # noqa: E402
    DamageAssessmentMCPClient,
    MCPClientError,
    PolicyAgentMCPClient,
)


async def _test_policy_agent_mcp_client() -> None:
    async with PolicyAgentMCPClient() as client:
        customer = await client.find_customer("CUST-001")
        assert customer["found"] is True
        assert customer["customer"]["full_name"] == "Avery Morgan"

        policies = await client.get_customer_policies("CUST-001")
        assert policies["customer_found"] is True
        assert any(
            policy["policy_id"] == "POL-1001"
            for policy in policies["policies"]
        )

        policy_check = await client.check_policy_for_incident(
            "POL-1001",
            "2026-02-14",
            "COLLISION",
        )
        assert policy_check["found"] is True
        assert policy_check["policy"]["incident_within_policy_period"] is True
        assert policy_check["policy"]["incident_type_listed_as_covered_peril"] is True

        history = await client.get_customer_claim_history("CUST-001")
        assert history["customer_found"] is True
        assert len(history["claims"]) > 0

        try:
            await client._call_tool("get_claim_details", {"claim_id": "CLM-2001"})
        except MCPClientError as error:
            assert "not available" in str(error)
        else:
            raise AssertionError("Policy client allowed a damage-only tool")

        try:
            await client.check_policy_for_incident(
                "POL-1001",
                "not-a-date",
                "COLLISION",
            )
        except MCPClientError as error:
            assert "check_policy_for_incident" in str(error)
        else:
            raise AssertionError("Invalid date did not surface the server tool error")


async def _test_damage_assessment_mcp_client() -> None:
    async with DamageAssessmentMCPClient() as client:
        claim = await client.get_claim_details("CLM-2001")
        assert claim["found"] is True
        assert claim["claim"]["incident_type"] == "COLLISION"
        assert claim["claim"]["vehicle_registration"] == "IL8K4M2"

        estimates = await client.get_repair_estimates("CLM-2001")
        assert estimates["claim_found"] is True
        assert any(
            estimate["estimate_id"] == "EST-3001"
            for estimate in estimates["estimates"]
        )

        try:
            await client._call_tool("find_customer", {"customer_id": "CUST-001"})
        except MCPClientError as error:
            assert "not available" in str(error)
        else:
            raise AssertionError("Damage client allowed a policy-only tool")


def test_policy_agent_mcp_client() -> None:
    """Exercise Policy agent wrappers against the running MCP server and database."""
    anyio.run(_test_policy_agent_mcp_client)


def test_damage_assessment_mcp_client() -> None:
    """Exercise Damage Assessment wrappers against the running MCP server and database."""
    anyio.run(_test_damage_assessment_mcp_client)


if __name__ == "__main__":
    anyio.run(_test_policy_agent_mcp_client)
    anyio.run(_test_damage_assessment_mcp_client)
    print("All real MCP client integration checks passed.")
