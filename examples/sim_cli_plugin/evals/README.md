# sim_cli 评测集

> 状态：v1（2026-05-24）
> 目的：保证 ops agent 在驱动 simgraph CLI 时遵守纪律——先看状态、不重复启动、不编 PID。

## 用例覆盖

| 文件 | 覆盖 | 用例 | 防护 |
|---|---|---|---|
| [status_first.yaml](status_first.yaml) | 启停纪律 | 4 | cli_status 先行、幂等启动 |
| [recovery.yaml](recovery.yaml) | 重启恢复 | 2 | stop → status → start |
