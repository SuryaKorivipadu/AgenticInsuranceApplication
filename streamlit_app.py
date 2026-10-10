import json
import os
from datetime import datetime
from typing import Any

import requests
import streamlit as st


API_URL = os.getenv(
    "CLAIM_INTAKE_API_URL",
    "http://127.0.0.1:8000/api/claims/intake",
)
MAX_EVIDENCE_FILES = 10
MAX_EVIDENCE_SIZE = 15 * 1024 * 1024
ALLOWED_EVIDENCE_TYPES = ["txt", "md", "pdf", "docx", "jpg", "jpeg", "png"]
REQUEST_TIMEOUT = (10, 240)

st.set_page_config(
    page_title="Claim Intake | InsureFlow",
    page_icon="🛡️",
    layout="wide",
)

st.markdown(
    """
    <style>
    :root {
        color-scheme: light;
        --app-bg: #f3f6fb;
        --surface: #ffffff;
        --text: #172033;
        --muted: #526078;
        --border: #d5deea;
        --primary: #155eef;
    }
    html, body, [data-testid="stAppViewContainer"], .stApp {
        background: var(--app-bg) !important;
        color: var(--text) !important;
    }
    [data-testid="stHeader"] { background: var(--app-bg) !important; }
    .block-container { max-width: 1120px; padding-top: 2rem; }
    h1, h2, h3, h4, h5, h6,
    [data-testid="stMarkdownContainer"] h1,
    [data-testid="stMarkdownContainer"] h2,
    [data-testid="stMarkdownContainer"] h3 {
        color: #102a43 !important;
    }
    p, li, label, small,
    [data-testid="stWidgetLabel"],
    [data-testid="stWidgetLabel"] p,
    [data-testid="stCaptionContainer"],
    [data-testid="stTooltipIcon"] {
        color: var(--text) !important;
    }
    [data-testid="stCaptionContainer"] {
        color: var(--muted) !important;
    }
    [data-testid="stForm"] {
        background: var(--surface) !important;
        border: 1px solid var(--border);
        border-radius: 14px;
        padding: 1.5rem;
    }
    [data-testid="stMetric"] {
        background: var(--surface) !important;
        border: 1px solid var(--border);
        border-radius: 12px;
        padding: 1rem;
    }
    [data-baseweb="input"],
    [data-baseweb="textarea"],
    [data-baseweb="select"] > div {
        background: #ffffff !important;
        border-color: #aab8ca !important;
    }
    [data-baseweb="input"] input,
    [data-baseweb="textarea"] textarea {
        background: #ffffff !important;
        color: var(--text) !important;
        caret-color: var(--text) !important;
        cursor: text !important;
        pointer-events: auto !important;
        user-select: text !important;
    }
    [data-testid="stTextArea"] textarea {
        background-color: #ffffff !important;
        color: #172033 !important;
        -webkit-text-fill-color: #172033 !important;
        caret-color: #172033 !important;
        opacity: 1 !important;
    }
    [data-baseweb="select"],
    [data-baseweb="select"] * {
        color: var(--text) !important;
        cursor: pointer !important;
        pointer-events: auto !important;
    }
    [data-baseweb="input"]:focus-within,
    [data-baseweb="textarea"]:focus-within,
    [data-baseweb="select"]:focus-within {
        outline: 2px solid #155eef !important;
        outline-offset: 1px;
    }
    input::placeholder,
    textarea::placeholder,
    [data-testid="stTextArea"] textarea::placeholder {
        color: #66758b !important;
        -webkit-text-fill-color: #66758b !important;
        opacity: 1 !important;
    }
    [data-testid="stFileUploader"] section {
        background: #ffffff !important;
        border-color: #aab8ca !important;
    }
    [data-testid="stFileUploader"] small,
    [data-testid="stFileUploader"] span {
        color: var(--muted) !important;
    }
    [data-testid="stExpander"] {
        background: #ffffff !important;
        border: 1px solid var(--border) !important;
        border-radius: 10px;
    }
    [data-testid="stExpander"] summary,
    [data-testid="stExpander"] summary p {
        color: var(--text) !important;
    }
    [data-testid="stFormSubmitButton"] button,
    [data-testid="stButton"] button[kind="primary"] {
        background: var(--primary) !important;
        border-color: var(--primary) !important;
        color: #ffffff !important;
    }
    [data-testid="stFormSubmitButton"] button p,
    [data-testid="stButton"] button[kind="primary"] p {
        color: #ffffff !important;
    }
    [data-testid="stAlert"] p,
    [data-testid="stAlert"] li {
        color: #172033 !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def _display_review(title: str, review: object) -> None:
    with st.expander(title, expanded=True):
        if isinstance(review, dict):
            st.write(f"**Status:** {review.get('status', 'No status returned')}")
            details = {
                key: value
                for key, value in review.items()
                if key != "status" and value not in (None, "", [], {})
            }
            if details:
                st.json(details, expanded=True)
            else:
                st.info("No additional findings were returned.")
        else:
            st.info("No review result was returned.")


def _display_report(report: dict[str, Any]) -> None:
    st.divider()
    st.subheader("Claim review")

    status = report.get("status")
    if status == "needs_information":
        st.warning("More information is needed before the claim is ready for review.")
    elif status == "ready_for_review":
        st.success("The agent reviews are ready for a human claims reviewer.")
    else:
        st.info(f"Workflow status: {status or 'unknown'}")

    missing_information = report.get("missing_information", [])
    if isinstance(missing_information, list) and missing_information:
        st.markdown("#### Information to provide")
        for item in missing_information:
            if isinstance(item, dict):
                field = item.get("field", "Information")
                question = item.get("question", "Please provide this information.")
                st.markdown(f"- **{field}:** {question}")
            else:
                st.markdown(f"- {item}")

    policy_review = report.get("policy_review")
    damage_review = report.get("damage_review")
    review_columns = st.columns(2)
    with review_columns[0]:
        _display_review("Policy review", policy_review)
    with review_columns[1]:
        _display_review("Damage and evidence review", damage_review)

    next_steps = report.get("next_steps", [])
    if isinstance(next_steps, list) and next_steps:
        st.markdown("#### Suggested next steps")
        for step in next_steps:
            st.markdown(f"- {step}")

    decision_note = report.get("decision_note")
    if isinstance(decision_note, str) and decision_note:
        st.info(decision_note)
    st.caption(
        "Agent findings support review only. They do not approve or deny a claim "
        "or determine coverage, liability, or fraud."
    )


st.title("🛡️ Claim Intake")
st.write(
    "Share the incident details and supporting evidence. The Policy and Damage "
    "agents will prepare findings for a human claims reviewer."
)

with st.form("claim_intake_form", clear_on_submit=False):
    st.markdown("### Claim and policy details")
    claim_id_column, customer_column = st.columns(2)
    claim_id = claim_id_column.text_input(
        "Claim ID",
        placeholder="e.g. CLM-2001",
        help="Leave blank if it has not been assigned; the intake agent will request it.",
    )
    customer_id = customer_column.text_input(
        "Customer ID",
        placeholder="e.g. CUST-001",
    )

    policy_column, incident_date_column = st.columns(2)
    policy_id = policy_column.text_input(
        "Policy ID",
        placeholder="e.g. POL-1001",
        help="Optional if you do not have the policy ID.",
    )
    incident_date = incident_date_column.text_input(
        "Incident date",
        placeholder="YYYY-MM-DD",
        help="Use YYYY-MM-DD. Leave blank if unknown.",
    )

    incident_type = st.selectbox(
        "Incident type",
        ["", "COLLISION", "THEFT", "FIRE", "WEATHER", "OTHER"],
        format_func=lambda value: value.replace("_", " ").title()
        if value
        else "Select or leave blank if unknown",
    )
    incident_description = st.text_area(
        "What happened?",
        placeholder=(
            "Describe where and how the incident happened and what was damaged."
        ),
        height=120,
    )

    st.markdown("### Supporting evidence")
    evidence_files = st.file_uploader(
        "Upload photos, reports, or repair estimates",
        type=ALLOWED_EVIDENCE_TYPES,
        accept_multiple_files=True,
        max_upload_size=15,
        help=(
            "Accepted: TXT, Markdown, PDF, DOCX, JPG, JPEG, and PNG. "
            "Maximum 10 files, 15 MB each."
        ),
    )

    submitted = st.form_submit_button(
        "Submit claim for review",
        type="primary",
        use_container_width=True,
    )

if submitted:
    st.session_state.pop("claim_intake_report", None)

    if incident_date.strip():
        try:
            datetime.strptime(incident_date.strip(), "%Y-%m-%d")
        except ValueError:
            st.error("Enter the incident date in YYYY-MM-DD format.")
            st.stop()

    if len(evidence_files) > MAX_EVIDENCE_FILES:
        st.error(f"Upload no more than {MAX_EVIDENCE_FILES} evidence files.")
        st.stop()

    oversized_files = [
        uploaded_file.name
        for uploaded_file in evidence_files
        if uploaded_file.size > MAX_EVIDENCE_SIZE
    ]
    if oversized_files:
        st.error(
            "Each evidence file must be 15 MB or smaller. Too large: "
            + ", ".join(oversized_files)
        )
        st.stop()

    claim = {
        "claim_id": claim_id.strip(),
        "customer_id": customer_id.strip(),
        "policy_id": policy_id.strip(),
        "incident_date": incident_date.strip(),
        "incident_type": incident_type,
        "incident_description": incident_description.strip(),
    }
    files = [
        (
            "evidence_files",
            (
                uploaded_file.name,
                uploaded_file.getvalue(),
                uploaded_file.type or "application/octet-stream",
            ),
        )
        for uploaded_file in evidence_files
    ]
    with st.spinner("Submitting claim and waiting for agent reviews..."):
        try:
            if files:
                response = requests.post(
                    API_URL,
                    data={
                        "claim": json.dumps(claim),
                        "claim_text": incident_description.strip(),
                    },
                    files=files,
                    timeout=REQUEST_TIMEOUT,
                )
            else:
                response = requests.post(
                    API_URL,
                    json={
                        "claim": claim,
                        "claim_text": incident_description.strip(),
                    },
                    timeout=REQUEST_TIMEOUT,
                )
        except requests.Timeout:
            st.error(
                "The claim review timed out. The agents may still be processing; "
                "check the backend before submitting the same claim again."
            )
            st.stop()
        except requests.ConnectionError:
            st.error(
                f"Could not connect to the Claim Intake API at {API_URL}. "
                "Confirm the FastAPI backend is running."
            )
            st.stop()
        except requests.RequestException as error:
            st.error(f"Could not submit the claim: {error}")
            st.stop()

    if not response.ok:
        try:
            error_body = response.json()
        except requests.exceptions.JSONDecodeError:
            error_body = response.text
        detail = (
            error_body.get("detail", error_body)
            if isinstance(error_body, dict)
            else error_body
        )
        st.error(f"Claim Intake API returned HTTP {response.status_code}: {detail}")
    else:
        try:
            report = response.json()
        except requests.exceptions.JSONDecodeError:
            st.error("The Claim Intake API returned a response that was not JSON.")
        else:
            if not isinstance(report, dict):
                st.error("The Claim Intake API returned an unexpected response.")
            else:
                st.session_state["claim_intake_report"] = report

report = st.session_state.get("claim_intake_report")
if isinstance(report, dict):
    _display_report(report)
