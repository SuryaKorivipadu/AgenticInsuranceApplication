# AgenticInsuranceApplication

## Claim Intake API

The frontend submits claims to the FastAPI backend at
`POST http://127.0.0.1:8000/api/claims/intake`. The handler runs the Claim
Intake LangGraph workflow, which calls the existing Policy and Damage A2A
agents in parallel and returns a combined report with missing information and
suggested next steps. Claim Intake is a backend API, not a separate A2A server;
it does not make a coverage, liability, or fraud decision.

Start the MCP server, Ollama, Policy Agent, Damage Agent, and FastAPI backend in
separate terminals from the repository root. The downstream agents require the
MCP server and Ollama:

```powershell
.\.venv\Scripts\python.exe -m app.mcp.server
```

```powershell
.\.venv\Scripts\python.exe -m app.agents.policy_agent
```

```powershell
.\.venv\Scripts\python.exe -m app.agents.damage_agent
```

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

For JSON clients, send a `claim` object, optional `claim_text`, and optional
existing `evidence_files` paths accessible to the Damage Agent:

```json
{
  "claim": {
    "claim_id": "CLM-2001",
    "customer_id": "CUST-001",
    "policy_id": "POL-1001",
    "incident_date": "2026-02-14",
    "incident_type": "COLLISION"
  },
  "claim_text": "Front impact at a junction; front bumper and left headlamp damaged.",
  "evidence_files": [
    "01_GOOD_COMPLETE_CLAIM/INCIDENT/accident_report.pdf",
    "01_GOOD_COMPLETE_CLAIM/DAMAGE_PHOTOS/front_damage.jpg"
  ]
}
```

For browser uploads, send `multipart/form-data` with a JSON string in the
`claim` field, optional `claim_text`, and one or more `evidence_files` file
fields. The API stages uploads only for the duration of the workflow and limits
file types, file count, and file size. It also accepts `text/plain` and returns
questions for missing structured fields. Set `POLICY_AGENT_URL`,
`DAMAGE_AGENT_URL`, or `CLAIM_INTAKE_A2A_TIMEOUT_SECONDS` to override defaults.

Run the Claim Intake API checks after starting the MCP server and Policy Agent.
The Damage Agent and Ollama are not needed for these checks:

```powershell
$env:PYTHONPATH = (Get-Location).Path
.\.venv\Scripts\python.exe test\test_claim_intake_api.py
```

## Damage Assessment Agent

The Damage Assessment Agent listens on `http://127.0.0.1:5002`. From the
repository root, start the MCP server and Damage Assessment Agent in separate
terminals:

```powershell
.\.venv\Scripts\python.exe -m app.mcp.server
```

```powershell
.\.venv\Scripts\python.exe -m app.agents.damage_agent
```

The agent uses the local Ollama model configured in `app/utils/call_ai.py`.
Send an A2A JSON request with a `claim_id`, optional `additional_context`, and
optional `evidence_files` paths relative to `sample_claims`. Supported evidence
is text, PDF, DOCX, JPEG, and PNG; files must be stored under the project's
`sample_claims` directory on the agent host. The agent returns evidence-review
findings and estimate-total checks, not a coverage or fraud determination.

## Streamlit Claim Intake UI

Install the optional UI dependency after installing the project requirements:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-ui.txt
```

Start the FastAPI backend and its MCP, Policy, and Damage services as described
above. Then launch the Streamlit frontend from the repository root:

```powershell
.\.venv\Scripts\python.exe -m streamlit run streamlit_app.py
```

Open the local URL shown by Streamlit (normally `http://localhost:8501`). The
UI accepts claim/customer/policy identifiers, incident date and type, an
incident description, and up to 10 evidence files (TXT, Markdown, PDF, DOCX,
JPG, JPEG, or PNG; 15 MB per file). Unknown fields may be left blank so the
intake workflow can request them. Set `CLAIM_INTAKE_API_URL` to override the
default backend URL `http://127.0.0.1:8000/api/claims/intake`.

The results show missing-information prompts, Policy and Damage review
findings, and suggested next steps. Findings are not an approval, denial, or
coverage decision.

To run its real A2A integration check, start the MCP server, Ollama, and the
Damage Assessment Agent, then execute:

```powershell
.\.venv\Scripts\python.exe test\test_damage_agent_a2a.py
```
