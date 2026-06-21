import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from app.routers import upload, dictionaries, mappings, applications, supplier_search, batches, contracts, audit, settings as settings_router
from app.config import settings

app = FastAPI(title="Procurement Assistant API", version="1.0.0")

def parse_cors_origins(value: str):
    if not value or value.strip() == "*":
        return ["*"]
    return [origin.strip() for origin in value.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=parse_cors_origins(settings.CORS_ORIGINS),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(upload.router, prefix="/api/upload", tags=["Upload"])
app.include_router(dictionaries.router, prefix="/api/dictionaries", tags=["Dictionaries"])
app.include_router(mappings.router, prefix="/api/mappings", tags=["Mappings"])
app.include_router(applications.router, prefix="/api/applications", tags=["Applications"])
app.include_router(supplier_search.router, prefix="/api/supplier-search", tags=["Supplier Search"])
app.include_router(batches.router, prefix="/api/procurement-batches", tags=["Procurement Batches"])
app.include_router(contracts.router, prefix="/api/contracts", tags=["Contracts"])
app.include_router(audit.router, prefix="/api/audit", tags=["Audit"])
app.include_router(settings_router.router, prefix="/api/settings", tags=["Settings"])

@app.get("/api/health")
def health():
    return {"status": "ok"}


FRONTEND_DIST_DIR = Path(os.getenv("FRONTEND_DIST_DIR", Path.cwd().parent / "frontend" / "dist")).resolve()
if FRONTEND_DIST_DIR.exists():
    assets_dir = FRONTEND_DIST_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_frontend(full_path: str):
        requested = (FRONTEND_DIST_DIR / full_path).resolve() if full_path else FRONTEND_DIST_DIR / "index.html"
        if full_path and requested.is_file() and FRONTEND_DIST_DIR in requested.parents:
            return FileResponse(requested)
        return FileResponse(FRONTEND_DIST_DIR / "index.html")
