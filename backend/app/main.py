from fastapi import FastAPI

from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.app_name_display,
    description="Evidence-first organizational memory auditor",
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "database_path": get_settings().database_path}
