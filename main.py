from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings


app = FastAPI(
    title="TOIR Backend API",
    version="0.1.0",
    description="Backend service for the TOIR application.",
)


@app.on_event("startup")
async def startup_event():
    print("Starting up TOIR backend...")


@app.on_event("shutdown")
async def shutdown_event():
    print("Shutting down TOIR backend...")


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "ok", "service": "toir-backend"}