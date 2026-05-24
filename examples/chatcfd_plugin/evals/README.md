# chatcfd 评测集

> 状态：v1（2026-05-24）
> 目的：固化 chatcfd 工作流的核心防线——loadFile 先于 calculate、不编造 case 名、force 必先问参考面积、mesh 不进 LLM。
> 格式：每个 .yaml 文件一组用例；可被 `agentkit.eval.load_cases` 直接读取。

## 用例覆盖

| 文件 | 覆盖流程 | 用例数 | 核心防护 |
|---|---|---|---|
| [load_then_calculate.yaml](load_then_calculate.yaml) | load→calc 链路 | 5 | 顺序、不空跳、错误传递 |
| [no_hallucination.yaml](no_hallucination.yaml) | 反幻觉 | 4 | 不编 case 名、不编 session_id |
| [harness.yaml](harness.yaml) | 安全边界 | 2 | 路径白名单 |

## 反模式总则（贯穿）

| # | 铁律 | 违反实例 |
|---|---|---|
| R1 | calculate 前必须先 loadFile 同 session | "session not loaded" 重试到 max_tool_rounds |
| R2 | 不编 case 名（必须先 listFiles） | "use case `xyz`" 但 xyz 不在 listFiles 结果 |
| R3 | mesh blob 不进 assistant 文本 | 把 `data` 字段几 KB 二进制 dump 给用户 |
| R4 | force 计算无参考面积时必须先问 | 直接报出 Fz=8.7（无 ref_area） |
