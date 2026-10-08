from datetime import date

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from app.utils.sqlite_db import fetch_all, fetch_one


mcp = MCPServer(
    name="Insurance Claims MCP Server",
)


@mcp.tool()
def health_check() -> dict[str, str]:
    """Confirm the insurance claims MCP server is ready."""
    return {"status": "ok", "service": "insurance-claims-mcp"}


@mcp.tool()
def find_customer(customer_id: str) -> dict[str, object]:
    """Look up a customer by exact customer ID."""
    row = fetch_one(
        """
        SELECT customer_id, full_name, date_of_birth, email, phone, address, kyc_status
        FROM customers
        WHERE customer_id = ?
        """,
        (customer_id,),
    )
    return {"found": row is not None, "customer": dict(row) if row else None}


@mcp.tool()
def get_customer_policies(customer_id: str) -> dict[str, object]:
    """Return all policies for a customer ID and indicate whether the customer exists."""
    customer = fetch_one(
        "SELECT customer_id FROM customers WHERE customer_id = ?",
        (customer_id,),
    )
    if customer is None:
        return {"customer_found": False, "customer_id": customer_id, "policies": []}

    policies = fetch_all(
        """
        SELECT policy_id, customer_id, policy_type, vehicle_registration,
               vehicle_description, start_date, end_date, status,
               coverage_limit, deductible, covered_perils
        FROM policies
        WHERE customer_id = ?
        ORDER BY start_date DESC, policy_id
        """,
        (customer_id,),
    )
    return {
        "customer_found": True,
        "customer_id": customer_id,
        "policies": [dict(row) for row in policies],
    }


@mcp.tool()
def check_policy_for_incident(
    policy_id: str,
    incident_date: str,
    incident_type: str,
) -> dict[str, object]:
    """Return policy facts and date/peril matches; this is not a final eligibility decision."""
    try:
        incident_day = date.fromisoformat(incident_date)
    except ValueError as error:
        raise ToolError("incident_date must be a valid date in YYYY-MM-DD format") from error
    if incident_day.isoformat() != incident_date:
        raise ToolError("incident_date must use YYYY-MM-DD format")

    row = fetch_one(
        """
        SELECT policy_id, customer_id, policy_type, start_date, end_date,
               status, coverage_limit, deductible, covered_perils
        FROM policies
        WHERE policy_id = ?
        """,
        (policy_id,),
    )
    if row is None:
        return {"found": False, "policy_id": policy_id}

    policy = dict(row)
    covered_perils = [
        peril.strip()
        for peril in str(policy["covered_perils"]).split(";")
        if peril.strip()
    ]
    policy["covered_perils"] = covered_perils
    policy["incident_date"] = incident_date
    policy["incident_within_policy_period"] = (
        str(policy["start_date"]) <= incident_date <= str(policy["end_date"])
    )
    policy["incident_type"] = incident_type
    policy["incident_type_listed_as_covered_peril"] = any(
        incident_type.strip().casefold() == peril.casefold()
        for peril in covered_perils
    )
    return {"found": True, "policy": policy}


@mcp.tool()
def get_customer_claim_history(
    customer_id: str,
    limit: int = 20,
) -> dict[str, object]:
    """Return recent claim records for a customer; limit must be between 1 and 100."""
    if not 1 <= limit <= 100:
        raise ToolError("limit must be between 1 and 100")

    customer = fetch_one(
        "SELECT customer_id FROM customers WHERE customer_id = ?",
        (customer_id,),
    )
    if customer is None:
        return {"customer_found": False, "customer_id": customer_id, "claims": []}

    claims = fetch_all(
        """
        SELECT claim_id, customer_id, policy_id, incident_date, incident_type,
               incident_description, claimed_amount, status
        FROM claims_history
        WHERE customer_id = ?
        ORDER BY incident_date DESC, claim_id
        LIMIT ?
        """,
        (customer_id, limit),
    )
    return {
        "customer_found": True,
        "customer_id": customer_id,
        "claims": [dict(row) for row in claims],
    }


@mcp.tool()
def get_claim_details(claim_id: str) -> dict[str, object]:
    """Return claim incident details with its linked vehicle information."""
    row = fetch_one(
        """
        SELECT c.claim_id, c.customer_id, c.policy_id, c.incident_date,
               c.incident_type, c.incident_description, c.claimed_amount,
               c.status, p.vehicle_registration, p.vehicle_description
        FROM claims_history AS c
        JOIN policies AS p ON p.policy_id = c.policy_id
        WHERE c.claim_id = ?
        """,
        (claim_id,),
    )
    return {"found": row is not None, "claim": dict(row) if row else None}


@mcp.tool()
def get_repair_estimates(claim_id: str) -> dict[str, object]:
    """Return repair estimates for a known claim ID."""
    claim = fetch_one(
        "SELECT claim_id FROM claims_history WHERE claim_id = ?",
        (claim_id,),
    )
    if claim is None:
        return {"claim_found": False, "claim_id": claim_id, "estimates": []}

    estimates = fetch_all(
        """
        SELECT estimate_id, claim_id, workshop, estimate_date,
               total_amount, currency, line_items
        FROM repair_estimates
        WHERE claim_id = ?
        ORDER BY estimate_date DESC, estimate_id
        """,
        (claim_id,),
    )
    return {
        "claim_found": True,
        "claim_id": claim_id,
        "estimates": [dict(row) for row in estimates],
    }


if __name__ == "__main__":
    mcp.run(
        transport="streamable-http",
        host="127.0.0.1",
        port=8765,
    )
