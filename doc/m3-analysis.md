# M3 复盘 — Thread + Compact + IPC 升级

> 状态：✅ 已完成
> 关键产出：`session/compact.py`（LLM-based 压缩）+ WebSocket 路由（thread_id/fork/open/cancel）+ 7 个新测试

---

## 1. 改了什么

### 1.1 session/compact.py（新）— LLM-based 上下文压缩

```python
Compactor(llm, CompactConfig(target_tokens=8000, keep_recent_turns=6))
```

每次 turn 开始先调 `maybe_compact(thread)`：
- 估算 token < target → 不动
- 估算 token ≥ target 且历史够长 → 取 head 段，喂给 LLM 让它写 ~150 字摘要，原 head 替换成一条 `SystemMessage([Earlier conversation summary]...)`
- 系统提示和最近 6 轮原样保留

**摘要 prompt 是常量**：`SUMMARY_PROMPT`——可被 host 覆盖（子类化 Compactor 重写 `_summarize`）。

### 1.2 App 集成

```python
App(compactor=Compactor(llm))   # 可选；不传就不压缩
```

Compactor 不是必需依赖——hello_agent 不传，chatcfd 传。

### 1.3 turn cancellation

App 现在跟踪 `_turns: dict[thread_id, TurnContext]`。`cancel_turn(thread_id)` 触发该 turn 的 `cancel_event`，每个 tool call 前会检查并提前退出。

### 1.4 WebSocket 协议升级

| 客户端发 | 行为 |
|---|---|
| `{type: user_message, content, thread_id?}` | 在指定 thread 发 turn；turn 在后台 task 跑，主 loop 继续收消息 |
| `{type: cancel, thread_id}` | 触发该 thread 的 cancel；回 `cancel_ack` |
| `{type: fork, thread_id}` | 深拷贝该 thread，回新的 `thread_started` |
| `{type: open, thread_id}` | resume 已有 thread |

**关键架构变更**：turn 不再阻塞 receive loop。`asyncio.create_task(run_turn(...))` + `send_lock` 保证：
- 服务器在 turn 跑的同时仍能收 `cancel`
- 两个消息不会同时写 WebSocket（lock）
- 客户端断连时主动 cancel 后台 task

### 1.5 ThreadPool 加 `register()` 方法

`fork()` 出来的新 thread 要进 pool。之前 IPC 层 reach 进 `_threads` 私有 dict，丑。加 `register(thread)` 一句话搞定。

---

## 2. 关键设计决定的合理性审查

### 2.1 Compactor 是「带 LLM 的算法对象」，不是 Thread 的方法

**做法**：`Compactor(llm).maybe_compact(thread)` 而不是 `thread.compact(llm)`。

**为什么合理**：
- Thread 是数据，不该知道 LLM 存在
- 多种压缩策略（LLM 摘要 / 滑窗 / 抽取式）都能实现同样接口
- 测试时不传 Compactor，Thread 行为完全确定

**疑点**：算 token 用 `chars // 4` 太粗。**对**——但接口接受 `chars_per_token`，host 想用 tiktoken 就传。先不引入 tokenizer 依赖。

### 2.2 摘要只保留 head 段 + 最后 N 轮

**做法**：取 `boundaries[-keep_recent_turns]` 作为分界点，前面压成一条 SystemMessage。

**为什么合理**：
- LLM 在工具循环里最依赖"最近发生了什么"——保留原话
- 早期决策（"用户选了案例 A"、"已确认坐标系"）值得留摘要
- 一条 SystemMessage 让 LLM 不会误以为是上一轮的对话

**疑点**：
- ToolMessage 跨边界时不强保对应 ToolCall——只切在 UserMessage 边界。这是对的：tool round 内部不能切（不然 LLM 看到孤儿 tool_result 会 confuse）。
- 没有反压缩（用户问"你之前说什么"答不出）。**M4 之后看真用例再补取证查询能力**。

### 2.3 IPC 后台 task + lock

**做法**：
```python
active_task = asyncio.create_task(run_turn(...))
send_lock = asyncio.Lock()  # protect ws.send_text
```

**为什么合理**：
- WebSocket 是双工但 send/receive 各一个流。要支持「turn 跑期间用户能 cancel」必须把 receive 不阻塞
- `asyncio.Lock` 是最小够用的并发原语——不引 Queue/StreamReader 增复杂度
- 只允许一个 turn 在跑（第二条 `user_message` 直接报错 "turn already in progress"）：UX 上单线程更可控；想并发就 fork

**疑点**：客户端断连时 cancel 后台 task——但没等它完。这是对的：上层 finally 会跑 `await self.shutdown()` 给资源；turn 本身是无副作用观测者（除了 tool 已经 dispatch 的副作用，那是 tool 自己的事）。

### 2.4 「带状态的 fork」用深拷贝

**做法**：`Thread.fork()` 深拷贝 messages 和 metadata。

**为什么合理**：
- 用户原话："想从消息 17 开 case B 比较"——典型场景就是 try 一个反事实
- 引用语义 + COW 听起来省内存，但 messages 是 Pydantic 不可变模型，每次 append 已经是新对象——深拷贝实际成本主要在 metadata
- chatcfd 实际 metadata 就 `{"cfd_state": CFDState(...)}` 几十字节

**疑点**：fork 完了原 thread 的 active TurnContext 没复制——这是对的，fork 出来的新 thread 没有正在跑的 turn。

### 2.5 Compactor 不在 turn 中间触发，只在 turn 开始

**做法**：`maybe_compact()` 在 `set_system` 和 `add_user` 后、tool round loop 之前。

**为什么合理**：
- tool round 中间压缩会让 LLM 看到 history 突变，可能导致它重复刚做的事
- 用户 message 已 append，所以压缩看到的是"完整一轮即将开始"的状态
- 压缩本身要花一次 LLM call——放在 turn 开始 amortize 在长对话里

**疑点**：如果用户连发 50 条短消息也不会触发压缩。**对**——target_tokens 才是真触发条件，不是消息数。

### 2.6 SUMMARY_PROMPT 是模块级常量

**做法**：定义为 module-level 字符串，子类 Compactor 时不替换它而是覆盖 `_summarize()`。

**为什么合理**：
- 一般 host 不需要改
- 真要改的 host 通常想换整个流程（比如先抽事实再摘要），所以 override 方法比 override 字符串更灵活
- 不引入"模板字符串 + 变量替换"的复杂度

---

## 3. 测试覆盖

| 文件 | 数量 | 关键测试 |
|---|---|---|
| `tests/test_smoke.py` (M1) | 7 | 框架基础 |
| `tests/test_m3.py` (新) | 7 | compactor 触发/不触发 + IPC fork/open/cancel/未知 thread |
| `examples/chatcfd_plugin/test_plugin.py` (M2) | 9 | 插件 + 框架集成 |
| **总计** | **23** | 全绿 |

最关键的两个：
- `test_compactor_compresses_when_over_target` — 用 FakeLLM 不需 key 也能跑
- `test_websocket_fork_creates_independent_thread` — 端到端验证 IPC fork

---

## 4. 框架代码量审计

```
src/agentkit/  33 个 .py 文件  ~1350 行
```

M3 净增 ~180 行（compact.py 130 + IPC 升级 50）。
**净增模块 1 个**：`session/compact.py`。其他全是补全。

---

## 5. 还剩什么没做

| # | 待办 | 触发条件 |
|---|---|---|
| 1 | tokenizer 精确算 token（替代 chars/4） | 摘要触发不准时 |
| 2 | Compactor 持久化"被压缩的原文"（如果想 audit） | 用户问"以前说啥"时 |
| 3 | retry 按错误类型分类 | 真量 + 真 LLM provider 之后 |
| 4 | MCP 自动重连 | post_service 真断时 |
| 5 | Thread 持久化（SQLite Pool） | 用户要求 resume 跨重启 |

---

## 6. 一句话总结

**M3 给框架补上了"长对话能跑"和"会话能管理"两块核心能力，都用最小手段完成：Compactor 是独立 130 行可被 FakeLLM 测试的小算法，IPC 加 4 个消息类型 + 一个 lock 就支持了 cancel/fork/open。框架还是 33 个文件 1350 行，没膨胀。下一步 M4 上 SimGraph 验证抽象。**
