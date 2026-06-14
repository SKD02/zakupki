from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import upload, dictionaries, mappings, applications, supplier_search, batches

app = FastAPI(title="Procurement Assistant API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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

@app.get("/api/health")
def health():
    return {"status": "ok"}
