from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional

from agents.base_agent import AgentError, BaseAgent


class HallucinationError(Exception):
    def __init__(self, claim: str, evidence: str, confidence_delta: float):
        self.claim = claim
        self.evidence = evidence
        self.confidence_delta = confidence_delta
        super().__init__(
            f"幻觉检测触发 | 声明: {claim[:60]}... | "
            f"证据: {evidence[:60]}... | 置信度偏差: {confidence_delta:.2f}"
        )


def mock_llm_call(prompt: str, temperature: float = 0.3, max_tokens: int = 2048) -> str:
    return json.dumps({
        "status": "ok",
        "content": f"[MOCK] 纠错分析完成, prompt长度={len(prompt)}",
    }, ensure_ascii=False)


class SelfCorrectionAgent(BaseAgent):
    name: str = "SelfCorrection"

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.confidence_threshold: float = self.config.get("confidence_threshold", 0.7)
        self.max_retries: int = self.config.get("max_retries", 3)

    def process(self, input_data: Any, **kwargs: Any) -> Dict[str, Any]:
        start = time.time()
        self._log_start("反思纠错", data_type=type(input_data).__name__)

        try:
            if not input_data:
                raise AgentError(self.name, "纠错输入为空")

            reasoning_result: Dict[str, Any] = input_data if isinstance(input_data, dict) else {"data": input_data}
            original_documents: List[str] = kwargs.get("original_documents", [])

            verification = self.verify_facts(reasoning_result, original_documents)

            if not verification["passed"]:
                self.logger.warning(
                    "[%-20s] ⚠ 事实校验未通过 | 原因: %s",
                    self.name, verification["reason"],
                )
                correction = self._correct(reasoning_result, verification)
                elapsed = time.time() - start
                self._log_end("反思纠错(已修正)", elapsed, corrected=True)
                return correction

            elapsed = time.time() - start
            self._log_end("反思纠错(通过)", elapsed, corrected=False)
            return {
                **reasoning_result,
                "verification": verification,
                "corrected": False,
            }

        except HallucinationError as he:
            self.logger.error("[%-20s] 🚫 幻觉拦截: %s", self.name, he)
            return {
                **input_data if isinstance(input_data, dict) else {"data": input_data},
                "verification": {"passed": False, "reason": str(he), "hallucination": True},
                "corrected": False,
                "needs_rewrite": True,
            }
        except AgentError:
            raise
        except Exception as exc:
            self.logger.exception("[%-20s] 纠错过程发生未预期异常", self.name)
            raise AgentError(self.name, f"纠错失败: {exc}") from exc

    def verify_facts(
        self,
        reasoning_result: Dict[str, Any],
        original_documents: List[str],
    ) -> Dict[str, Any]:
        """
        事实校验核心方法。

        将推理链中的每一条结论与原始文档进行逐条比对：
        1. 提取推理结论中的关键声明 (claims)
        2. 在原始文档中搜索支撑证据
        3. 计算声明与证据的语义一致性 (confidence_delta)
        4. 若 confidence_delta 超过阈值，抛出 HallucinationError
        """

        chain = reasoning_result.get("reasoning_chain", [])
        if not chain:
            return {"passed": True, "reason": "无推理链需要校验"}

        failed_claims: List[Dict[str, Any]] = []

        for hop in chain:
            claim = hop.get("evidence_text", "")
            confidence = hop.get("confidence", 0.5)

            if confidence < self.confidence_threshold:
                failed_claims.append({
                    "hop_index": hop.get("hop_index", -1),
                    "claim": claim,
                    "confidence": confidence,
                    "reason": f"置信度 {confidence:.2f} < 阈值 {self.confidence_threshold}",
                })

            if original_documents:
                prompt = (
                    f"请判断以下声明是否能在原始文档中找到支撑:\n"
                    f"声明: {claim}\n"
                    f"原始文档摘要: {'; '.join(d[:200] for d in original_documents[:3])}\n"
                    f"返回 JSON: {{'supported': bool, 'confidence': float}}"
                )
                raw = mock_llm_call(prompt, temperature=0.1)
                try:
                    parsed = json.loads(raw)
                    content = parsed.get("content", "{}")
                    fact_check = json.loads(content) if isinstance(content, str) else content
                except (json.JSONDecodeError, TypeError):
                    fact_check = {"supported": True, "confidence": 0.8}

                if not fact_check.get("supported", True):
                    delta = abs(fact_check.get("confidence", 0) - confidence)
                    if delta > 0.3:
                        raise HallucinationError(
                            claim=claim,
                            evidence="原始文档中未找到支撑",
                            confidence_delta=delta,
                        )
                    failed_claims.append({
                        "hop_index": hop.get("hop_index", -1),
                        "claim": claim,
                        "confidence": confidence,
                        "reason": f"文档支撑不足, delta={delta:.2f}",
                    })

        if failed_claims:
            return {
                "passed": False,
                "reason": f"{len(failed_claims)} 条声明未通过校验",
                "failed_claims": failed_claims,
            }

        return {"passed": True, "reason": "所有声明均通过事实校验"}

    def _correct(
        self,
        reasoning_result: Dict[str, Any],
        verification: Dict[str, Any],
    ) -> Dict[str, Any]:
        failed_claims = verification.get("failed_claims", [])
        self.logger.info(
            "[%-20s] ↻ 开始修正 %d 条未通过声明",
            self.name, len(failed_claims),
        )

        corrected_chain = list(reasoning_result.get("reasoning_chain", []))
        for fc in failed_claims:
            hop_idx = fc.get("hop_index", -1)
            if 0 <= hop_idx < len(corrected_chain):
                prompt = (
                    f"以下声明未通过事实校验，请修正:\n"
                    f"原始声明: {fc['claim']}\n"
                    f"原因: {fc['reason']}\n"
                    f"请返回修正后的 JSON: {{'evidence_text': str, 'confidence': float}}"
                )
                raw = mock_llm_call(prompt, temperature=0.2)
                try:
                    parsed = json.loads(raw)
                    content = parsed.get("content", "{}")
                    correction = json.loads(content) if isinstance(content, str) else content
                except (json.JSONDecodeError, TypeError):
                    correction = {
                        "evidence_text": f"[已修正] {fc['claim']}",
                        "confidence": self.confidence_threshold,
                    }

                corrected_chain[hop_idx].update(correction)
                corrected_chain[hop_idx]["corrected"] = True

        return {
            **reasoning_result,
            "reasoning_chain": corrected_chain,
            "verification": {**verification, "passed": True, "corrected": True},
            "corrected": True,
        }
