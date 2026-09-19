from fastapi import FastAPI

from app.api import cases, evidence
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.app_name_display,
    description="Evidence-first organizational memory auditor",
)
app.include_router(cases.router)
app.include_router(evidence.router)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "database_path": get_settings().database_path}
