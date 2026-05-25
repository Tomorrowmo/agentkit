# M6 复盘 — 评测从「CI 烟测」升级为「开发工具」

> 状态：✅ 已完成
> 关键产出：评测 setup hook 系统 + live-LLM 模式 + `python -m agentkit.eval` CLI（含 diff 子命令）
> **86/86 全绿**（M5 是 79，新增 7）

---

## 1. 这一版回应了 M5 复盘的三条最高优先级遗留

| M5 复盘 | M6 交付 |
|---|---|
| 2. 评测 setup hook 系统化（目前 sim_cli 是测试代码硬写） | `agentkit/eval/setup.py` + `@setup_hook("key")` 装饰器 |
| 1. live-LLM 评测模式 | `agentkit/eval/live.py` + `AGENTKIT_EVAL_MODE=live` 环境开关 |
| 4. scorecard 上传到 dashboard（趋势图） | 简化版：`python -m agentkit.eval diff prev.json new.json` 直接对比两份评测结果 |

加上一个连带交付：`python -m agentkit.eval run` 命令行入口，让评测脱离 pytest 也能跑。

---

## 2. setup hook 系统的设计合理性

### 2.1 痛点（M5 暴露的）

M5 的 sim_cli 评测测试代码里有这段硬写：
```python
def apply_setup(case):
    setup = case.setup or {}
    process_registry.procs.clear()
    for name in setup.get("pre_running", []):
        process_registry.add(name, ["simgraph", "c"], pid=12345)
```

每个 plugin 都要在自己的 test_evals.py 里写一遍类似的 dispatch。sim_parse 还更恶心——`/tmp/...` 路径要 remap + 创建文件。**典型的"重复模式想被抽出来"信号**。

### 2.2 设计

```python
@setup_hook("pre_running", teardown=lambda v, c: process_registry.procs.clear())
def _pre_running(value, ctx):
    for name in value:
        process_registry.add(name, ...)
```

- key 是 `case.setup` dict 的 key——declarative dispatch
- fn 接 `(value, AppContext)`——能拿到 registry/threads/router
- teardown 可选——案例之间状态不互相污染
- 注册进 `DEFAULT_REGISTRY` 是 import-time side effect——plugin 的 `eval_setup.py` 一旦被 import 就生效
- 也可传自定义 `registry=` 做测试隔离

### 2.3 为什么是 dict-key dispatch 而不是 class hierarchy

考虑过：
- A. `class PreRunningSetup(SetupHandler):` 继承式
- B. dict-key 装饰器（最终选这个）
- C. 一个大 `setup(case, ctx)` 函数让 plugin 自己 switch case

A 太重——hook 是 5 行函数，建 class 浪费。
C 太散——每个 plugin 自己 switch case 会重复一堆 boilerplate。
B 是最小可用——key 当 dispatch key，框架管循环。

**疑点**：如果两个 plugin 都注册 `path` key（sim_parse 已经用了），会都被触发。当前实现是"按注册顺序全跑"，这对 union plugin 是想要的（路径需要被两个 plugin 各自处理）。冲突时由 plugin 作者用更具体的 key 名字（如 `simparse_path`）规避。**先这样**。

### 2.4 收益对账

| 文件 | M5 行数 | M6 行数 | 减少 |
|---|---|---|---|
| `examples/sim_cli_plugin/test_sim_cli_evals.py` | 56 | 50 | 11% |
| `examples/sim_parse_plugin/test_sim_parse_evals.py` | 86 | 53 | 38% |

setup 逻辑下沉到 plugin 自己的 `eval_setup.py`，pytest 文件回归"只跑 case"的本职。

---

## 3. live-LLM 模式

### 3.1 关键区分

| 模式 | 验证什么 | 速度 | 需要 |
|---|---|---|---|
| **scripted** | 框架管道：tool dispatch / harness / args / errors | <1s/case | nothing |
| **live** | LLM 实际行为：选对工具了吗？args 填对了吗？没幻觉吗？ | 数秒/case | API key + 配额 |

**两个模式跑同一份 EvalCase**——没有重复定义。同一个 YAML 既是 scripted-mode 的脚手架，也是 live-mode 的断言基准。这是核心设计纪律。

### 3.2 API 形态

```python
from agentkit.eval import run_cases, EvalMode

results = await run_cases(
    cases=load_cases("evals/"),
    builder=build_eval_app,    # (llm: LLMClient) -> App
    mode=EvalMode.LIVE,
)
```

`builder` 函数收 LLMClient，吐 App。**mode 由 caller 决定 LLM 类型**——这是一个故意的小契约：
- scripted: 每 case 都 `builder(ScriptedLLM(per-case-script))`
- live: 一次 `builder(LLMClient(model=...))`，所有 case 共享同一个 App

### 3.3 没有真正 live-跑过的原因

我没用真 API key 跑过 live mode（避免烧用户的钱）。但 `test_run_cases_scripted_mode_uses_builder_per_case` 验证了 dispatch 机制——live 走同一条路径，换的只是 LLM 实例。**真做 LLM 回归测试**时，用户加 `AGENTKIT_EVAL_MODE=live AGENTKIT_MODEL=claude-sonnet-4-6` 跑 CLI 即可。

---

## 4. CLI 设计

### 4.1 命令

```
python -m agentkit.eval run <cases-path> --app <module:func> [--mode scripted|live]
                                          [--json path] [--md path]
python -m agentkit.eval diff <prev.json> <new.json>
```

### 4.2 模块入口约定

`--app sim_cli_plugin.eval_setup:build_eval_app` — plugin 显式暴露一个 `(llm) -> App` builder 函数。这是 **plugin 与评测 CLI 之间的契约**。

每个参考 plugin 现在都在 `<plugin>/eval_setup.py` 里有 `build_eval_app(llm)`。production main.py 自己拼 App、用真 LLM 配置；evaluation builder 共用 tools/skills/harness 但 LLM 是参数。

### 4.3 退出码语义

- `run` 返回 1 当任何 case fail（CI gate）
- `diff` 返回 1 当**有回归**（regressed cases ≥ 1）——fixed/added 不算失败

这让 CI 能直接 `python -m agentkit.eval diff baseline.json head.json`，回归就挂掉。

### 4.4 Windows 编码踩坑

Markdown 输出用 `✅` / `❌`。Windows 默认 GBK，直接 print 会 `UnicodeEncodeError`。CLI `main()` 入口加了 `_force_utf8_stdio()`——stdout/stderr 切 UTF-8。**测试时真踩到了这个**——CLI 已加固。

---

## 5. 测试矩阵

| 套件 | 数 | 备注 |
|---|---|---|
| 框架自验 (smoke + m3 + eval_framework + eval_m6) | 29 | 含 setup hook + CLI diff 测试 |
| chatcfd plugin + evals | 9 + 12 | |
| simgraph plugin + evals | 7 + 11 | |
| sim_cli evals | 6 | |
| sim_parse evals | 6 | |
| multi_app composition | 6 | |
| **合计** | **86** | 全绿，0.88s |

`test_eval_m6.py` 7 个新测试覆盖：
- setup hook 注册 + 跑 + teardown
- `@setup_hook` 装饰器进自定义 registry
- `resolve_mode` env 解析
- `run_cases` 在 scripted 模式 builder 调用语义
- `diff` 命令的回归 vs 干净退出码
- CLI `run` 端到端拿 sim_cli plugin 跑

---

## 6. 框架代码量审计

```
src/agentkit/   42 个 .py 文件   ~2000 行
                ↑ M6 新增 4: eval/{setup,live,cli,__main__}
```

| 阶段 | 文件增量 | 关键 |
|---|---|---|
| M5 | +5 | eval/*  + runtime/web_template |
| M6 | +4 | eval/{setup, live, cli, __main__} |

仍然没膨胀。

---

## 7. 「评测能做的事」清单（M6 后）

| 想做 | 怎么做 |
|---|---|
| CI 烟测：框架管道改了没破回归 | `pytest examples/<plugin>/test_*_evals.py` |
| LLM 回归测：换模型 / 改 prompt 后行为对吗 | `AGENTKIT_EVAL_MODE=live python -m agentkit.eval run evals --app ...` |
| 改 prompt 前后对比 | 跑两次 `agentkit.eval run --json` → `agentkit.eval diff old.json new.json` |
| 给评测加新 setup pattern | plugin 的 `eval_setup.py` 加 `@setup_hook("new_key")` |
| 跨 plugin 评测 | union 的 `build_eval_app` 把 SetupRegistry 用同一个 DEFAULT |
| 评测结果给非工程师看 | `--md scorecard.md` 输出，扔 wiki / PR comment |

---

## 8. 还没做的（按真触发条件排）

| # | 待办 | 触发条件 |
|---|---|---|
| 1 | live-LLM 真跑一次拿真数 | 用户给 API key + 第一次想测 prompt 改动 |
| 2 | scorecard 持久化到 SQLite/JSON 历史 | 多人改 prompt + 想看通过率长期趋势 |
| 3 | UI artifact 真渲染（mesh/subgraph 可视） | 给操作员用 |
| 4 | 评测结果上 dashboard (Grafana / 自建) | 上 production + 多人协作 |
| 5 | reproduce 失败 turn 命令（吐出全部上下文） | 第一次某 case 诡异挂时 |

---

## 9. 一句话总结

**M6 把 evaluation 从「pytest 跑一下」升级为「带 setup 钩子 + 跨模式 + 命令行 + 回归 diff」的开发工具：sim_cli/sim_parse 评测代码减肥 11~38%，scripted/live 两种模式共用同一份 YAML 案例，CLI 让 CI 直接 gate 回归。框架长 4 个文件没膨胀。下一步该让真 LLM 跑一次评测了。**
