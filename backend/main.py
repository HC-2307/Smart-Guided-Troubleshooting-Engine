from fastapi import FastAPI
from backend.api.troubleshoot import router

app = FastAPI()

app.include_router(router, prefix="/api/v1")

@app.get("/health")
def health():
    return {"status": "ok"}

    