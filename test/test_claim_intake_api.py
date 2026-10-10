from fastapi.testclient import TestClient

from app.agents.damage_agent import EVIDENCE_ROOT
from app.main import app


client = TestClient(app)


def test_claim_intake_api_requests_missing_information() -> None:
    response = client.post(
        "/api/claims/intake",
        json={"claim_text": "My car was damaged in a collision."},
    )

    assert response.status_code == 200
    report = response.json()
    assert report["status"] == "needs_information"
    assert report["policy_review"]["status"] == "needs_information"
    assert report["damage_review"]["status"] == "needs_information"
    requested_fields = {item["field"] for item in report["missing_information"]}
    assert {"customer_id", "incident_date", "incident_type", "claim_id"} <= (
        requested_fields
    )
    assert report["next_steps"]
    assert report["decision"] is None


def test_claim_intake_api_calls_policy_agent_and_requests_evidence() -> None:
    response = client.post(
        "/api/claims/intake",
        json={
            "claim": {
                "claim_id": "CLM-2001",
                "customer_id": "CUST-001",
                "policy_id": "POL-1001",
                "incident_date": "2026-02-14",
                "incident_type": "COLLISION",
            }
        },
    )

    assert response.status_code == 200
    report = response.json()
    assert report["policy_review"]["status"] == "facts_match_for_review"
    assert report["damage_review"]["status"] == "needs_information"
    assert report["damage_review"]["missing_information"] == [
        "evidence_files or additional_context"
    ]
    assert report["status"] == "needs_information"


def test_claim_intake_api_accepts_frontend_file_uploads() -> None:
    temporary_directories_before = set(EVIDENCE_ROOT.glob("claim-intake-*"))
    response = client.post(
        "/api/claims/intake",
        data={"claim": "{}", "claim_text": "Front impact collision."},
        files=[
            ("evidence_files", ("damage.jpg", b"sample image bytes", "image/jpeg"))
        ],
    )

    assert response.status_code == 200
    report = response.json()
    assert report["status"] == "needs_information"
    assert report["damage_review"]["missing_information"] == ["claim_id"]
    assert set(EVIDENCE_ROOT.glob("claim-intake-*")) == temporary_directories_before


def test_claim_intake_api_rejects_unsupported_upload_type() -> None:
    response = client.post(
        "/api/claims/intake",
        data={"claim": "{}"},
        files=[
            (
                "evidence_files",
                ("script.exe", b"not evidence", "application/octet-stream"),
            )
        ],
    )

    assert response.status_code == 422
    assert "Unsupported evidence file type" in response.json()["detail"]


if __name__ == "__main__":
    test_claim_intake_api_requests_missing_information()
    test_claim_intake_api_calls_policy_agent_and_requests_evidence()
    test_claim_intake_api_accepts_frontend_file_uploads()
    test_claim_intake_api_rejects_unsupported_upload_type()
    print("Claim Intake FastAPI integration checks passed.")
