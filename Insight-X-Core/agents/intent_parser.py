from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional

from agents.base_agent import AgentError, BaseAgent


def mock_llm_call(prompt: str, temperature: float = 0.7, max_tokens: int = 2048) -> str:
    return json.dumps({
        "status": "ok",
        "content": f"[MOCK] 模拟响应 prompt 长度={len(prompt)}",
    }, ensure_ascii=False)


class IntentParserAgent(BaseAgent):
    name: str = "IntentParser"

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.max_subtasks: int = self.config.get("max_subtasks", 8)

    def process(self, input_data: Any, **kwargs: Any) -> List[Dict[str, Any]]:
        start = time.time()
        self._log_start("意图拆解", document_length=len(str(input_data)))

        try:
            if not input_data:
                raise AgentError(self.name, "输入数据为空，无法进行意图解析")

            query: str = kwargs.get("query", "")
            if not query:
                raise AgentError(self.name, "缺少用户查询指令 (query)")

            prompt = self._build_parse_prompt(str(input_data), query)
            raw_response = mock_llm_call(prompt, temperature=0.3)
            subtasks = self._parse_subtasks(raw_response)

            elapsed = time.time() - start
            self._log_end("意图拆解", elapsed, subtask_count=len(subtasks))
            return subtasks

        except AgentError:
            raise
        except Exception as exc:
            self.logger.exception("[%-20s] 意图拆解发生未预期异常", self.name)
            raise AgentError(self.name, f"意图拆解失败: {exc}") from exc

    def _build_parse_prompt(self, document: str, query: str) -> str:
        return (
            f"你是一个专业的研究意图分析器。\n"
            f"用户查询: {query}\n"
            f"文档摘要(前500字): {document[:500]}\n"
            f"请将用户查询拆解为最多{self.max_subtasks}个可独立执行的子任务，"
            f"每个子任务包含: task_id, description, priority, dependencies。\n"
            f"以 JSON 数组格式返回。"
        )

    def _parse_subtasks(self, raw_response: str) -> List[Dict[str, Any]]:
        try:
            parsed = json.loads(raw_response)
            content = parsed.get("content", "[]")
            subtasks = json.loads(content) if isinstance(content, str) else content
        except (json.JSONDecodeError, TypeError):
            self.logger.warning("[%-20s] LLM 返回非标准 JSON，使用降级策略", self.name)
            subtasks = [
                {"task_id": 0, "description": "全量文档分析(降级)", "priority": 1, "dependencies": []}
            ]

        if len(subtasks) > self.max_subtasks:
            self.logger.warning(
                "[%-20s] 子任务数 %d 超过上限 %d，自动截断",
                self.name, len(subtasks), self.max_subtasks,
            )
            subtasks = subtasks[: self.max_subtasks]

        return subtasks
