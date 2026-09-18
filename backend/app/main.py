from fastapi import FastAPI

from app.core.config import get_settings

app = FastAPI(title="KEEPER", description="Evidence-first organizational memory auditor")


@app.get("/api/health")
def health() -> dict[str, str]:
    settings = get_settings()
    return {"status": "ok", "database_path": settings.database_path}
