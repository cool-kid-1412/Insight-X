from __future__ import annotations

import logging
import sys

from fastapi import FastAPI

from api.routes import router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)

app = FastAPI(
    title="Insight-X-Core API",
    description="基于多 Agent 协同与长链推理 (CoT) 的复杂长文本深度解析系统",
    version="0.1.0",
)

app.include_router(router)


@app.get("/health", tags=["system"])
async def health_check():
    return {"status": "healthy", "service": "Insight-X-Core"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "api:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
