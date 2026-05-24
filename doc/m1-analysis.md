# M1 复盘 — 核心骨架

> 状态：✅ 已完成
> 范围：protocol / tools / harness / skills / llm / session / observability / mcp / plugin / ipc / runtime 全部模块 + hello_agent 示例 + 7 个冒烟测试

---

## 1. 这一版交付了什么

```
src/agentkit/
├── protocol/         5 文件   纯 Pydantic 契约
├── tools/            6 文件   ABC + 装饰器 + Registry + Router + Exposure
├── harness/          2 文件   可组合 before/after 钩子
├── skills/           2 文件   markdown+frontmatter loader
├── llm/              2 文件   LiteLLM 封装 + 流式
├── session/          4 文件   Thread / Turn / Pool
├── observability/    3 文件   Tracer + InsightLog
├── mcp/              5 文件   client + pool + adapter + proxy_executor
├── plugin/           5 文件   App + 三个空 ABC（PromptBuilder/ArtifactFactory/ContextHook）
├── ipc/              2 文件   WebSocket
└── runtime/          2 文件   FastAPI + /healthz

examples/hello_agent/  echo + add 两个工具的最小 host
tests/test_smoke.py    7 个测试，无需 LLM key
```

---

## 2. 每个模块的设计合理性自审

### 2.1 protocol/ — 「这是宪法」

**设计**：5 个文件全是 Pydantic 模型，零 I/O，零业务逻辑。
**为什么合理**：所有上层模块共享同一套消息/工具/事件定义，跨进程时也只序列化这一套。
**疑点**：`Message` 用 `Union` 而不是 `Annotated[Union, Field(discriminator='role')]`——LiteLLM 转换时手写了 `_msg_to_dict`，目前够用。若将来要做 thread snapshot 反序列化，会需要 discriminator。**记一笔，不立即改**。

### 2.2 tools/ — 「最被高频触碰的 API」

**设计**：ABC（`ToolExecutor`）+ 装饰器（`@tool`）双轨。Registry 是普通 dict，Router 调度时插入 harness 和 tracer。
**为什么合理**：
- ABC 给重型工具（需要状态、需要继承）一个清晰落点
- 装饰器给一次性函数提供低门槛入口
- 两条路最终都产出 `ToolExecutor` 实例，Registry 不区分来源——上层项目想换写法不用改框架

**真踩过的坑**：
- `@tool` 第一版用 `class _FnExecutor(ToolExecutor): pass` + 后赋值 `handle`，被 ABC 的 `__abstractmethods__` 冻结机制咬到。改用 `type()` 动态建类把 `handle` 写进 namespace。这是 Python ABC 的已知陷阱，留下文档值得。

**疑点**：
- `ToolSearch` 只做关键词打分。规模一上来 LLM 嫌粗——但用 embedding 是肌肉层的事，不该进框架。**对**。
- Router 把工具结果转 ToolResult 的逻辑写死。若工具想返回二进制（mesh、图片），目前走不通。**M2 接 chatcfd 真工具时会暴露这个，到时再加 `binary_payload` 字段**。

### 2.3 harness/ — 「故意做小」

**设计**：就 `before_call` / `after_call` 两个 hook，外加 `make_hook()` 函数式糖。`Harness` 类只做"按顺序跑 hooks，第一个 veto 就停"。
**为什么合理**：chatcfd 现有 harness 234 行混了路径白名单、Coding 工具确认、大小限制——但这些都是**业务规则**，不是框架职责。框架只提供"在哪里挂钩"，规则是 host 写。
**疑点**：没有 around hook（before 和 after 中间能拿到时间/结果）。**目前 Tracer 已经覆盖了这个用途，不重复造轮子**。

### 2.4 skills/ — 「最薄的一层」

**设计**：一个 `SkillLoader` 类，扫目录，每个 .md 解析 frontmatter，得到 `Skill(name, description, body, metadata)`。
**为什么合理**：skill 是文本资产，应该能脱离代码独立增删改。frontmatter 给了"声明触发条件"的口子（`trigger: always` / `tool_search`），但触发逻辑在 `PromptBuilder` 里——加载和使用分离。
**疑点**：没有 skill 间依赖、没有 `@include`、没有变量插值。**KISS。如果 M2 真需要再加**。

### 2.5 llm/ — 「能换 provider 就够了」

**设计**：`LLMClient(model="...")` + `.complete(messages, tools)` 和 `.stream(...)`。LiteLLM 帮我们抹平 OpenAI/Anthropic/Bedrock/本地服务的差异。
**为什么合理**：Codex 自己做 ModelProvider trait 只支持两家。LiteLLM 现成的同样体量代码支持 100+ provider。没有理由重造。
**疑点**：retry 是固定指数退避（0.5 * 2^n），不区分错误类型（rate limit vs invalid request）。**M2 跑真量后会看出哪些错误根本不该 retry，到时改成 classified retry**。

### 2.6 session/ — 「Thread 是一等公民」

**设计**：`Thread` 持有 messages + metadata，`fork()` 是深拷贝，`ThreadPool` 是内存 dict。
**为什么合理**：用户原版 chatcfd 把 messages 直接堆在 `AgentSession`，没有 fork/resume 的概念——"我想从消息 17 开 case B 比较"做不到。Thread 抽出来后这种能力天然支持。
**疑点**：
- ThreadPool 重启丢全部。**对，所以 ThreadPool 是接口形态，将来加 SQLitePool 不破坏其他模块**。
- `fork()` 深拷贝消息——内存翻倍。**只有显式 fork 才发生，不是默认行为，可以接受**。

### 2.7 observability/ — 「JSONL 够了」

**设计**：`Tracer` 是 context manager 风格收集 spans 到内存 + 可被子类覆盖 `on_span`。`InsightLog` 就一个 `write(dict)` 写 JSONL。
**为什么合理**：90% 的 agent debug 场景是"这次 tool 调用为啥失败"、"这一轮花了多久"——`jq` 一个 JSONL 全搞定。OTLP/Prometheus 是规模到生产再考虑的事。
**疑点**：没有 span context propagation。**单进程目前用不到，分布式才需要，到时再补**。

### 2.8 mcp/ — 「最像 Codex 的部分」

**设计**：`MCPClient` 单连接（SSE/stdio）→ `MCPPool` 多服务器管理 → `MCPProxyExecutor` 把 MCP 工具包装成 `ToolExecutor` 注册进 Registry。
**为什么合理**：MCP 工具进系统后和本地工具走同一条 dispatch 链路——`Router` 不知道、`Harness` 不知道、`Tracer` 不知道。这就是「适配器在边界处」的胜利。
**疑点**：
- 没有重连/心跳。**Pool 暴露了 `reconnect(name)`，调用方可以在 tool 失败后手动重连。自动重连等真出 production 问题再加**。
- MCP 的 Resources/Prompts 没接。**chatcfd 现在用 stdio mempalace 也只是当 tool 用。到 M2 看真有没有 Resources 用例**。

### 2.9 plugin/ — 「上层项目的插座」

**设计**：`App` 是组装器，构造时接收 5 个口子（tools, mcp_servers, llm, harness, prompt_builder, artifact_factory, context_hooks），三个空 ABC（PromptBuilder/ArtifactFactory/ContextHook）让 host 覆盖。`App.turn()` 是主循环：LLM → tools → LLM → ... 最多 10 轮。
**为什么合理**：业务方写 host 时不需要 import session/tools/router/harness 这些模块——只需要继承 ABC 或直接传函数。
**疑点**：
- `turn()` 把流式事件 yield 出来由 IPC 层翻译——这是好设计。但 `complete` 而非 `stream`，没用上 LLM 流式。**M2 优先级提升**。
- `MAX_TOOL_ROUNDS = 10` 是常量。**应该可配，构造 App 时传入。M2 顺手改**。

### 2.10 ipc/ — 「先 WebSocket，其他后补」

**设计**：FastAPI WebSocket endpoint，client 发 `{type: "user_message", content: "..."}`，server stream 出 `StreamEvent`。
**为什么合理**：chatcfd 已经用 WebSocket，迁移 0 改动。
**疑点**：没有 thread_id 路由（每次连一个新 thread）、没有 cancel。**M3 做 Thread/Compact 时一起加**。

### 2.11 runtime/ — 「就是 uvicorn」

**设计**：`build_asgi(app)` 返回 FastAPI 实例，加上 `/healthz`。
**为什么合理**：没什么好说，要的就是普通。

---

## 3. 自我评估：原则有没有兑现

| 原则 | 兑现情况 | 证据 |
|---|---|---|
| 框架不掺业务 | ✅ | `grep -r -i "cfd\|simgraph\|case\|mesh" src/` 零命中 |
| 模块独立演进 | ✅ | tools 不 import mcp；mcp 不 import ipc；skills 不依赖任何 agentkit 模块 |
| 默认能跑 | ✅ | 三个 ABC 都有空实现，hello_agent 不写 plugin 也能起 |
| 最小内核 | ✅ | 31 个 .py，总 ~1100 行（不含测试） |
| 协议先行 | ✅ | protocol/ 是 leaf 节点，被所有人 import，自己不 import 任何 agentkit 模块 |

## 4. 已知遗留（按优先级）

| # | 待办 | 触发条件 |
|---|---|---|
| 1 | LLM 流式真正接进 `turn()` | M2 chatcfd 接入时如果体感慢就改 |
| 2 | `MAX_TOOL_ROUNDS` / `MAX_RETRIES` 等魔法常数变 App 参数 | M2 改，顺手事 |
| 3 | Router 支持二进制返回（mesh blob、图片） | M2 chatcfd 的 loadFile 工具会触发 |
| 4 | WebSocket 加 thread_id 路由 + cancel | M3 |
| 5 | LLM-based 上下文压缩 | M3 主要任务 |
| 6 | retry 按错误类型分类 | M2 跑真量后看到再说 |
| 7 | Message Union discriminator | thread snapshot 反序列化需要时 |
| 8 | MCP 自动重连 | 生产环境 MCP server 不稳时 |

---

## 5. 一句话总结

**M1 把 chatcfd 现有 agent 层里的"通用骨架"全部抽到 agentkit，业务 ABC 留空，证明了"agent 框架"和"agent 应用"可以分仓库独立演进。M2 之前不动框架代码——所有改动都应该在 host 项目里发生。**
