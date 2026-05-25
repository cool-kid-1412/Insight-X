from __future__ import annotations

import logging
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class AgentContext:
    context_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    session_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)


class AgentError(Exception):
    def __init__(self, agent_name: str, message: str, context: Optional[AgentContext] = None):
        self.agent_name = agent_name
        self.context = context
        super().__init__(f"[{agent_name}] {message}")


class BaseAgent(ABC):
    name: str = "BaseAgent"

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.logger = logging.getLogger(self.__class__.__name__)
        self._context: Optional[AgentContext] = None

    @property
    def context(self) -> AgentContext:
        if self._context is None:
            self._context = AgentContext()
        return self._context

    def _log_start(self, action: str, **kwargs: Any) -> None:
        self.logger.info(
            "[%-20s] ▶ 开始执行: %s | 参数: %s",
            self.name,
            action,
            kwargs,
        )

    def _log_end(self, action: str, elapsed: float, **kwargs: Any) -> None:
        self.logger.info(
            "[%-20s] ✔ 执行完成: %s | 耗时: %.3fs | %s",
            self.name,
            action,
            elapsed,
            kwargs,
        )

    @abstractmethod
    def process(self, input_data: Any, **kwargs: Any) -> Any:
        raise NotImplementedError("子类必须实现 process 方法")

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(name={self.name})>"
