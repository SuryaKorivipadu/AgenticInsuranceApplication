import os
from types import TracebackType
from typing import Self

from mcp import Client


MCP_SERVER_URL = os.getenv(
    "INSURANCE_MCP_SERVER_URL",
    "http://127.0.0.1:8765/mcp",
)


class MCPClientError(RuntimeError):
    """Raised when an MCP tool fails or returns an unexpected response."""


class _AgentMCPClient:
    """Base client that keeps an MCP connection open for one agent workflow."""

    _allowed_tools: frozenset[str] = frozenset()

    def __init__(self, server_url: str = MCP_SERVER_URL) -> None:
        self._server_url = server_url
        self._client: Client | None = None

    async def __aenter__(self) -> Self:
        if self._client is not None:
            raise RuntimeError("MCP client is already connected")

        client = Client(self._server_url)
        await client.__aenter__()
        self._client = client
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        client = self._client
        self._client = None
        if client is not None:
            await client.__aexit__(exc_type, exc_value, traceback)

    async def _call_tool(
        self, name: str, arguments: dict[str, object]
    ) -> dict[str, object]:
        if name not in self._allowed_tools:
            raise MCPClientError(f"Tool {name!r} is not available to this agent client")
        if self._client is None:
            raise RuntimeError("MCP client is not connected; use it inside 'async with'")

        result = await self._client.call_tool(name, arguments)
        if result.is_error:
            raise MCPClientError(f"MCP tool {name!r} failed: {result.content}")
        if result.structured_content is None:
            raise MCPClientError(
                f"MCP tool {name!r} returned no structured content"
            )
        return result.structured_content


class PolicyAgentMCPClient(_AgentMCPClient):
    """MCP client exposing database tools needed by the Policy agent."""

    _allowed_tools = frozenset(
        {
            "find_customer",
            "get_customer_policies",
            "check_policy_for_incident",
            "get_customer_claim_history",
        }
    )

    async def find_customer(self, customer_id: str) -> dict[str, object]:
        """Look up a customer by exact customer ID."""
        return await self._call_tool(
            "find_customer",
            {"customer_id": customer_id},
        )

    async def get_customer_policies(self, customer_id: str) -> dict[str, object]:
        """Return policies associated with a customer ID."""
        return await self._call_tool(
            "get_customer_policies",
            {"customer_id": customer_id},
        )

    async def check_policy_for_incident(
        self,
        policy_id: str,
        incident_date: str,
        incident_type: str,
    ) -> dict[str, object]:
        """Return policy period and peril-match facts for an incident."""
        return await self._call_tool(
            "check_policy_for_incident",
            {
                "policy_id": policy_id,
                "incident_date": incident_date,
                "incident_type": incident_type,
            },
        )

    async def get_customer_claim_history(
        self,
        customer_id: str,
        limit: int = 20,
    ) -> dict[str, object]:
        """Return recent claims associated with a customer ID."""
        return await self._call_tool(
            "get_customer_claim_history",
            {"customer_id": customer_id, "limit": limit},
        )


class DamageAssessmentMCPClient(_AgentMCPClient):
    """MCP client exposing claim and estimate lookups for damage assessment."""

    _allowed_tools = frozenset(
        {
            "get_claim_details",
            "get_repair_estimates",
        }
    )

    async def get_claim_details(self, claim_id: str) -> dict[str, object]:
        """Return claim incident details and linked vehicle information."""
        return await self._call_tool(
            "get_claim_details",
            {"claim_id": claim_id},
        )

    async def get_repair_estimates(self, claim_id: str) -> dict[str, object]:
        """Return repair estimates associated with a claim."""
        return await self._call_tool(
            "get_repair_estimates",
            {"claim_id": claim_id},
        )
