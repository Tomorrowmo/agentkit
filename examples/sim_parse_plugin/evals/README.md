# sim_parse 评测集

> 目的：验证「detect-first」纪律 + 不编 metadata + 拒绝越权路径。

| 文件 | 用例 | 防护 |
|---|---|---|
| [detect_first.yaml](detect_first.yaml) | 4 | detect 早于 parse、format=null 不硬上 |
| [forced_parse.yaml](forced_parse.yaml) | 2 | 用户明示 force 时才用 parse_<solver> |
