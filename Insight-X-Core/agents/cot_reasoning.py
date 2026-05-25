from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional

from agents.base_agent import AgentError, BaseAgent


def mock_llm_call(prompt: str, temperature: float = 0.7, max_tokens: int = 4096) -> str:
    return json.dumps({
        "status": "ok",
        "content": f"[MOCK] 推理完成，prompt长度={len(prompt)}",
    }, ensure_ascii=False)


class CoTReasoningAgent(BaseAgent):
    name: str = "CoTReasoning"

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.max_hops: int = self.config.get("max_hops", 5)
        self.cross_doc_enabled: bool = self.config.get("cross_doc_enabled", True)

    def process(self, input_data: Any, **kwargs: Any) -> Dict[str, Any]:
        start = time.time()
        self._log_start("多跳推理", subtask_count=len(input_data) if isinstance(input_data, list) else 1)

        try:
            if not input_data:
                raise AgentError(self.name, "推理输入为空")

            subtasks = input_data if isinstance(input_data, list) else [input_data]
            reasoning_chain: List[Dict[str, Any]] = []

            for hop_idx in range(self.max_hops):
                self.logger.info(
                    "[%-20s] ◈ 推理跳数 %d/%d | 已收集证据: %d 条",
                    self.name, hop_idx + 1, self.max_hops, len(reasoning_chain),
                )

                hop_result = self._execute_hop(subtasks, hop_idx, reasoning_chain)
                reasoning_chain.append(hop_result)

                if hop_result.get("confidence", 0) >= 0.85:
                    self.logger.info(
                        "[%-20s] ◈ 置信度 %.2f >= 0.85，提前终止推理链",
                        self.name, hop_result["confidence"],
                    )
                    break

            cross_doc_evidence = []
            if self.cross_doc_enabled:
                cross_doc_evidence = self._cross_document_compare(reasoning_chain)

            result = {
                "reasoning_chain": reasoning_chain,
                "cross_doc_evidence": cross_doc_evidence,
                "final_conclusion": self._synthesize(reasoning_chain, cross_doc_evidence),
                "total_hops": len(reasoning_chain),
            }

            elapsed = time.time() - start
            self._log_end("多跳推理", elapsed, hops=len(reasoning_chain), evidence=len(cross_doc_evidence))
            return result

        except AgentError:
            raise
        except Exception as exc:
            self.logger.exception("[%-20s] 推理过程发生未预期异常", self.name)
            raise AgentError(self.name, f"推理失败: {exc}") from exc

    def _execute_hop(
        self,
        subtasks: List[Dict[str, Any]],
        hop_idx: int,
        prev_chain: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        执行单跳推理。

        多跳推理（Multi-hop Reasoning）的核心思想：
        ─────────────────────────────────────────────
        第1跳: 从原始文档中提取与子任务直接相关的表层事实 (Surface Facts)
        第2跳: 基于第1跳的事实，沿语义关联向外扩展，获取间接证据
        第3跳+: 将前序跳的证据进行交叉验证，发现矛盾或补充支撑
        ─────────────────────────────────────────────
        每一跳的输出都包含: evidence_text, source_doc, confidence, hop_index
        后续跳会消费前序跳的输出作为上下文，形成链式推导结构。
        """

        context_summary = ""
        if prev_chain:
            context_summary = " | ".join(
                f"跳{r['hop_index']}: {r.get('evidence_text', '')[:80]}"
                for r in prev_chain[-3:]
            )

        prompt = (
            f"你是一个深度推理引擎，当前执行第 {hop_idx + 1} 跳推理。\n"
            f"前序推理上下文: {context_summary}\n"
            f"子任务列表: {json.dumps(subtasks, ensure_ascii=False)}\n"
            f"请基于上下文进行推理，输出: evidence_text, source_doc, confidence(0-1), hop_index。\n"
            f"以 JSON 格式返回。"
        )

        raw = mock_llm_call(prompt, temperature=0.2 + hop_idx * 0.1, max_tokens=4096)

        try:
            parsed = json.loads(raw)
            content = parsed.get("content", "{}")
            hop_result = json.loads(content) if isinstance(content, str) else content
        except (json.JSONDecodeError, TypeError):
            hop_result = {
                "evidence_text": f"[MOCK] 第{hop_idx+1}跳推理结果",
                "source_doc": "doc_0",
                "confidence": 0.5 + hop_idx * 0.1,
                "hop_index": hop_idx,
            }

        hop_result.setdefault("hop_index", hop_idx)
        hop_result.setdefault("confidence", 0.5)
        return hop_result

    def _cross_document_compare(self, chain: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        跨文档比对逻辑。

        在多文档场景下，不同文档对同一实体/事件可能存在：
        1. 互补信息 (Complementary) —— 可合并增强结论
        2. 矛盾信息 (Contradictory)  —— 需要标记并交给 SelfCorrection 处理
        3. 冗余信息 (Redundant)      —— 去重后保留置信度最高的来源

        本方法模拟跨文档比对过程，将推理链中来自不同文档的证据进行两两比较，
        输出比对结果列表。
        """
        self.logger.info("[%-20s] ◈ 开始跨文档比对，证据数: %d", self.name, len(chain))

        evidence_by_doc: Dict[str, List[Dict[str, Any]]] = {}
        for ev in chain:
            doc_id = ev.get("source_doc", "unknown")
            evidence_by_doc.setdefault(doc_id, []).append(ev)

        comparisons: List[Dict[str, Any]] = []
        doc_ids = list(evidence_by_doc.keys())

        for i in range(len(doc_ids)):
            for j in range(i + 1, len(doc_ids)):
                doc_a, doc_b = doc_ids[i], doc_ids[j]
                ev_a_list, ev_b_list = evidence_by_doc[doc_a], evidence_by_doc[doc_b]

                prompt = (
                    f"比对文档 {doc_a} 和 {doc_b} 的证据:\n"
                    f"证据A: {json.dumps(ev_a_list, ensure_ascii=False)}\n"
                    f"证据B: {json.dumps(ev_b_list, ensure_ascii=False)}\n"
                    f"请判断: complementary / contradictory / redundant，并给出说明。\n"
                    f"以 JSON 返回。"
                )

                raw = mock_llm_call(prompt, temperature=0.1)
                try:
                    parsed = json.loads(raw)
                    content = parsed.get("content", "{}")
                    cmp_result = json.loads(content) if isinstance(content, str) else content
                except (json.JSONDecodeError, TypeError):
                    cmp_result = {
                        "doc_pair": (doc_a, doc_b),
                        "relation": "complementary",
                        "explanation": f"[MOCK] {doc_a} 与 {doc_b} 证据互补",
                    }

                cmp_result.setdefault("doc_pair", (doc_a, doc_b))
                comparisons.append(cmp_result)

        self.logger.info(
            "[%-20s] ◈ 跨文档比对完成，共 %d 对比较",
            self.name, len(comparisons),
        )
        return comparisons

    def _synthesize(
        self,
        chain: List[Dict[str, Any]],
        cross_doc: List[Dict[str, Any]],
    ) -> str:
        contradictions = [c for c in cross_doc if c.get("relation") == "contradictory"]
        if contradictions:
            return f"推理链中发现 {len(contradictions)} 处跨文档矛盾，需进入纠错环节"
        return "推理链完整，各跳证据一致，结论可信"
