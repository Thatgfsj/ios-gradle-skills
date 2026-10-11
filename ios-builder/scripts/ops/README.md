# scripts/ops — 运维脚本

面向「把远程构建当服务用」的场景：接入、体检、触发、自检。
所有脚本**只碰用户的项目目录与远端仓库**，不改本仓库；读远端一律走 `gh` 或 `GITHUB_TOKEN`，
不打印任何 Secret 的值。

| 脚本 | 作用 | 依赖 | 典型调用 |
| --- | --- | --- | --- |
| `lint_skill.py` | 校验 SKILL.md 规范、命令矩阵、references 路由、错误码与示例工程 pbxproj 结构 | 无（有 pyyaml 时更深） | `python ios-builder/scripts/ops/lint_skill.py` |
| `trigger_build.py` | 无 builder CLI 时触发 workflow、轮询 run、把 `ipa` artifact 落到 `./dist/` | `gh` 或 `GITHUB_TOKEN` | `python trigger_build.py --project /path/to/MyApp --unsigned` |
| `selftest_lint.py` | 往临时副本里注入 18 种工程缺陷，断言 `lint_skill.py` 每条检查都能抓到（防止“看起来通过”的空转检查） | 无 | `python ios-builder/scripts/ops/selftest_lint.py -v` |
| `check_signing_secrets.py` | 查签名集合是否齐、本地 p12/mobileprovision 是否可用、类型与 distribution 是否匹配 | `gh` 或 `GITHUB_TOKEN`；可选 `openssl` | `python check_signing_secrets.py --project . --distribution store` |

## 与 builder CLI 的分工

正常路径永远是 CLI：`builder ios build` / `builder signing setup` / `builder dev …`。
本目录只在三种情况下取代它：

1. **CI/agent 需要机器可读输出**——`--json`、退出码、结构化报告；
2. **CLI 不可用或不可交互**——例如 `builder auth github` 走设备码，无法在无人值守环境完成；
3. **体检**——CLI 只在 dispatch 前查它自己关心的东西，`check_signing_secrets.py`
   会把描述文件类型、剩余有效期、设备数量一并列出来。

⚠️ `trigger_build.py` 的语义差异必须知道：它**不推工作区快照**（上游用 hidden ref
`refs/ios-builder/jobs/<build-id>`），构建的是远端**已提交**的代码。
要验证未提交的改动，用 `builder ios build`。GitHub API 不可达时可用
`--tag-fallback`（等价于上游的 `git tag ios-build/<name> && git push` 通道，但 tag 不携带 flags，
profile 取 `builder.json` 的 `defaultProfile`）。

## 约定

- 退出码：`0` 成功 / `1` 远端或校验失败 / `2` 配置缺失或非法 / `3` 缺凭据（各脚本 docstring 有逐条说明）。
- 口令、token 一律从环境变量读，绝不接命令行明文参数（`check_signing_secrets.py --password` 收的是**变量名**）。
- 产物目录固定 `./dist/`，与 CLI 一致；`.gitignore` 已忽略。
- 失败信息写 stderr 且附带可执行的修复建议；建议命令都出自
  `ios-builder/references/troubleshooting.md` 的 E 码索引。
