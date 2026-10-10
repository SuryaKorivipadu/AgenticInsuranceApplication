import json
import logging
import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from starlette.datastructures import FormData, UploadFile as StarletteUploadFile

from app.agents.claim_intake_agent import run_claim_intake
from app.agents.damage_agent import (
    EVIDENCE_ROOT,
    IMAGE_EXTENSIONS,
    MAX_EVIDENCE_FILES,
    MAX_EVIDENCE_SIZE,
    TEXT_EXTENSIONS,
)


logger = logging.getLogger(__name__)
router = APIRouter()
_CLAIM_FIELDS = (
    "claim_id",
    "customer_id",
    "policy_id",
    "incident_date",
    "incident_type",
    "incident_description",
)
_ALLOWED_EVIDENCE_EXTENSIONS = TEXT_EXTENSIONS | IMAGE_EXTENSIONS


def _parse_claim(value: object) -> dict[str, Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as error:
            raise ValueError("claim must contain valid JSON") from error
    if not isinstance(value, dict):
        raise ValueError("claim must be a JSON object")
    return value


def _parse_json_value(value: str, field: str) -> object:
    try:
        return json.loads(value)
    except json.JSONDecodeError as error:
        raise ValueError(f"{field} must contain valid JSON") from error


async def _parse_request(
    request: Request,
) -> tuple[dict[str, Any], list[StarletteUploadFile]]:
    content_type = request.headers.get("content-type", "").casefold()
    if "application/json" in content_type:
        payload = await request.json()
        if not isinstance(payload, dict):
            raise ValueError("Request body must be a JSON object")
        return payload, []

    if content_type.startswith("text/plain"):
        return {"claim_text": (await request.body()).decode("utf-8")}, []

    if content_type.startswith("multipart/form-data"):
        form: FormData = await request.form()
        raw_claim = form.get("claim")
        claim = (
            _parse_claim(raw_claim)
            if raw_claim is not None
            else {
                field: form.get(field)
                for field in _CLAIM_FIELDS
                if isinstance(form.get(field), str)
            }
        )
        payload: dict[str, Any] = {"claim": claim}

        claim_text = form.get("claim_text", form.get("additional_context", ""))
        if not isinstance(claim_text, str):
            raise ValueError("claim_text must be a string")
        if claim_text:
            payload["claim_text"] = claim_text

        raw_file_paths = form.get("evidence_file_paths")
        if raw_file_paths is not None:
            if not isinstance(raw_file_paths, str):
                raise ValueError("evidence_file_paths must be a JSON array")
            file_paths = _parse_json_value(raw_file_paths, "evidence_file_paths")
            if not isinstance(file_paths, list) or not all(
                isinstance(path, str) for path in file_paths
            ):
                raise ValueError("evidence_file_paths must be a JSON array of strings")
            payload["evidence_files"] = file_paths

        uploads = form.getlist("evidence_files")
        if not all(isinstance(item, StarletteUploadFile) for item in uploads):
            raise ValueError("evidence_files form fields must be uploaded files")
        return payload, [
            item for item in uploads if isinstance(item, StarletteUploadFile)
        ]

    raise HTTPException(
        status_code=415,
        detail="Use application/json, multipart/form-data, or text/plain.",
    )


async def _stage_uploads(
    uploads: list[StarletteUploadFile],
) -> tuple[tempfile.TemporaryDirectory[str], list[str]]:
    if len(uploads) > MAX_EVIDENCE_FILES:
        raise ValueError(f"At most {MAX_EVIDENCE_FILES} evidence files are allowed")
    EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True)
    temporary_directory = tempfile.TemporaryDirectory(
        prefix="claim-intake-",
        dir=EVIDENCE_ROOT,
    )
    directory = Path(temporary_directory.name)
    staged_paths: list[str] = []
    try:
        for index, upload in enumerate(uploads):
            filename = (upload.filename or "").replace("\\", "/").rsplit("/", 1)[-1]
            suffix = Path(filename).suffix.casefold()
            if suffix not in _ALLOWED_EVIDENCE_EXTENSIONS:
                raise ValueError(f"Unsupported evidence file type: {suffix or '(none)'}")

            destination = directory / f"{index:02d}{suffix}"
            size = 0
            with destination.open("wb") as output:
                while chunk := await upload.read(64 * 1024):
                    size += len(chunk)
                    if size > MAX_EVIDENCE_SIZE:
                        raise ValueError(
                            f"{filename} exceeds the {MAX_EVIDENCE_SIZE} byte limit"
                        )
                    output.write(chunk)

            if size == 0:
                raise ValueError(f"Evidence file {filename!r} is empty")
            staged_paths.append(destination.relative_to(EVIDENCE_ROOT).as_posix())

        return temporary_directory, staged_paths
    except Exception:
        temporary_directory.cleanup()
        raise


@router.post("/claims/intake")
async def intake_claim(request: Request) -> dict[str, Any]:
    """Accept claim JSON or multipart evidence, then run the LangGraph workflow."""
    temporary_directory: tempfile.TemporaryDirectory[str] | None = None
    try:
        payload, uploads = await _parse_request(request)
        existing_paths = payload.get("evidence_files", [])
        if not isinstance(existing_paths, list):
            raise ValueError("evidence_files must be a list")

        if uploads:
            temporary_directory, staged_paths = await _stage_uploads(uploads)
            payload["evidence_files"] = [*existing_paths, *staged_paths]

        return await run_claim_intake(payload)
    except HTTPException:
        raise
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except Exception as error:
        logger.exception("Claim intake workflow failed")
        raise HTTPException(
            status_code=502,
            detail="Claim review services could not complete the request.",
        ) from error
    finally:
        if temporary_directory is not None:
            temporary_directory.cleanup()