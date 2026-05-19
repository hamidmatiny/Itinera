"""FastAPI backend entrypoint for the AI Itinerary Generator."""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers.itinerary import router as itinerary_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

app = FastAPI(
    title="Itinera API",
    description="Hyper-personalized AI itinerary generation service",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(itinerary_router)


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Liveness probe for deployments and local dev."""
    return {"status": "ok"}
