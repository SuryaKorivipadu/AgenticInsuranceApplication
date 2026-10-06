import anyio
from mcp import Client


MCP_SERVER_URL = "http://127.0.0.1:8765/mcp"


async def _run_mcp_integration_checks() -> None:
    async with Client(MCP_SERVER_URL) as client:
        tools = await client.list_tools()
        tool_names = {tool.name for tool in tools.tools}
        assert {
            "health_check",
            "find_customer",
            "get_customer_policies",
            "check_policy_for_incident",
            "get_customer_claim_history",
        } <= tool_names

        health_result = await client.call_tool("health_check", {})
        assert health_result.is_error is False
        assert health_result.structured_content == {
            "status": "ok",
            "service": "insurance-claims-mcp",
        }

        # Verify customer lookup and its not-found response.
        customer_result = await client.call_tool(
            "find_customer", {"customer_id": "CUST-001"}
        )
        assert customer_result.is_error is False
        assert customer_result.structured_content["customer"]["full_name"] == "Avery Morgan"

        missing_customer = await client.call_tool(
            "find_customer", {"customer_id": "UNKNOWN"}
        )
        assert missing_customer.is_error is False
        assert missing_customer.structured_content == {
            "found": False,
            "customer": None,
        }

        # Verify customer-to-policy lookup and unknown-customer handling.
        policies_result = await client.call_tool(
            "get_customer_policies", {"customer_id": "CUST-001"}
        )
        assert policies_result.is_error is False
        assert [
            policy["policy_id"]
            for policy in policies_result.structured_content["policies"]
        ] == ["POL-1001"]

        missing_policies = await client.call_tool(
            "get_customer_policies", {"customer_id": "UNKNOWN"}
        )
        assert missing_policies.is_error is False
        assert missing_policies.structured_content == {
            "customer_found": False,
            "customer_id": "UNKNOWN",
            "policies": [],
        }

        # Verify that incident checks return facts, not a final eligibility decision.
        valid_period = await client.call_tool(
            "check_policy_for_incident",
            {
                "policy_id": "POL-1001",
                "incident_date": "2026-02-14",
                "incident_type": "COLLISION",
            },
        )
        assert valid_period.is_error is False
        assert valid_period.structured_content["policy"][
            "incident_within_policy_period"
        ] is True
        assert valid_period.structured_content["policy"][
            "incident_type_listed_as_covered_peril"
        ] is True

        outside_period = await client.call_tool(
            "check_policy_for_incident",
            {
                "policy_id": "POL-1001",
                "incident_date": "2025-12-31",
                "incident_type": "COLLISION",
            },
        )
        assert outside_period.is_error is False
        assert outside_period.structured_content["policy"][
            "incident_within_policy_period"
        ] is False

        missing_policy = await client.call_tool(
            "check_policy_for_incident",
            {
                "policy_id": "UNKNOWN",
                "incident_date": "2026-02-14",
                "incident_type": "COLLISION",
            },
        )
        assert missing_policy.is_error is False
        assert missing_policy.structured_content == {
            "found": False,
            "policy_id": "UNKNOWN",
        }

        invalid_date = await client.call_tool(
            "check_policy_for_incident",
            {
                "policy_id": "POL-1001",
                "incident_date": "not-a-date",
                "incident_type": "COLLISION",
            },
        )
        assert invalid_date.is_error is True

        # Verify history results, limits, and unknown-customer handling.
        history_result = await client.call_tool(
            "get_customer_claim_history",
            {"customer_id": "CUST-001"},
        )
        assert history_result.is_error is False
        assert len(history_result.structured_content["claims"]) == 3

        limited_history = await client.call_tool(
            "get_customer_claim_history",
            {"customer_id": "CUST-001", "limit": 1},
        )
        assert limited_history.is_error is False
        assert len(limited_history.structured_content["claims"]) == 1

        invalid_limit = await client.call_tool(
            "get_customer_claim_history",
            {"customer_id": "CUST-001", "limit": 101},
        )
        assert invalid_limit.is_error is True

        missing_history = await client.call_tool(
            "get_customer_claim_history",
            {"customer_id": "UNKNOWN"},
        )
        assert missing_history.is_error is False
        assert missing_history.structured_content == {
            "customer_found": False,
            "customer_id": "UNKNOWN",
            "claims": [],
        }


def test_mcp_server_tools() -> None:
    """Integration-test the tools on a running local MCP server."""
    anyio.run(_run_mcp_integration_checks)


if __name__ == "__main__":
    anyio.run(_run_mcp_integration_checks)
    print("All MCP server integration checks passed.")
