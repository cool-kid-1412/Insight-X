from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field, validator

from main import run_insight_x_pipeline

logger = logging.getLogger("InsightXAPI")

router = APIRouter(prefix="/v1/analyze", tags=["analyze"])


class AnalyzeRequest(BaseModel):
    document_paths: List[str] = Field(
        ...,
        description="待分析的文档路径列表",
        min_length=1,
        examples=[["report_a.pdf", "report_b.pdf"]],
    )
    query: str = Field(
        ...,
        description="用户查询指令",
        min_length=1,
        examples=["分析两家公司Q3营收差异"],
    )
    output_format: str = Field(
        default="markdown",
        description="输出格式: markdown | json",
    )
    max_correction_rounds: int = Field(
        default=3,
        description="最大纠错轮次",
        ge=1,
        le=10,
    )

    @validator("output_format")
    def validate_output_format(cls, v: str) -> str:
        if v not in ("markdown", "json"):
            raise ValueError("output_format 必须为 'markdown' 或 'json'")
        return v


class AnalyzeResponse(BaseModel):
    request_id: str
    status: str
    pipeline_elapsed_sec: float
    subtask_count: int
    reasoning_hops: int
    correction_rounds: int
    report: Dict[str, Any]


_task_store: Dict[str, Dict[str, Any]] = {}


@router.post(
    "/deep-report",
    response_model=AnalyzeResponse,
    summary="深度研报分析",
    description=(
        "基于多 Agent 协同与长链推理 (CoT) 的深度文档分析接口。"
        "支持跨文档比对、幻觉拦截与自动纠错闭环。"
    ),
)
async def deep_report_analyze(
    request: AnalyzeRequest,
    background_tasks: BackgroundTasks,
) -> AnalyzeResponse:
    """
    异步深度研报分析端点。

    ──────────────────────────────────────────────────────────────
    并发控制 & 分布式调度说明:
    ──────────────────────────────────────────────────────────────
    1. 当前实现使用 asyncio.to_thread 将同步 pipeline 委托至线程池，
       避免阻塞事件循环，保证 API 层的并发吞吐。
    2. 生产环境建议:
       - 使用 Celery / Ray / Dask 将 pipeline 任务分发至 Worker 集群
       - 通过 Redis / RabbitMQ 实现任务队列与结果回传
       - 对大文档场景启用流式响应 (SSE / WebSocket)
    3. 限流策略:
       - 建议在 Nginx / API Gateway 层配置 rate limiting
       - 单次请求文档总大小建议不超过 50MB
    ──────────────────────────────────────────────────────────────
    """

    import uuid

    request_id = uuid.uuid4().hex[:16]
    logger.info(
        "[API] 收到分析请求 | request_id=%s | 文档数=%d | query=%s",
        request_id, len(request.document_paths), request.query,
    )

    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: run_insight_x_pipeline(
                document_paths=request.document_paths,
                query=request.query,
                output_format=request.output_format,
                max_correction_rounds=request.max_correction_rounds,
            ),
        )

        return AnalyzeResponse(
            request_id=request_id,
            status=result.get("pipeline_status", "unknown"),
            pipeline_elapsed_sec=result.get("pipeline_elapsed_sec", 0),
            subtask_count=result.get("subtask_count", 0),
            reasoning_hops=result.get("reasoning_hops", 0),
            correction_rounds=result.get("correction_rounds", 0),
            report=result.get("report", {}),
        )

    except Exception as exc:
        logger.exception("[API] Pipeline 执行异常 | request_id=%s", request_id)
        raise HTTPException(
            status_code=500,
            detail=f"分析任务执行失败: {exc}",
        )
