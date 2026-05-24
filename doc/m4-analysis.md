# M4 复盘 — 第二个项目（SimGraph）+ 跨应用组合验证

> 状态：✅ 已完成
> 关键产出：`examples/simgraph_plugin/` + `examples/multi_app/`（两 app 共存）+ 13 个新测试
> **路线图全部完成**：M0→M1→M2→M3→M4 ✅

---

## 1. M4 的核心目的

按 design.md §九的纪律：「**第二个项目接入之前，不要急着发版**。框架最大的坑是只服务一个项目时自以为通用。」

M4 不是为 SimGraph 而做 SimGraph，**是为了用一个领域结构完全不同的应用去逼框架的抽象暴露错误**。

---

## 2. SimGraph 选得对不对？

**对**。看两个应用的关键维度对照：

| 维度 | chatcfd | simgraph | 是否结构不同 |
|---|---|---|---|
| 用户动词 | "analyze", "calculate" | "find", "search", "trace" | ✅ |
| 工具有状态 | 是（session_id 链） | 几乎全无状态 | ✅ |
| 状态位置 | 进程内 VTK | 外部 Neo4j | ✅ |
| 返回数据大小 | 兆级 mesh 二进制 | KB 级 JSON | ✅ |
| Artifact 形态 | mesh / table / file | result_list / data_card / subgraph | ✅ |
| 典型 turn 长度 | 长（load→calc→export 链） | 短（一次 query_graph 出结果） | ✅ |
| Harness 关注点 | 路径白名单（case 目录） | 路径白名单（index 目录）+ 写防护 | 同型不同根 |

**这就是好的对照**——很多维度相反，但底层仍然套同一份框架抽象。

---

## 3. 框架抽象有没有顶住？

### 3.1 顶住的部分（设计被验证）

| 抽象 | chatcfd 用法 | simgraph 用法 | 结论 |
|---|---|---|---|
| `ToolExecutor`/`@tool` | 6 个 stateful + binary 返回 | 6 个 stateless + JSON 返回 | **同 API 双用法都顺**。装饰器没限制 stateful/stateless |
| `PromptBuilder` ABC | 拼 active_case + 单元约定 | 拼 pinned_files + recent_queries | **build(thread) → str 足够** |
| `ArtifactFactory` ABC | 三种 kind | 三种 kind | **make() 接口够通用** |
| `HarnessHook` | 单个 hook 做路径检查 | 单个 hook 做路径检查 | 复用 |
| `Harness([h1, h2])` | — | — | M2 的"列表组合"在 M4 验证：`Harness([cfd_hook, sg_hook])` 直接用，框架无改动 |
| `Thread.metadata[...]` | `cfd_state` | `sg_state` | **同一 thread 上两套状态自然共存** |
| `BINARY_KEYS` 约定 | mesh blob 触发 | 不触发（无 binary） | **不强制：约定只在有用时启用** |
| `SkillLoader(dir)` | 加 chatcfd 自己的 skills 目录 | 加 simgraph 的 | 完全隔离 |
| `Compactor` | 长 calc 链对话用 | 长搜索对话用 | 不分领域 |

### 3.2 暴露的小坑（设计未失败但发现新需求）

1. **PromptBuilder 默认实现假设 `skills` 字段**
   - `PromptBuilder.__init__(skills=())` 是默认行为；CFDPromptBuilder/SimGraphPromptBuilder 都得调 `super().__init__(skills)` 才能正确传递
   - **不算问题，但可以更优雅**：让默认 build() 就用 self.skills

2. **`UnionPromptBuilder` / `UnionArtifactFactory` 是 host 写的，不在框架**
   - 这是**正确**的——它们是组合规则，框架不该规定
   - 但每个想合并多 app 的 host 都要重写一遍
   - **决定：写进 `doc/plugin_authoring.md` 作为推荐 pattern，但不放进框架**

3. **`ToolRegistry` 在重名 register 时 raise**
   - 当前用例（CFD camelCase + SimGraph snake_case）没冲突
   - 如果将来两个 plugin 都有 `search` 工具会爆
   - **决定**：先报错，因为静默覆盖更危险；plugin 作者要负责命名空间。**未来如果痛**，加 `register(executor, prefix="cfd_")` 选项

### 3.3 完全没用到的抽象

- `ToolExposure.DEFERRED` / `ToolSearch` — 12 个工具还撑得住 prompt
- 显式 `cancel` 通过 IPC — 两个 demo 还没演示
- `Thread.fork()` — 演示用例没触发

**这些不算「设计错误」，只算「现在还不需要」**。它们的存在让未来不写新代码就能用。

---

## 4. 两个应用的关系全图

```
              ┌───────────────────────────────────────────┐
              │                  agentkit                  │
              │   protocol / tools / harness / session /   │
              │   skills / llm / observability / mcp /     │
              │   ipc / plugin / runtime                   │
              └────────────────┬──────────────────────────┘
                               │ pip install agentkit
              ┌────────────────┼────────────────┐
              ▼                ▼                ▼
      ┌────────────────┐ ┌──────────────┐ ┌──────────────────┐
      │ chatcfd_plugin │ │simgraph_plugin│ │   multi_app      │
      │  6 CFD tools   │ │ 6 graph tools │ │   import 两者    │
      │  CFDPromptBldr │ │ SGPromptBldr  │ │  UnionPromptBldr │
      │  CFDArtifactFy │ │ SGArtifactFy  │ │  UnionArtifactFy │
      │  cfd_harness   │ │ sg_harness    │ │  Harness([h,h])  │
      └────────────────┘ └──────────────┘ └──────────────────┘
              │                │                  │
              ▼                ▼                  ▼
      :8765/agent       :8766/agent          :8767/agent
       (CFD only)       (SimGraph only)     (cross-app)
```

**关键观察**：

1. **两 plugin 互相不知道对方存在**
   - `chatcfd_plugin/` 不 import `simgraph_plugin/`，反之亦然
   - 共存能力 100% 来自 agentkit 的扩展点设计

2. **跨应用工作流由 LLM 编排，不是代码**
   - 用户："找张伟做的 Ma6，加载第一个分析"
   - LLM 选择 `simgraph.query_graph` → 看到结果 → 选择 `chatcfd.loadFile`
   - Plugin A 的输出**不直接喂给** Plugin B；都经过 LLM 这一层
   - 这是**最干净的耦合**——零

3. **工具的关系不是层次关系**
   - chatcfd 工具不在 simgraph 工具之上、之下、之内
   - 它们是同一个 Registry 里的同级条目
   - 框架（Router/Harness/Tracer）一视同仁

4. **共享了什么？**
   - 同一个 LLM 客户端实例（省 API 配额）
   - 同一个 Thread（同一个对话窗口）
   - 同一个 Harness 链（任一 hook 拒就拒）
   - 同一个 Compactor（长对话压缩）
   - 同一个 ASGI 进程（一个端口）

5. **没共享什么？**
   - 业务状态：CFDState vs SimGraphState 在 Thread.metadata 各占一个 key
   - 系统 prompt：每个 plugin 自管
   - artifact kind：每个 plugin 各自定义
   - skill 目录：各自独立

---

## 5. 测试矩阵

| 套件 | 数量 | 验证什么 |
|---|---|---|
| `tests/test_smoke.py` (M1) | 7 | 框架基础 |
| `tests/test_m3.py` (M3) | 7 | Compact + IPC 升级 |
| `examples/chatcfd_plugin/test_chatcfd_plugin.py` (M2) | 9 | CFD 插件 |
| `examples/simgraph_plugin/test_simgraph_plugin.py` (M4) | 7 | SimGraph 插件 |
| `examples/multi_app/test_composition.py` (M4) | 6 | **跨 app 共存** |
| **总计** | **36** | 全绿 |

最关键的 6 个跨 app 测试：
- `test_no_tool_name_collision` — 12 个工具不重名
- `test_merged_registry_has_all_12_tools` — 合并后注册表完整
- `test_router_dispatches_either_app` — 同一个 Router 调度两边都行
- `test_union_prompt_includes_both_roles` — 两个 system prompt 都进了
- `test_union_artifact_factory_first_match_wins` — Artifact 委派正确
- `test_cross_app_workflow_simulation` — 真跨 app 调用链跑通

---

## 6. 关键发现 — 框架价值的最终证据

**chatcfd → simgraph 的"二次接入成本"**：

| 工作 | 工时 | 改了 agentkit 吗 |
|---|---|---|
| 6 个工具（mock impl） | ~80 行 tools.py | 否 |
| PromptBuilder + State | ~50 行 | 否 |
| ArtifactFactory（3 kind） | ~45 行 | 否 |
| Harness hook | ~25 行 | 否 |
| 2 个 skill markdown | ~30 行 | 否 |
| main.py 装配 | ~30 行 | 否 |
| **总** | **~260 行 plugin 代码** | **0 行 agentkit 代码** |

**这就是 design.md §九「第二项目验证」要找的答案**：
- 不改框架 → 抽象站得住
- 260 行写完一个完整 host → 接入成本可接受
- 跨 app 组合代码（UnionPromptBuilder / UnionArtifactFactory）才 ~25 行 → 组合便宜

---

## 7. 整个路线的对账

| 里程碑 | 计划工时 | 实际状态 | 关键交付 |
|---|---|---|---|
| M0 spike | 1-2 天 | 跳过（直接 M1） | — |
| M1 核心骨架 | 1 周 | ✅ 一次会话 | 11 模块 + 7 测试 |
| M2 迁 chatcfd | 1 周 | ✅ 一次会话 | 6 工具 reference plugin + 9 测试 + 流式/二进制/参数化 3 修 |
| M3 Thread + Compact | 4-5 天 | ✅ 一次会话 | Compact + IPC fork/open/cancel + 7 测试 |
| M4 第二项目验证 | 1 周 | ✅ 一次会话 | SimGraph plugin + multi-app + 13 测试 |

---

## 8. 框架代码体量最终审计

```
src/agentkit/   33 个 .py 文件   ~1380 行
                ↑ M3 后没新增模块，M4 完全没动框架
```

四个里程碑期间框架增量：

| 阶段 | 新增/修改 | 文件数变化 |
|---|---|---|
| M0→M1 | 全套骨架 | +31 |
| M1→M2 | 流式 + 二进制约定 + 参数化 | +0（修 2） |
| M2→M3 | Compactor + IPC 升级 | +1 (compact.py) |
| M3→M4 | **无** | +0 |

**M4 完全没碰框架**——这是抽象稳的最直接证据。

---

## 9. 还剩什么（按真触发条件，不按预想）

| # | 待办 | 触发条件（不出现就别动） |
|---|---|---|
| 1 | tiktoken 精确算 token | Compact 触发明显不准时 |
| 2 | retry 按错误类型 | 真量后看到 rate-limit/429 在 retry 时 |
| 3 | MCP 自动重连 | post_service 真出 production 断连时 |
| 4 | ThreadPool 持久化（SQLite） | 用户要求跨重启 resume 时 |
| 5 | Tool 命名空间前缀 | 两个 plugin 真出工具名冲突时 |
| 6 | `tool_search`（ToolExposure.DEFERRED 真用上） | 工具数 > 20 时 |
| 7 | reproduce 失败 turn 的能力 | 用户开始抱怨某次结果不对、想回放时 |

---

## 10. 一句话总结

**SimGraph 是一个领域结构和 chatcfd 几乎相反的应用，但它没逼框架做任何修改就跑起来了，并且跟 chatcfd 在同一进程里组合也没破坏任何 ABC。两个 plugin 互不依赖，跨应用工作流由 LLM 编排——这是"骨架 vs 肌肉"分离的最终证据。M4 完成，路线图收尾。**
