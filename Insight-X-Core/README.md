# Insight-X-Core

> 基于多 Agent 协同与长链推理（CoT）的复杂长文本深度解析系统

---

## 项目简介

**Insight-X-Core** 是一个面向研报/长文本场景的多智能体深度分析框架。系统通过四个核心 Agent 的协同工作，实现了从意图拆解、多跳推理、跨文档比对到幻觉拦截与自动纠错的完整闭环，最终输出结构化的深度分析报告。

核心特性：

- **多跳推理 (Multi-hop Reasoning)**：逐跳扩展证据链，支持置信度提前终止
- **跨文档比对**：自动识别互补/矛盾/冗余的跨文档证据关系
- **幻觉拦截 (Hallucination Detection)**：基于置信度偏差的事实校验，触发 `HallucinationError` 自动拦截
- **纠错闭环 (Self-Correction Loop)**：最多 N 轮打回重写，确保输出可靠性
- **异步 API**：FastAPI + `run_in_executor` 非阻塞并发

---

## 架构图

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Insight-X Pipeline                           │
│                                                                     │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────────┐  │
│  │   Intent      │    │   CoT        │    │   Self-Correction    │  │
│  │   Parser      │───▶│   Reasoning  │───▶│   Agent              │  │
│  │   Agent       │    │   Agent      │    │                      │  │
│  └──────────────┘    └──────────────┘    │  verify_facts()      │  │
│       │  拆解子任务     │  多跳推理        │       │               │  │
│       │                 │  跨文档比对      │       ▼               │  │
│       │                 │                 │  ┌─────────────┐     │  │
│       │                 │                 │  │ passed?     │     │  │
│       │                 │                 │  └──┬──────┬───┘     │  │
│       │                 │                 │     │ YES   │ NO      │  │
│       │                 │                 │     ▼       │         │  │
│       │                 │  ◀── 打回重写 ──┼─────────────┘         │  │
│       │                 │  (max 3 rounds) │                       │  │
│       │                 │                 │  🚫 HallucinationError│  │
│       │                 │                 └──────────┬────────────┘  │
│       │                 │                            │               │
│       │                 │                            ▼               │
│       │                 │                 ┌──────────────────────┐  │
│       │                 │                 │   Report Generator   │  │
│       │                 │────────────────▶│   Agent              │  │
│       │                 │                 │   (JSON / Markdown)  │  │
│       │                 │                 └──────────────────────┘  │
│       │                 │                            │               │
│       │                 │                            ▼               │
│       │                 │                 ┌──────────────────────┐  │
│       │                 │                 │   Structured Report  │  │
│       │                 │                 └──────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 快速安装

```bash
# 克隆仓库
git clone https://github.com/your-org/Insight-X-Core.git
cd Insight-X-Core

# 创建虚拟环境 (推荐)
python -m venv .venv
source .venv/bin/activate   # Linux/macOS
# .venv\Scripts\activate    # Windows

# 安装依赖
pip install -r requirements.txt
```

---

## 使用方式

### 1. 命令行运行 Pipeline

```bash
python main.py
```

### 2. 启动 API 服务

```bash
# 方式一: 直接运行
python -m api

# 方式二: 使用 uvicorn
uvicorn api:app --host 0.0.0.0 --port 8000 --reload
```

### 3. 调用 API

```bash
curl -X POST http://localhost:8000/v1/analyze/deep-report \
  -H "Content-Type: application/json" \
  -d '{
    "document_paths": ["report_a.pdf", "report_b.pdf"],
    "query": "分析两家公司在2024年Q3的营收增长驱动因素并对比差异",
    "output_format": "markdown",
    "max_correction_rounds": 3
  }'
```

### 4. 访问 API 文档

启动服务后访问: `http://localhost:8000/docs`

---

## 示例输出日志

```
2026-05-25 10:23:01 | INFO     | InsightXPipeline     | ======================================================================
2026-05-25 10:23:01 | INFO     | InsightXPipeline     | Insight-X Pipeline 启动 | 文档数: 2 | 查询: 分析两家公司在2024年Q3的营收增长驱动因素并对比差异
2026-05-25 10:23:01 | INFO     | InsightXPipeline     | ─── Stage 1/4: Intent Parsing ───
2026-05-25 10:23:01 | INFO     | IntentParser         | [IntentParser        ] ▶ 开始执行: 意图拆解 | 参数: {'document_length': 15234}
2026-05-25 10:23:01 | INFO     | IntentParser         | [IntentParser        ] ✔ 执行完成: 意图拆解 | 耗时: 0.003s | {'subtask_count': 4}
2026-05-25 10:23:01 | INFO     | InsightXPipeline     | ─── Stage 2/4: CoT Reasoning ───
2026-05-25 10:23:01 | INFO     | CoTReasoning         | [CoTReasoning        ] ▶ 开始执行: 多跳推理 | 参数: {'subtask_count': 4}
2026-05-25 10:23:01 | INFO     | CoTReasoning         | [CoTReasoning        ] ◈ 推理跳数 1/5 | 已收集证据: 0 条
2026-05-25 10:23:01 | INFO     | CoTReasoning         | [CoTReasoning        ] ◈ 推理跳数 2/5 | 已收集证据: 1 条
2026-05-25 10:23:01 | INFO     | CoTReasoning         | [CoTReasoning        ] ◈ 推理跳数 3/5 | 已收集证据: 2 条
2026-05-25 10:23:01 | INFO     | CoTReasoning         | [CoTReasoning        ] ◈ 开始跨文档比对，证据数: 3
2026-05-25 10:23:01 | INFO     | CoTReasoning         | [CoTReasoning        ] ◈ 跨文档比对完成，共 1 对比较
2026-05-25 10:23:01 | INFO     | CoTReasoning         | [CoTReasoning        ] ✔ 执行完成: 多跳推理 | 耗时: 0.008s | {'hops': 3, 'evidence': 1}
2026-05-25 10:23:01 | INFO     | InsightXPipeline     | ─── Stage 3/4: Self-Correction (max 3 rounds) ───
2026-05-25 10:23:01 | INFO     | SelfCorrection       | [SelfCorrection      ] ▶ 开始执行: 反思纠错 | 参数: {'data_type': 'dict'}
2026-05-25 10:23:01 | WARNING | SelfCorrection       | [SelfCorrection      ] ⚠ 事实校验未通过 | 原因: 2 条声明未通过校验
2026-05-25 10:23:01 | INFO     | SelfCorrection       | [SelfCorrection      ] ↻ 开始修正 2 条未通过声明
2026-05-25 10:23:01 | INFO     | SelfCorrection       | [SelfCorrection      ] ✔ 执行完成: 反思纠错(已修正) | 耗时: 0.005s | {'corrected': True}
2026-05-25 10:23:01 | INFO     | InsightXPipeline     | 纠错通过 (轮次 1)
2026-05-25 10:23:01 | INFO     | InsightXPipeline     | ─── Stage 4/4: Report Generation ───
2026-05-25 10:23:01 | INFO     | ReportGenerator      | [ReportGenerator     ] ▶ 开始执行: 报告生成 | 参数: {'output_format': 'markdown'}
2026-05-25 10:23:01 | INFO     | ReportGenerator      | [ReportGenerator     ] ✔ 执行完成: 报告生成 | 耗时: 0.001s | {'format': 'markdown', 'length': 523}
2026-05-25 10:23:01 | INFO     | InsightXPipeline     | ======================================================================
2026-05-25 10:23:01 | INFO     | InsightXPipeline     | Insight-X Pipeline 完成 | 总耗时: 0.021s | 格式: markdown
2026-05-25 10:23:01 | INFO     | InsightXPipeline     | ======================================================================
```

---

## 项目结构

```
Insight-X-Core/
├── agents/                     # 核心 Agent 模块
│   ├── __init__.py
│   ├── base_agent.py           # 抽象基类 BaseAgent + AgentContext + AgentError
│   ├── intent_parser.py        # 意图拆解 Agent
│   ├── cot_reasoning.py        # 多跳推理 + 跨文档比对 Agent
│   ├── self_correction.py      # 反思纠错 Agent + HallucinationError
│   └── report_generator.py     # 报告生成 Agent (JSON/Markdown)
├── core/                       # 基础设施模块
│   ├── chunking.py             # 长文本切片
│   ├── prompts.py              # 提示词模板
│   └── memory.py               # 记忆管理
├── api/                        # FastAPI 接口层
│   ├── __init__.py             # FastAPI app 入口
│   └── routes.py               # /v1/analyze/deep-report 端点
├── utils/                      # 工具模块
│   ├── pdf_parser.py           # PDF 解析
│   └── markdown_converter.py   # Markdown 转换
├── main.py                     # Pipeline 主工作流
├── requirements.txt
└── .gitignore
```

---

## License

MIT
