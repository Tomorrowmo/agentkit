# agentkit 框架设计

> 状态：**设计讨论阶段（M-1）**，暂不动手编码
> 创建：2026-05-24
> 仓库：`d:\Git\Personal\agentKit`

---

## 〇、文档导读

本文档是 agentkit 通用 agent 框架的设计起点，记录：

1. 调研 openai/codex 后得出的工程启发
2. chatcfd 现有 agent 层的现状诊断
3. agentkit 的分层架构、目录结构、模块职责
4. MCP 与工具系统的关系（三类"工具"的归属）
5. 可视化全景图（6 张）
6. 落地路线图
7. 待讨论的设计问题清单

阅读顺序建议：先看「二、关键判断」→「七、可视化全景」→ 其余按需。

---

## 一、背景与目标

**用户原始需求**

> 我想利用 openai/codex 这个项目来重构 chatcfd。因为对 Agent 的框架不熟悉，里面的坑点也不知道，所以最好是有参照。不是完全复用 codex，而是基于他的 agent 架构来重构。我希望有一套 agent 的框架，这样未来我是做 chatcfd 还是 simgraph，还是其他的 agent，我都可以基于这套架构上去做。

**目标**

- 抽出**独立的、可扩展的** agent 框架 `agentkit`
- 上层应用（chatcfd / simgraph / 未来其他项目）通过 plugin 接入
- 统一工具接入方式、skill 设计、prompt 演进路径
- 仓库位置：`d:\Git\Personal\agentKit`，独立于 chatcfd / simgraph

---

## 二、关键判断

**Codex 不是 agent framework，是一个 coding agent**。仓库描述就是 "Lightweight coding agent that runs in your terminal"。

但它的工程纪律非常强：把 protocol / tools / session / app-server / skills / sandboxing 都做了独立 crate 拆分——**值得抄的是"分层与边界"，不是代码**。

而且它是 **Rust（129 个 crate + Bazel）写的**。我们是 Python。**代码 0% 可复用，思想 80% 可借鉴**。

### 好处 vs 坏处

| 维度 | 好处 | 坏处 |
|---|---|---|
| **工程参照** | 分层契约（protocol / core / tools / app-server）、ToolExecutor trait、Registry+Router、ThreadManager、Skill 嵌入机制——这套"准 framework"骨架成熟可抄 | Rust→Python 重写工作量大；Codex 的并发模型（Arc+async trait）在 Python 里要换成不同范式 |
| **可复用性** | `app-server-protocol` 的 JSON-RPC 方法表跨语言可移植；ToolExposure（Direct/Deferred/Hidden）+ ToolSearch 对算法越来越多时是杀手锏 | Codex 的 sandbox（landlock/seatbelt/bwrap）、apply_patch、execpolicy、git-utils、code-mode 全是 coding 专属，完全用不上 |
| **LLM 适配** | — | Codex 实际只支持 OpenAI Responses API + Bedrock，**没有真正的多 provider 抽象**。我们用 LiteLLM |
| **学习成本** | 工程边界示范作用强（"resist adding code to codex-core" 这种纪律） | 直接读 Rust 源码门槛高，agent_jobs/multi_agents/realtime-webrtc 这些重型设施会带偏 |

**底线**：把 Codex 当**架构参考书**用，不要当**依赖库**用。

---

## 三、Codex 架构调研结论

### 3.1 整体架构

Codex 是**多 crate workspace 的分层架构**，核心边界：

`protocol`（纯数据契约）→ `core`（业务逻辑）→ 外围（`tui` / `exec` / `app-server` / `mcp-server`）

- **`protocol`**（30 文件，纯 serde 类型）：所有跨进程/跨 crate 的请求、响应、事件、配置都在这里定义，无业务逻辑。整个系统的"宪法"
- **`core`** (`codex-core`)：业务逻辑；严禁 `print_stdout/stderr`，"designed to be used by the various Codex UIs"
- **`tools`** (`codex-tools`)：工具的**宿主侧模型与适配器**，刻意从 `core` 剥出来。"host-side tool machinery shared by multiple consumers"
- **`tui` / `exec` / `app-server` / `mcp-server`**：四个并列的入口，全部基于 `core`
- **`sandboxing` / `linux-sandbox` / `bwrap` / `windows-sandbox-rs` / `execpolicy`**：沙箱单独成层

### 3.2 工具接入机制（最值得借鉴）

工具体系是 **trait + registry + router** 三段式：

- **声明**：`ToolSpec` 枚举，Schema 手写而非 schemars 自动生成——刻意控制 LLM 看到的形状
- **执行契约**：`async trait ToolExecutor`，`ToolExposure` 四态：`Direct / Deferred / DirectModelOnly / Hidden`
- **注册**：`ToolRegistry { tools: HashMap<ToolName, Arc<dyn CoreToolRuntime>> }`
- **分发**：`ToolRouter` 把 LLM `ResponseItem` 转 `ToolCall`，再 dispatch
- **MCP 支持**：独立 `rmcp-client` crate + `tools/src/mcp_tool.rs` 适配 + `core/src/session/mcp.rs` 管理

### 3.3 会话与状态

不是"一个 session 对象"那么简单，Codex 把"**线程(Thread)**"作为第一公民：

- **顶层**：`ThreadManager`，负责 `NewThread / fork / resume / archive`
- **单线程内部**：`Session`（运行时状态）+ `TurnContext`（本轮上下文）+ `InputQueue`
- **持久化**：`rollout` 把整个会话写盘，可 `resume` / `fork`
- **上下文压缩**：基于 LLM 总结——把历史送给模型生成 summary，然后用 summary + 最近 N 个 user message 替换历史

### 3.4 TUI / Web / IPC 解耦（最值得抄的部分）

**5 个并列前端**：`tui`(ratatui) / `exec`(一次性 CLI) / `mcp-server` / `app-server`(RPC 后端) / `realtime-webrtc`(语音)

`app-server` 协议：**JSON-RPC 2.0**，四种传输（stdio / WebSocket / Unix Socket / off），RPC 方法按命名空间组织：

`thread/* turn/* fs/* command/* process/* skills/* plugin/* hooks/* config/* mcpServer/*`

### 3.5 多 LLM 适配（比想象中弱）

Codex 实际上是**单一形态(OpenAI Responses API) + 多家 endpoint 兼容**：

- 抽象 trait `ModelProvider` 实现只有两个：OpenAI Responses 兼容 + Bedrock
- **没有 LiteLLM 式的协议统一层**
- Anthropic 原生协议不支持

**结论**：这部分我们不抄，用 LiteLLM。

### 3.6 照抄/必须改造/不要照抄清单

#### ✅ 能照抄（高优先级）

1. **`protocol` crate 思路**：所有跨进程消息抽成纯 Pydantic 模型
2. **ToolExecutor ABC + Registry + Router 三段式**
3. **`ToolExposure`（Direct/Deferred/Hidden）+ ToolSearch**——对算法注册表是杀手锏
4. **`ThreadManager` + Thread/Turn 模型 + fork/resume**
5. **基于 LLM 的 context 压缩**
6. **JSON-RPC over WebSocket / stdio 的 app-server**

#### 🔧 必须改造

7. **Skill 机制**：用 markdown+frontmatter（Claude Code 风格），不用 Codex 的 `include_dir!` 编译期嵌入
8. **Model Provider**：用 LiteLLM 不造轮子
9. **Hooks**：做轻量版（pre_calculate / post_calculate / on_load_file）

#### ❌ 不要照抄

10. **OS 级沙箱**（seatbelt/landlock/bwrap）——CFD agent 用不到
11. **`apply_patch` + `code-mode` + `execpolicy` + `git-utils` + AGENTS.md 加载器**——纯 coding-agent 专属
12. **`agent_jobs` / `multi_agents` 复杂编排**——Phase 3 用简单 dispatch
13. **Bazel 构建 + 129 crate**——Python 项目过度工程化
14. **`realtime-webrtc`**——CFD 分析没有语音需求

---

## 四、chatcfd 现状诊断

### 4.1 现状架构

```
┌─ WebSocket/CLI ───── main.py
│                        │
│    ┌──────────────────┼──────────┐
│    │                  │          │
│  设置              MCP池初始化   内存提取
│ 持久化           (MCPClientPool) (自动)
│    │                  │          │
│    └──────────────────┼──────────┘
│                       │
│                  agent_loop.py ◄──── skills.py (系统提示)
│                 (LLM 主循环)
│                   │  │  │
│      ┌────────────┼──┼──┼─────────┐
│      │            │  │  │         │
│   memory    duplicate  工件生成   harness
│   注入       检测    _make_artifact (安全检查)
│  (自动)      (sig)    (硬编码工具名)
│      │            │  │  │         │
│      └────────────┼──┼──┼─────────┘
│                   │
│              mcp_client.py
│           (工具路由+连接)
│                   │
│         ┌─────────┴─────────┐
│         │                   │
│      SSE客户端         stdio客户端(mempalace)
│   (post_service)       (独立进程)
│
└─ session.py (会话容器：messages + 状态)
```

### 4.2 做对的事（值得保留进框架层）

| 设计 | 位置 |
|---|---|
| `MCPClientPool` 多服务器+SSE/stdio 路由 | `agent/mcp_client.py:159-252` |
| `Harness.before_call/after_call` 钩子模型 | `agent/harness.py:21-56` |
| `stream_run` 的生成器流式 + cancel 支持 | `agent/agent_loop.py:329-565` |
| `SessionPool` 无状态简约设计 | `agent/session.py:21-41` |
| 设置持久化的幂等合并处理 | `agent/main.py:63-75` |

### 4.3 CFD 耦合三大热点（最难抽离）

| Rank | 位置 | 耦合内容 |
|---|---|---|
| **1** | `agent/agent_loop.py:14-70` | `_make_artifact_title` 硬编码 calculate/exportData/loadFile/slice/clip/contour 等 12+ 处工具名/方法名 |
| **2** | `agent/agent_loop.py:73-114` + `agent/main.py:250-282` | mempalace 内存集成的 `_infer_wing`、loadFile 后自动 search、对话结束自动提取数字 |
| **3** | `agent/skills.py` 全文 234 行 | ROLE/TOOLS/RULES/SAMPLES 完全 CFD 化 |

### 4.4 其他问题

- MEMPALACE_LLM_TOOLS / CODING_TOOLS 白名单硬编码在 `mcp_client.py`
- 工件生成 + 内存注入 + 去重检测 + LLM 循环全挤在 `agent_loop.py`
- `insight_log` 的 tools_called 永远为空（`agent/insight_log.py:245`）
- 状态散落在 `AgentSession` 上，没有变更钩子

---

## 五、用户的方法论判断

**用户原话**：

> agent 系统未来的演进就是不断增加确定性的工具，以及优化提示词和 skill。

**评估**：**对一半**。这是"内容层"演进的正确方法论，但作为**框架要提供的能力**远不止这三样。

| 用户已想到 | 框架还必须提供（容易漏） | 不能漏的原因 |
|---|---|---|
| 确定性工具 | **Tool 抽象与暴露策略**（Direct/Deferred/Hidden + ToolSearch） | 工具一多 LLM context 就爆 |
| 优化提示词 | **上下文工程**（history 规范化 + LLM-based 压缩 + 工件过滤） | 多轮聊久必爆 context |
| 优化 skill | **会话/线程模型**（Thread + Turn + fork/resume） | 没这个无法支持"中途开 case B 比较"场景 |
| — | **可观测性**（trace + insight log + tool 耗时/结果） | 没日志根本不知道改的 prompt 是好是坏 |
| — | **IPC/传输层抽象**（WebSocket / stdio / CLI / 嵌入） | 上层应用形态多样 |
| — | **Harness/Safety 钩子点** | 不同项目的边界规则不同 |
| — | **LLM client 抽象 + 错误/重试/超时** | LLM 不稳定 |
| — | **Plugin 接入约定** | 上层应用接入框架的"插座" |

**一句话**：用户的思路是"内容层"演进的对的方法论，但框架的价值在"骨架层"——给一个稳定的地方去演进那些内容。

---

## 六、agentkit 目录结构

```
agentkit/                              # ← 独立 git 仓库，pip 包
├── pyproject.toml                     # pip install agentkit
├── README.md
├── doc/
│   ├── design.md                      # 本文档
│   ├── tool_authoring.md              # 上层项目怎么写工具（待写）
│   └── plugin_authoring.md            # 上层项目怎么写插件（待写）
│
├── src/agentkit/
│   ├── protocol/                      # 纯 Pydantic 契约层（最稳定）
│   │   ├── messages.py                # WS/RPC 消息
│   │   ├── tool_spec.py               # ToolSpec + ToolExposure
│   │   ├── events.py                  # 工件/流事件
│   │   └── errors.py                  # 错误类型
│   │
│   ├── tools/                         # 工具抽象（不依赖任何来源）
│   │   ├── executor.py                # ABC: ToolExecutor.spec() + handle()
│   │   ├── registry.py                # ToolRegistry
│   │   ├── router.py                  # ToolRouter
│   │   ├── exposure.py                # Direct/Deferred/Hidden + ToolSearch
│   │   ├── spec.py                    # ToolSpec
│   │   └── builtin/                   # 框架内置通用工具（可选，如 think/sleep）
│   │
│   ├── mcp/                           # MCP 子系统（独立模块）
│   │   ├── client.py                  # 基于官方 mcp SDK 包一层
│   │   ├── pool.py                    # 多 server 连接池（SSE + stdio）
│   │   ├── adapter.py                 # MCP Tool schema → ToolSpec
│   │   ├── proxy_executor.py          # MCPProxyExecutor
│   │   ├── manager.py                 # 生命周期（连接/断开/重连/健康检查）
│   │   └── server_helper.py           # 可选：帮上层项目包装成 MCP server
│   │
│   ├── session/                       # 会话/线程
│   │   ├── thread.py                  # Thread (fork/resume/archive)
│   │   ├── turn.py                    # TurnContext
│   │   ├── pool.py                    # ThreadPool
│   │   └── compact.py                 # LLM-based 上下文压缩
│   │
│   ├── llm/                           # LLM 客户端
│   │   ├── client.py                  # LiteLLM 封装 + 重试/超时
│   │   └── stream.py                  # 流式抽象
│   │
│   ├── harness/                       # 安全/边界
│   │   ├── base.py                    # 默认实现
│   │   └── hooks.py                   # before_call/after_call 钩子
│   │
│   ├── skills/                        # Skill 加载
│   │   └── loader.py                  # frontmatter+md（Claude Code 风格）
│   │
│   ├── ipc/                           # 传输层
│   │   ├── websocket.py
│   │   ├── stdio_rpc.py
│   │   ├── cli.py
│   │   └── methods.py                 # thread/* turn/* skills/* 命名空间
│   │
│   ├── observability/                 # 可观测性
│   │   ├── insight_log.py             # 结构化 JSONL
│   │   ├── trace.py                   # tool call 耗时/结果
│   │   └── metrics.py
│   │
│   ├── plugin/                        # 上层项目接入点（关键）
│   │   ├── app.py                     # App 类，组装一切
│   │   ├── prompt_builder.py          # ABC
│   │   ├── artifact_factory.py        # ABC
│   │   ├── context_hooks.py           # ABC
│   │   └── tool_set.py                # ABC
│   │
│   └── runtime/                       # 运行时入口
│       └── server.py                  # uvicorn 启动
│
├── tests/
└── examples/
    ├── hello_agent/                   # 最小 demo：1 个 echo 工具
    └── todo_agent/                    # 中等 demo：内存型 todo agent
```

### 上层项目接入示例（设想 chatcfd 用法）

```python
# chatcfd/agent_main.py（业务侧只需几十行）
from agentkit import App
from chatcfd.plugins import CFDPromptBuilder, CFDArtifactFactory, CFDMemoryHook
from chatcfd.plugins.tools import CFD_TOOLSET

App(
    prompt_builder=CFDPromptBuilder(),
    artifact_factory=CFDArtifactFactory(),
    context_hooks=[CFDMemoryHook()],
    tools=CFD_TOOLSET,
    mcp_servers=["http://localhost:8000/sse"],
).run(host="0.0.0.0", port=8765)
```

---

## 七、三类"工具"的归属

**核心纪律**：业务工具永远不进 agentkit。

| 类别 | 在哪写 | 例子 | 谁拥有 |
|---|---|---|---|
| **A. 框架抽象层** | `agentkit/tools/` | `ToolExecutor` ABC、`ToolRegistry`、`ToolRouter` | agentkit |
| **B. 远程工具源接入** | `agentkit/mcp/` | MCP client、连接池、schema→ToolSpec 适配器 | agentkit |
| **C. 业务工具的具体实现** | **上层项目仓库** | `calculate` / `loadFile`（CFD）<br>`build_graph` / `query_node`（SimGraph） | chatcfd / simgraph |

### 为什么 MCP 独立成顶层 `agentkit/mcp/`，不放 `agentkit/tools/mcp/`

1. MCP 不只暴露 Tools，还有 Resources / Prompts，未来可能用到
2. MCP 是**协议层**，和 IPC、LLM 同级，不是 tools 的子类
3. 避免 tools/ 模块越来越胖（未来还可能有 openapi/ / grpc/ 连接器）

### 本地 Python 工具（不走 MCP）的两种姿势

**姿势 1：继承 ToolExecutor 直接写**
```python
from agentkit.tools import ToolExecutor

class SomeLocalTool(ToolExecutor):
    name = "do_something"
    spec = ...
    async def handle(self, args): ...
```

**姿势 2：装饰器糖**
```python
from agentkit.tools import tool

@tool(name="do_something", description="...")
async def do_something(arg1: str, arg2: int) -> dict:
    ...
```

---

## 八、可视化全景（6 张图）

### 图 1：整体生态 —— agentkit 和上层应用的关系

```
                ┌─────────────────────────────────────────────────┐
                │              agentkit  (通用框架)                │
                │          d:\Git\Personal\agentKit               │
                │                                                 │
                │  protocol / tools / mcp / session / llm /       │
                │  harness / skills / ipc / observability / plugin│
                └─────────────────────┬───────────────────────────┘
                                      │ pip install agentkit
                ┌─────────────────────┼─────────────────────┐
                ▼                     ▼                     ▼
        ┌───────────────┐    ┌───────────────┐    ┌───────────────┐
        │    chatcfd    │    │   simgraph    │    │   其他 agent   │
        │  (CFD 数据分析) │    │   (图分析)    │    │  (未来项目)    │
        │               │    │               │    │               │
        │  ▸ 业务 prompt │    │  ▸ 业务 prompt │    │  ▸ 业务 prompt │
        │  ▸ 业务工具    │    │  ▸ 业务工具    │    │  ▸ 业务工具    │
        │  ▸ Plugin 实现 │    │  ▸ Plugin 实现 │    │  ▸ Plugin 实现 │
        └───────────────┘    └───────────────┘    └───────────────┘
```

### 图 2：agentkit 内部分层

```
┌─────────────────────────────────────────────────────────────────┐
│  ipc/        【对外传输层】                                       │
│  WebSocket  │  stdio JSON-RPC  │  HTTP SSE  │  CLI               │
└──────────────────────────┬──────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  plugin/     【上层接入点 ── 业务项目通过这层接进来】              │
│  App  │  PromptBuilder  │  ArtifactFactory  │  ContextHook       │
└──────────────────────────┬──────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  session/    【对话编排核心】                                     │
│  Thread (fork/resume) │ Turn │ Pool │ Compact (LLM 压缩)         │
└──────┬────────────┬──────────────┬──────────────────────────────┘
       │            │              │
       ▼            ▼              ▼
  ┌─────────┐  ┌────────┐  ┌──────────┐
  │ tools/  │  │  llm/  │  │ harness/ │
  │  工具    │  │ LLM 端  │  │ 安全边界 │
  │ Executor│  │ LiteLLM│  │ 白名单   │
  │ Registry│  │ 重试   │  │ hook 钩子│
  │ Router  │  │ 流式   │  │          │
  │ Exposure│  └────────┘  └──────────┘
  └────┬────┘
       │ 通过 adapter 拉远程工具
       ▼
  ┌──────────┐
  │   mcp/   │   ─────►  外部 MCP server (post_service / mempalace)
  │ Client   │
  │ Pool     │
  │ Adapter  │
  │ Proxy    │
  └──────────┘

  ─── 横向支撑层 (被所有模块使用) ───
  ┌──────────┐  ┌──────────┐  ┌────────────────┐
  │ protocol/│  │  skills/ │  │ observability/ │
  │ 纯契约   │  │ md+frontm│  │ trace / log    │
  │ Pydantic │  │  loader  │  │ JSONL          │
  └──────────┘  └──────────┘  └────────────────┘
```

### 图 3：三类"工具"的归属

```
╔═══════════════════════════════════════════════════════════════════╗
║  类别 A：框架抽象层                       位置: agentkit/tools/     ║
║  ──────────────────────────────                                   ║
║  ToolExecutor(ABC)  ToolRegistry  ToolRouter  ToolSpec            ║
║  Exposure(Direct / Deferred / Hidden) + ToolSearch                ║
║                                                                   ║
║  ⓘ 通用契约，与业务无关                                            ║
╚═══════════════════════════════════════════════════════════════════╝
                              ▲
                              │ 使用
                              │
╔═══════════════════════════════════════════════════════════════════╗
║  类别 B：远程工具源接入                   位置: agentkit/mcp/       ║
║  ──────────────────────────────                                   ║
║  MCPClient (SSE / stdio)     MCPPool         MCPManager           ║
║  MCPAdapter (schema→ToolSpec)  MCPProxyExecutor                   ║
║                                                                   ║
║  ⓘ 把外部 MCP server 的工具桥接进 agentkit                          ║
╚═══════════════════════════════════════════════════════════════════╝
                              ▲
                              │ 抓 schema / 转发调用
                              │
╔═══════════════════════════════════════════════════════════════════╗
║  类别 C：业务工具的具体实现               位置: 上层项目仓库         ║
║  ──────────────────────────────                                   ║
║                                                                   ║
║  chatcfd/post_service/mcp_tools/                                  ║
║    ├── calculate.py     loadFile.py     exportData.py            ║
║    └── listFiles.py     getMethodTemplate.py     compare.py      ║
║                                                                   ║
║  simgraph/your_mcp_server/                                       ║
║    ├── build_graph.py   query_node.py   ...                      ║
║                                                                   ║
║  ⓘ 业务逻辑，永远不进 agentkit                                      ║
╚═══════════════════════════════════════════════════════════════════╝
```

### 图 4：工具流转完整链路（启动期 + 运行期）

```
┌─ 启动期 (一次性) ─────────────────────────────────────────────────┐
│                                                                  │
│   ① post_service 启动        ② chatcfd 进程启动                   │
│       (业务侧)                     │                              │
│       │                            │ App(mcp_servers=[...])      │
│       │ FastMCP 暴露                │                              │
│       │ calculate/loadFile/...     ▼                              │
│       │                       ③ agentkit/mcp/pool.py 连接          │
│       ▼                            │                              │
│   localhost:8000/sse  ◄─────────── ④ 抓取 MCP tools/list           │
│                                    │                              │
│                                    ▼                              │
│                              ⑤ agentkit/mcp/adapter.py             │
│                                    │ schema → ToolSpec            │
│                                    ▼                              │
│                              ⑥ MCPProxyExecutor 包装               │
│                                    │                              │
│                                    ▼                              │
│                              ⑦ tools/registry.py 注册              │
│                                  Direct  → 常驻 prompt             │
│                                  Deferred → ToolSearch 按需        │
│                                  Hidden  → 内部专用                │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘

┌─ 运行期 (每次调用) ───────────────────────────────────────────────┐
│                                                                  │
│   用户消息: "分析这个 CGNS 文件"                                   │
│       │                                                          │
│       ▼                                                          │
│   ipc/ws → session/Thread.append_user_msg                        │
│       │                                                          │
│       ▼                                                          │
│   llm/client.invoke(history + tool_specs)                        │
│       │                                                          │
│       │ LLM 返回 tool_call: loadFile(path="...")                  │
│       ▼                                                          │
│   harness.before_call() ── 检查路径白名单                          │
│       │ ✓                                                        │
│       ▼                                                          │
│   tools/router.dispatch("loadFile")                              │
│       │                                                          │
│       ▼                                                          │
│   MCPProxyExecutor.handle()                                      │
│       │ MCP 协议转发                                              │
│       ▼                                                          │
│   post_service/engine.load_file()  ── 真实计算                    │
│       │ 返回 {summary, data, output_files}                       │
│       ▼                                                          │
│   harness.after_call() ── 检查结果大小                            │
│       │                                                          │
│       ▼                                                          │
│   observability/log ── 记录 tool 耗时/结果                        │
│       │                                                          │
│       ▼                                                          │
│   ArtifactFactory.make_artifact()  ── 上层 plugin 生成工件         │
│       │                                                          │
│       ▼                                                          │
│   stream → ipc/ws → 浏览器渲染                                    │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### 图 5：一次完整请求的时序

```
浏览器     ipc/ws    Thread     llm    Router    Harness    MCPProxy  post_service
  │          │        │         │       │         │          │           │
  │ 用户消息  │        │         │       │         │          │           │
  ├─────────►│        │         │       │         │          │           │
  │          ├───────►│ append  │       │         │          │           │
  │          │        ├────────►│ invoke│         │          │           │
  │          │        │         │       │         │          │           │
  │          │        │         │ tool_call: loadFile                    │
  │          │        │◄────────┤       │         │          │           │
  │          │        ├─────────────────►│ dispatch│          │           │
  │          │        │         │       ├────────►│ before   │           │
  │          │        │         │       │         │ ✓        │           │
  │          │        │         │       │         ├─────────►│ handle    │
  │          │        │         │       │         │          ├──────────►│
  │          │        │         │       │         │          │          load_file
  │          │        │         │       │         │          │◄──────────┤
  │          │        │         │       │         │◄─────────┤           │
  │          │        │         │       │ after ✓ │          │           │
  │          │        │         │       │         │          │           │
  │          │        │ append tool_msg │         │          │           │
  │          │        ├────────►│ invoke│         │          │           │
  │          │        │         │       │         │          │           │
  │          │        │◄────────┤ "已加载 N 个 zone..."                   │
  │          │◄───────┤ stream  │       │         │          │           │
  │◄─────────┤        │         │       │         │          │           │
  │ 渲染气泡  │        │         │       │         │          │           │
  │ + 工件   │        │         │       │         │          │           │
```

### 图 6：4 + 1 个里程碑路线

```
你在这里 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━►
   ↓
┌────────┐    ┌────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│  M0    │    │     M1     │    │      M2      │    │      M3      │    │      M4      │
│ Spike  │───►│  核心骨架   │───►│  迁 chatcfd  │───►│Thread+Compact│───►│SimGraph验证  │
│ 1-2 天 │    │   1 周     │    │    1 周      │    │   4-5 天     │    │    1 周      │
└────────┘    └────────────┘    └──────────────┘    └──────────────┘    └──────────────┘
   │              │                   │                   │                   │
   │              │                   │                   │                   │
   ▼              ▼                   ▼                   ▼                   ▼
echo 工具      protocol            chatcfd 业务         长对话能跑          抽象被
跑通骨架      tools                零损失运行           fork/resume        真实第二
              llm                  在新框架上                              项目检验
              harness
              observability
              plugin
              mcp
              ipc(WS)
              skills
              ↑                                                            ↑
        可被业务项目 import                                          "通用框架"的自证
```

---

## 九、落地路线图

| Milestone | 目标 | 工期 | 输出 |
|---|---|---|---|
| **M0：spike** | 全新空仓库，用 1 个 echo 工具 + 1 个 dummy plugin 跑通 protocol→tools→executor→ws 全链路 | 1-2 天 | 100 行能跑的 demo，**先验证抽象设计** |
| **M1：核心骨架** | 完成 protocol / tools / llm / harness / observability / plugin / mcp / ipc(WS) / skills 模块 | 1 周 | 可被业务项目 import 使用 |
| **M2：迁 chatcfd** | 把 chatcfd 现有 6 工具 + skills.py + artifact 改造成 plugin 接入 | 1 周 | chatcfd 业务零损失运行在新框架上 |
| **M3：Thread + Compact** | 加 session 高级特性（fork/resume + LLM 压缩） | 4-5 天 | 长对话能跑 |
| **M4：第二项目验证** | SimGraph 或一个最小 demo 接入，**用真实第二项目验证抽象** | 1 周 | 抽象通过实战检验 |

### 关键纪律

1. **第一个项目接入之前，不要急着抽抽象**
2. **第二个项目接入之前，不要急着发版**
3. **框架最大的坑是"只服务一个项目时自以为通用"**
4. **业务工具永远不进 agentkit**

---

## 十、一句话总览

```
   agentkit  =  "骨架"  =  protocol + tools + mcp + session + llm
                          + harness + skills + ipc + observability + plugin

   上层项目  =  "肌肉"  =  业务工具(MCP server)  +  Plugin 实现
                          (prompt + artifact + hook)

   迭代方法  =  "演进"  =  增加确定性工具 + 优化 skill/prompt + 完善 plugin
                          (用户的方法论)，但只有骨架稳定，肌肉才能持续生长
```

---

## 十一、待讨论的设计问题

按优先级排序。**P0 不先想清，后面全要返工**。

### 🔴 P0：决定整个框架形态的根问题

| # | 问题 | 影响 |
|---|---|---|
| **1a** | **本地 Python 工具怎么写**：继承 ABC vs 装饰器？sync vs async？参数 schema 怎么声明（Pydantic 模型 / JSON schema dict / type hints 反射）？返回值是 dict 还是 ToolResult 类？ | 决定上层项目写一个工具有多痛/多爽。**最关键的一个 API** |
| **1b** | **MCP 工具怎么自动接入**：MCPProxyExecutor 如何处理 schema 不匹配 / 错误传递 / 流式响应 / 长连接重连？MCP 的 Resources/Prompts 怎么暴露？ | 决定 MCP 集成的稳定性 |
| **2** | **Plugin 注入模型**：`App(plugins=[...]).run()` vs 装饰器注册 vs 依赖注入容器（FastAPI Depends 风格）？怎么让 plugin 拿到框架核心对象（thread、tool registry）？ | 决定上层应用接入框架的姿势 |
| **3** | **Session/Thread 的存储后端**：内存（重启丢失）/ SQLite（本地单机）/ Redis（多副本）？接口设计 vs 后端可插拔？fork/resume 是深拷贝消息还是引用+COW？ | 决定能否多人/分布式部署，及恢复语义 |

### 🟡 P1：影响开发体验和长期可演进性

| # | 问题 | 影响 |
|---|---|---|
| **4** | **Skill 的触发模型**：Codex 风格（ToolSearch 按需载入）/ Claude Code 风格（all-in-prompt）/ 混合？ | 决定 LLM context 占用 vs 响应速度的权衡 |
| **5** | **工具暴露策略落实**：ToolSearch 自己写还是用 LLM function-call 模拟？deferred 工具的 schema 怎么 lazy load？ | 决定工具规模能扩展到多少 |
| **6** | **上下文压缩什么时候触发**：token 阈值 / 轮数 / 显式命令？压缩粒度（整段一压 / 工件级别保留 / tool result 替换为 summary）？ | 决定长对话能撑多久，省钱与否 |
| **7** | **可观测性日志结构**：JSONL（简单）/ SQLite（可查询）/ OTLP（标准但重）？trace 维度（thread → turn → tool_call → llm_call 四级）？ | 决定将来 debug 提示词、看 token 花费、找耗时瓶颈 |

### 🟢 P2：可以晚一点定的

| # | 问题 | 影响 |
|---|---|---|
| **8** | **IPC 层先做哪几种传输**：WebSocket（chatcfd 已有）/ stdio JSON-RPC（CLI/bridge）/ HTTP SSE（更通用）？要不要复刻 codex 的 `thread/* turn/* skills/*` 命名空间？ | 决定第二个项目能否复用 |
| **9** | **Harness 的扩展点放哪**：全局规则 / 工具级规则 / plugin 注入规则？路径白名单怎么由上层项目声明？危险命令名单怎么合并？ | 决定上层项目能否定制边界 |
| **10** | **LLM 中断/工具失败的恢复语义**：工具 timeout 是 retry / 报错给用户 / 让 LLM 自己看到错误重试？LLM 流中断后 thread 状态是什么？ | 决定容错强度 |
| **11** | **多 Agent 编排怎么留口子**：Phase 3 的对比/Coding/报告子 agent，框架要不要内建编排原语，还是只暴露"在 tool handler 里 spawn 新 thread"的能力？ | 决定将来子 agent 设计灵活度 |

### 建议讨论顺序

**先 #1a → #1b → #2 → #4**（这四个互相影响最大，定下来其他就好谈）

→ 然后 #3

→ 再 #5 #6

→ 剩下的 P2 边做边定

---

## 附录 A：参考资料

- openai/codex 仓库：https://github.com/openai/codex
- 本文档相关的 chatcfd 文件：
  - `chatcfd/CLAUDE.md` — 项目总览
  - `chatcfd/agent/agent_loop.py:14-137` — 当前 LLM 循环 + 工件 + 内存
  - `chatcfd/agent/skills.py` — CFD 化的 prompt
  - `chatcfd/agent/mcp_client.py:159-252` — MCPClientPool（值得保留）
  - `chatcfd/agent/harness.py:21-56` — Harness 钩子模型（值得保留）
  - `chatcfd/post_service/algorithm_registry.py` — 对照 codex `tools/registry`

## 附录 B：术语表

| 术语 | 含义 |
|---|---|
| **Thread** | 一次完整的会话，可 fork/resume/archive，类似 git branch |
| **Turn** | Thread 内的一轮（user msg → LLM → tools → assistant msg） |
| **ToolSpec** | LLM 看到的工具描述（name/description/parameters schema） |
| **ToolExecutor** | 工具的执行端，ABC，业务项目实现 |
| **ToolExposure** | 工具对 LLM 的可见度：Direct(常驻)/Deferred(按需)/Hidden(内部) |
| **MCP** | Model Context Protocol，工具/资源/提示的远程协议 |
| **Plugin** | 上层项目接入 agentkit 的方式，包含 PromptBuilder/ArtifactFactory/ContextHook |
| **Compact** | 基于 LLM 的对话历史压缩 |
| **Harness** | 框架的硬约束层（路径白名单/资源限制/before-after 钩子） |
