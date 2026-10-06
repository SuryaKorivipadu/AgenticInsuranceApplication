from typing import Dict

from fastapi import FastAPI

from app.utils.logging import get_logger

app = FastAPI()
logger = get_logger(__name__)


@app.get("/", response_model=Dict[str, str])
def root() -> Dict[str, str]:
    """Return the application health status."""
    return {"message": "Fast API application is running. Status is healthy."}
