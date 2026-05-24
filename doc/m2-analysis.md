# M2 复盘 — chatcfd 上船 + 框架打磨

> 状态：✅ 已完成
> 关键产出：`examples/chatcfd_plugin/`（6 工具 + Prompt/Artifact/Memory/Harness 全套插件）+ 框架小修

---

## 1. 这一版改了什么

### 1.1 框架小修（按 M1 复盘的遗留单）

| # | 项目 | 改动 | 触发原因 |
|---|---|---|---|
| 1 | LLM 流式接进 turn() | `LLMClient.complete_streaming(on_delta)` + `App(stream_llm=True)` 默认开启 | chatcfd 响应感慢，先用户先看到字 |
| 2 | `MAX_TOOL_ROUNDS` 变 App 参数 | `App(max_tool_rounds=10, tool_result_preview=2000)` | 顺手事 |
| 3 | 二进制返回 | `BINARY_KEYS = ("data","mesh","blob","bytes")` 约定；`_strip_binary` 把 LLM 视图清空，ArtifactFactory 看完整 payload | `loadFile` 真返 mesh blob 必触发 |

**核心设计决定**：二进制走「约定优于配置」。tool 返 `{"summary": "...", "data": <blob>}`，框架自动剥；不需要 tool 声明 "I return binary"，也不需要框架引入新的 `ToolResultKind` 枚举。**这条约定写进了 `app.py` 的 docstring，是框架与 host 之间的契约**。

### 1.2 chatcfd_plugin 交付物

```
examples/chatcfd_plugin/
├── README.md                        迁移路径表（mock → 真 MCP）
├── main.py                          21 行装配
├── test_plugin.py                   9 测试，无 LLM key
└── chatcfd_plugin/
    ├── __init__.py                  公开 6 个名字
    ├── tools.py                     6 个 @tool（mock 算 + 真 wire shape）
    ├── prompt_builder.py            CFDPromptBuilder + CFDState
    ├── artifact_factory.py          mesh / table / file 三种工件
    ├── hooks.py                     CFDMemoryHook + cfd_harness_hook（路径白名单）
    └── skills/
        ├── cfd-loadfile.md
        └── cfd-units.md
```

**chatcfd 业务知识在 plugin 内部完全可见**：
- `CFD_ROLE` 字符串只在 `prompt_builder.py`
- `DEMO_CASES` 只在 `tools.py`
- 路径白名单只在 `hooks.py`

**agentkit 源代码里 grep "cfd"**：依然零命中。✅

---

## 2. 关键设计决定的合理性审查

### 2.1 流式实现：队列 + 后台 task

**做法**：
```python
delta_queue = asyncio.Queue()
async def _on_delta(text): await delta_queue.put(text)
llm_task = asyncio.create_task(self.llm.complete_streaming(..., _on_delta, ...))
while text := await delta_queue.get(): yield AssistantTextEvent(delta=text)
```

**为什么这样**：`complete_streaming` 接受回调而非返迭代器——回调能在内部把 tool_call 分片拼起来；外面 App.turn() 需要 yield。两者通过 queue 桥接。

**疑点**：
- 用 `Queue` 而不是 `anyio.create_memory_object_stream` 是因为 stdlib 够用，不引入新依赖。
- `complete_streaming` 内部用 `hasattr(ret, "__await__")` 判断回调是否 async——稍微脏但避免要求所有回调都 async。**接受**。

### 2.2 二进制约定：`{"summary": str, "data": <blob>}`

**做法**：把"有 summary 字段"当作"这是结构化结果"的信号；剥掉 BINARY_KEYS 里的字段，留下 metadata。

**为什么合理**：
- 跟 chatcfd 现有 PRD 的统一返回格式（`{type, summary, data, output_files}`）天然对齐
- 不需要工具显式声明 "我返回 binary"
- 不影响普通返回 `{"text": "hi"}`（没 `summary` 字段就原样走）

**疑点**：
- 一个 tool 如果意外返了顶层 `summary` 但里面 `data` 是普通字典，会被错误地剥。**用例：`{"summary": "x", "data": {"rows": [...]}}`**——目前会把 rows 替换成 `{_stripped, kind, approx_size}`。
- **决定：可以接受**。理由：约定是「想被剥的 tool 才声明 summary」；不声明 summary 的 tool 即便有 data 字段也不剥。文档里要写清。**已写**。

### 2.3 PromptBuilder 拿 thread 不拿 user_message

**做法**：`PromptBuilder.build(thread) -> str`，不传当前 user_message。

**为什么合理**：
- 系统 prompt 是 thread 级的（同一会话内不应每轮都重算太多）
- 业务方需要 user_message 就读 `thread.messages[-1]`

**疑点**：每轮都调 `build()` 重新拼，无缓存。**chatcfd 主要拼字符串，量不大；M3 加 Compact 时统一加缓存层**。

### 2.4 CFDState 走 thread.metadata 而不是单独参数

**做法**：`thread.metadata["cfd_state"] = CFDState(...)`，业务自己管。

**为什么合理**：框架不知道也不该知道有 active_case 这回事。`metadata` 是给业务用的纯 dict。多个插件同时用同一个 thread 时按 key 各占各的。**理想的扩展点**。

### 2.5 cfd_harness_hook 用函数 + make_hook

**做法**：
```python
async def _whitelist(call): ...
cfd_harness_hook = make_hook(before=_whitelist)
```

**为什么不是 class**：路径白名单是无状态的——构造一个 class 实例没意义。`make_hook` 函数式糖适合这种纯函数 hook。

**疑点**：如果未来要支持「白名单可热更新」，就要换 class 装 state。**到时再换，今天不预测**。

### 2.6 真 chatcfd 迁移路径

README 里列了一张表，所有"换 mock 为真"的位置都在 plugin 内部：
- `CFD_TOOLS = [...]` → `App(mcp_servers=["http://localhost:8000/sse"])`
- `CFDArtifactFactory.make()` 里换计算 mesh URL 的逻辑
- `CFDMemoryHook` 加 mempalace 调用

**这就是"框架稳、肌肉变"的最直接证据**：mock→真的迁移完全不触碰 agentkit 源码。

---

## 3. 测试覆盖

| 套件 | 数量 | 范围 |
|---|---|---|
| `tests/test_smoke.py`（agentkit） | 7 | 框架内部 |
| `examples/chatcfd_plugin/test_plugin.py` | 9 | 插件 + 框架集成（不依赖 LLM） |
| **总计** | **16** | 全绿 |

特别值得记的两个测试：
- `test_loadfile_strips_mesh_for_llm` — 证明二进制剥离按预期工作
- `test_harness_rejects_path_outside_case_root` — 证明 host 能成功用 Harness 加业务规则

---

## 4. 与 M1 复盘的对账

| M1 标记的待办 | M2 状态 |
|---|---|
| (1) LLM 流式 | ✅ 已做 |
| (2) MAX_TOOL_ROUNDS 变参数 | ✅ 已做 |
| (3) Router 二进制返回 | ✅ 用 BINARY_KEYS 约定做 |
| (4) WebSocket thread_id + cancel | ⏳ M3 |
| (5) Compact | ⏳ M3 |
| (6) retry 按错误分类 | ⏳ 真量后再说 |
| (7) Message Union discriminator | ⏳ snapshot 反序列化时 |
| (8) MCP 自动重连 | ⏳ 真出问题时 |

---

## 5. 框架代码量审计

```
src/agentkit/  31 个 .py 文件
              ~1200 行（包括 docstring）
```

M2 净增 ~60 行（complete_streaming + _strip_binary + max_tool_rounds 参数化）。**没新增模块**。

---

## 6. 一句话总结

**M2 用一个真业务案例（chatcfd 6 工具 + skill + artifact + harness 全套）证明了"plugin 接入"这条路径是顺的：21 行装配，9 测试通过，框架未变形。同时小修了 3 个 M1 暴露的真实需求，每个修法都保持「约定 + 默认值」的形态，没有引入新抽象。**
