# scripts/ai — 供 agent 调用的脚本

这里的脚本**只输出结构化结果或补丁**，不改变仓库状态（除非显式 `--write`）。
Agent 的推荐用法：先调用本目录脚本拿到结论，再去 `ios-builder/references/` 读对应小节。

| 脚本 | 输入 | 输出 | 典型调用 |
| --- | --- | --- | --- |
| `analyze_build_log.py` | 远程构建日志（文件 / stdin） | E1~E10 错误码 + 根因 + 首条修复命令；`--json` 结构化 | `gh run view <id> --log > build.log && python analyze_build_log.py build.log --project .` |
| `patch_builder_config.py` | 目标工程目录 | 探测形态 + builder.json 的 unified diff；`--write` 才落盘（自动 `.bak`） | `python patch_builder_config.py --project /path/to/MyApp --unsigned` |

约定：

- 作用对象永远是**用户的项目目录**，绝不是本仓库。
- 退出码非 0 表示"需要人来决定"，不是"脚本坏了"；错误细节一律写 stderr。
- E 码含义见 `../references/troubleshooting.md`（脚本规则表与手册一一对应；
  另有 `SRC`＝源码编译错误、`ASC`＝App Store Connect 侧问题，这两类不占 E 码）。
- 不覆盖已有配置：`patch_builder_config.py` 只做合并式改写，未知字段原样保留。
