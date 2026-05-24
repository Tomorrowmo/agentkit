# simgraph 评测集

> 状态：v1（2026-05-24）
> 目的：把 SimGraph 项目 docs/评测 里的核心铁律转译为本插件可执行的用例。
> 来源：参考 [simgraph-new docs 评测](D:/Git/simgraph-new/docs/评测/README.md)。

## 用例覆盖

| 文件 | 覆盖流程 | 用例数 | 核心防护 |
|---|---|---|---|
| [search.yaml](search.yaml) | NL 搜索 | 5 | 不编 file_id、count 稳定、过滤参数生效 |
| [provenance.yaml](provenance.yaml) | 谱系追踪 | 3 | upstream 真来自图谱、空 upstream 老实说 |
| [ingest_dedup.yaml](ingest_dedup.yaml) | 入库去重 | 3 | 同 path 不生成多 file_id |

## 反模式总则（贯穿 — 抄自 simgraph 评测）

| # | 铁律 |
|---|---|
| R1 | 数值/file_id 必须可溯源 |
| R2 | 同图谱下 count 必须稳定（不漂） |
| R3 | 不说"已完成"无对应 tool_call |
| R4 | LOW/MED 置信度必须如实暴露 |
