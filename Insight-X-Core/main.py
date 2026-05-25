from __future__ import annotations

import logging
import sys
import time
from typing import Any, Dict, List, Optional

from agents import (
    CoTReasoningAgent,
    IntentParserAgent,
    ReportGeneratorAgent,
    SelfCorrectionAgent,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)

logger = logging.getLogger("InsightXPipeline")


def run_insight_x_pipeline(
    document_paths: List[str],
    query: str,
    *,
    output_format: str = "markdown",
    max_correction_rounds: int = 3,
    agent_configs: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Insight-X 多 Agent 协同主工作流。

    ┌──────────────────────────────────────────────────────────────────┐
    │ Pipeline 执行顺序:                                               │
    │                                                                  │
    │  1. IntentParser  ──→ 拆解用户意图为子任务列表                    │
    │  2. CoTReasoning  ──→ 多跳推理 + 跨文档比对                      │
    │  3. SelfCorrection ──→ 事实校验 (最多 max_correction_rounds 轮)  │
    │  4. ReportGenerator──→ 组装结构化报告                             │
    │                                                                  │
    │  分布式调度说明:                                                  │
    │  当前为单进程串行执行，生产环境可通过以下方式水平扩展:              │
    │  - IntentParser / CoTReasoning 可并行处理不同子任务 (asyncio)     │
    │  - SelfCorrection 的 verify_facts 可分布式映射到校验集群          │
    │  - ReportGenerator 可流式输出 (SSE) 减少首字节延迟               │
    └──────────────────────────────────────────────────────────────────┘
    """

    pipeline_start = time.time()
    logger.info("=" * 70)
    logger.info("Insight-X Pipeline 启动 | 文档数: %d | 查询: %s", len(document_paths), query)
    logger.info("=" * 70)

    configs = agent_configs or {}

    # ── Stage 1: Intent Parsing ──────────────────────────────────────
    logger.info("─── Stage 1/4: Intent Parsing ───")
    intent_agent = IntentParserAgent(config=configs.get("intent_parser"))
    documents_text = _load_documents(document_paths)
    subtasks = intent_agent.process(documents_text, query=query)
    logger.info("意图拆解完成, 子任务数: %d", len(subtasks))

    # ── Stage 2: Chain-of-Thought Reasoning ──────────────────────────
    logger.info("─── Stage 2/4: CoT Reasoning ───")
    reasoning_agent = CoTReasoningAgent(config=configs.get("cot_reasoning"))
    reasoning_result = reasoning_agent.process(subtasks)
    logger.info(
        "推理完成, 跳数: %d, 跨文档证据: %d",
        reasoning_result.get("total_hops", 0),
        len(reasoning_result.get("cross_doc_evidence", [])),
    )

    # ── Stage 3: Self-Correction Loop ────────────────────────────────
    #
    # 纠错闭环设计:
    #   while correction_round < max_correction_rounds:
    #       verified = SelfCorrection.process(reasoning_result)
    #       if verified: break
    #       else: reasoning_result = CoTReasoning.re_process(verified)
    #
    # 并发控制说明:
    #   在分布式部署下，SelfCorrection 的多轮打回可由消息队列 (Kafka/RabbitMQ)
    #   协调，每轮纠错作为一个独立消费任务，避免阻塞主线程。
    #
    logger.info("─── Stage 3/4: Self-Correction (max %d rounds) ───", max_correction_rounds)
    correction_agent = SelfCorrectionAgent(config=configs.get("self_correction"))

    current_result = reasoning_result
    for round_idx in range(max_correction_rounds):
        logger.info("纠错轮次 %d/%d", round_idx + 1, max_correction_rounds)
        corrected = correction_agent.process(
            current_result,
            original_documents=[documents_text],
        )

        if corrected.get("corrected", False) or corrected.get("verification", {}).get("passed", True):
            if corrected.get("needs_rewrite", False):
                logger.info("检测到幻觉，触发重新推理...")
                current_result = reasoning_agent.process(subtasks)
                continue
            current_result = corrected
            logger.info("纠错通过 (轮次 %d)", round_idx + 1)
            break
        else:
            logger.warning("纠错未通过，打回重写...")
            current_result = reasoning_agent.process(subtasks)

    else:
        logger.warning("达到最大纠错轮次 %d，使用当前结果继续", max_correction_rounds)

    # ── Stage 4: Report Generation ───────────────────────────────────
    logger.info("─── Stage 4/4: Report Generation ───")
    report_agent = ReportGeneratorAgent(
        config={**configs.get("report_generator", {}), "output_format": output_format}
    )
    final_report = report_agent.process(current_result)

    pipeline_elapsed = time.time() - pipeline_start
    logger.info("=" * 70)
    logger.info(
        "Insight-X Pipeline 完成 | 总耗时: %.3fs | 格式: %s",
        pipeline_elapsed,
        output_format,
    )
    logger.info("=" * 70)

    return {
        "pipeline_status": "completed",
        "pipeline_elapsed_sec": round(pipeline_elapsed, 3),
        "correction_rounds": round_idx + 1 if 'round_idx' in dir() else 0,
        "subtask_count": len(subtasks),
        "reasoning_hops": reasoning_result.get("total_hops", 0),
        "report": final_report,
    }


def _load_documents(paths: List[str]) -> str:
    """
    加载文档内容。

    生产环境中此处应接入:
    - PDF 解析 (utils/pdf_parser.py)
    - Markdown 转换 (utils/markdown_converter.py)
    - 分布式文件系统 (S3/HDFS) 的异步读取
    当前使用 mock 数据模拟。
    """
    contents: List[str] = []
    for path in paths:
        try:
            with open(path, "r", encoding="utf-8") as f:
                contents.append(f.read())
        except FileNotFoundError:
            logger.warning("文档不存在: %s，使用 mock 数据替代", path)
            contents.append(f"[MOCK] 模拟文档内容: {path}")
        except Exception as exc:
            logger.error("文档读取失败: %s | 错误: %s", path, exc)
            contents.append(f"[ERROR] 无法读取: {path}")
    return "\n\n---\n\n".join(contents)


if __name__ == "__main__":
    result = run_insight_x_pipeline(
        document_paths=["sample_report_a.pdf", "sample_report_b.pdf"],
        query="分析两家公司在2024年Q3的营收增长驱动因素并对比差异",
    )
    print("\n" + "=" * 50)
    print("PIPELINE OUTPUT:")
    print("=" * 50)
    if isinstance(result.get("report", {}).get("report"), str):
        print(result["report"]["report"][:2000])
    else:
        print(str(result)[:2000])
