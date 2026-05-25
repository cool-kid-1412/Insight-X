from __future__ import annotations

import json
import time
from enum import Enum
from typing import Any, Dict, List, Optional

from agents.base_agent import AgentError, BaseAgent


class OutputFormat(str, Enum):
    JSON = "json"
    MARKDOWN = "markdown"


def mock_llm_call(prompt: str, temperature: float = 0.5, max_tokens: int = 4096) -> str:
    return json.dumps({
        "status": "ok",
        "content": f"[MOCK] 报告生成完成, prompt长度={len(prompt)}",
    }, ensure_ascii=False)


class ReportGeneratorAgent(BaseAgent):
    name: str = "ReportGenerator"

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.output_format: OutputFormat = OutputFormat(
            self.config.get("output_format", "markdown")
        )

    def process(self, input_data: Any, **kwargs: Any) -> Dict[str, Any]:
        start = time.time()
        self._log_start("报告生成", output_format=self.output_format.value)

        try:
            if not input_data:
                raise AgentError(self.name, "报告生成输入为空")

            verified_result: Dict[str, Any] = (
                input_data if isinstance(input_data, dict) else {"data": input_data}
            )

            if self.output_format == OutputFormat.JSON:
                report = self._generate_json_report(verified_result)
            else:
                report = self._generate_markdown_report(verified_result)

            elapsed = time.time() - start
            self._log_end("报告生成", elapsed, format=self.output_format.value, length=len(report))
            return {
                "report": report,
                "format": self.output_format.value,
                "metadata": {
                    "generated_at": time.time(),
                    "agent": self.name,
                    "hops": verified_result.get("total_hops", 0),
                    "corrected": verified_result.get("corrected", False),
                },
            }

        except AgentError:
            raise
        except Exception as exc:
            self.logger.exception("[%-20s] 报告生成发生未预期异常", self.name)
            raise AgentError(self.name, f"报告生成失败: {exc}") from exc

    def _generate_json_report(self, data: Dict[str, Any]) -> str:
        report_structure = {
            "title": "Insight-X 深度研报分析结果",
            "summary": data.get("final_conclusion", ""),
            "reasoning_chain": data.get("reasoning_chain", []),
            "cross_doc_evidence": data.get("cross_doc_evidence", []),
            "verification": data.get("verification", {}),
            "corrected": data.get("corrected", False),
        }
        return json.dumps(report_structure, ensure_ascii=False, indent=2)

    def _generate_markdown_report(self, data: Dict[str, Any]) -> str:
        sections: List[str] = []

        sections.append("# Insight-X 深度研报分析结果\n")

        conclusion = data.get("final_conclusion", "无结论")
        sections.append(f"## 核心结论\n\n{conclusion}\n")

        chain = data.get("reasoning_chain", [])
        if chain:
            sections.append("## 推理链路\n")
            for hop in chain:
                idx = hop.get("hop_index", "?")
                evidence = hop.get("evidence_text", "N/A")
                conf = hop.get("confidence", 0)
                corrected = " (已修正)" if hop.get("corrected") else ""
                sections.append(
                    f"### 第 {idx + 1} 跳{corrected}\n"
                    f"- **证据**: {evidence}\n"
                    f"- **置信度**: {conf:.2f}\n"
                )

        cross_doc = data.get("cross_doc_evidence", [])
        if cross_doc:
            sections.append("## 跨文档比对\n")
            for cmp in cross_doc:
                pair = cmp.get("doc_pair", ("?", "?"))
                relation = cmp.get("relation", "unknown")
                explanation = cmp.get("explanation", "")
                sections.append(
                    f"- **{pair[0]} ↔ {pair[1]}**: {relation} — {explanation}\n"
                )

        verification = data.get("verification", {})
        if verification:
            sections.append("## 事实校验\n")
            passed = verification.get("passed", False)
            reason = verification.get("reason", "")
            status_icon = "✅" if passed else "❌"
            sections.append(f"- **状态**: {status_icon} {'通过' if passed else '未通过'}\n")
            sections.append(f"- **说明**: {reason}\n")

        return "\n".join(sections)
