# Contributing to ios-gradle-skills

感谢参与！本文说明如何为本仓库新增 iOS 构建知识、示例工程或脚本。

## How to Contribute

### 1. Adding New iOS Knowledge

知识库文件放在 `ios-builder/references/`，沿用现有命名：

- `framework-detection.md` - 工程形态识别（原生/RN/Expo/Flutter/KMP/Cordova）
- `builder-json-schema.md` - `builder.json` 全字段与默认值
- `workflow-yml-anatomy.md` - `ios-build.yml` 逐段解读
- `code-signing.md` - 证书、描述文件、Secrets、降级路径
- `flutter-hot-reload.md` - Flutter 热重载生命周期
- `react-native-hot-reload.md` - RN/Metro 热重载
- `mobai-device-bridge.md` - MobAI 设备通道与 WSL 网络
- `troubleshooting.md` - 错误码表 E1~E10

新增一篇时，务必同时：在根 `SKILL.md` 的任务路由或排错索引里给出入口，
并在 `claw-skill.yaml` 的 `references:` 列表登记。

### 2. Adding Example Projects

示例放在 `examples/`，每个目录必须含 `README.md` 说明运行方式与要点。

- 可真实构建的工程：`ios.path` 指向含 `*.xcodeproj` 的目录，根目录带 `builder.json`，
  并在 `.github/workflows/validate.yml` 的 `build-example` job 中验证。
- 尚不可构建的：写成设计文档，并在其 README 首行明确标注
  "本目录为设计文档，尚无代码"——不要描述不存在的文件。

### 3. Adding Scripts

脚本放在 `ios-builder/scripts/ai/`（供 agent 调用）或 `ios-builder/scripts/ops/`（运维）。要求：

- 文件头 docstring 写清 Usage / Options / 退出码含义
- 跨平台（Windows / Linux / macOS / WSL），路径一律用正斜杠相对路径
- 作用对象是**用户的项目目录**（`--project` 参数或就近探测），绝不改动本仓库自身
- 失败时把原因写到 stderr，并给出可执行的修复建议

## Guidelines

- 文档要具体可执行，命令用第三人称祈使句（"执行 `builder ios build`"，不写"你应该…"）
- 不硬编码路径与 owner/repo，用占位符或从 `builder.json` 读取
- 避免冗余文档：不新增 `CHANGELOG.md` / `INSTALL.md` / `docs/` 站点，说明一律进 README 或 references
- `SKILL.md` 严格控制在 500 行以内；大段知识下沉到 `references/`，根文件只保留路由与关键矩阵

### 版本数据时效政策

本仓库价值高度依赖版本号准确，规则如下：

- Xcode / iOS SDK 版本以 [Apple 发布说明](https://developer.apple.com/news/releases/) 为准；
  macOS runner 镜像预装的 Xcode 版本以
  [actions/runner-images](https://github.com/actions/runner-images) 为准，不要凭记忆编造
- `builder` CLI 的命令、flag、`builder.json` 字段与 Secret 名称以
  [MobAI-App/ios-builder](https://github.com/MobAI-App/ios-builder) 上游 README 为准；
  上游升级后须复核 `builder/builder.template.json` 与 `ios-builder/references/builder-json-schema.md`
- 更新版本数据时，同步刷新 `SKILL.md` / `README.md` / `claw-skill.yaml` /
  `builder/builder.template.json` 中的默认值，并更新文首"数据截至"日期
- 不确定的 DSL 或 API 宁可不写，也不要写出看起来合理的假命令

## Submitting Changes

1. Fork 本仓库并新建分支
2. 提交前本地跑一遍校验：

   ```bash
   python ios-builder/scripts/ops/lint_skill.py
   ```

3. 用清晰的 commit message 提交，PR 里说明动机与验证方式

## Questions?

重大改动请先开 issue 讨论。
