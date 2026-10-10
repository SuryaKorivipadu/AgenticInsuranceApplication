from typing import Dict

from fastapi import FastAPI

from app.api.api import router as api_router
from app.utils.logging import get_logger

app = FastAPI()
app.include_router(api_router, prefix="/api")
logger = get_logger(__name__)


@app.get("/", response_model=Dict[str, str])
def root() -> Dict[str, str]:
    """Return the application health status."""
    return {"message": "Fast API application is running. Status is healthy."}
