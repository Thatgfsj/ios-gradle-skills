# ios-gradle-skills

![Build Status](https://img.shields.io/github/actions/workflow/status/your-org/ios-gradle-skills/validate.yml?branch=main)
![License](https://img.shields.io/github/license/your-org/ios-gradle-skills)
![builder](https://img.shields.io/badge/ios--builder-v0.11.0-blue)
![iOS](https://img.shields.io/badge/iOS-17.0-blue)

供 AI agent 使用的 **iOS 构建技能包**（OpenClaw / agent-skills 格式）：
在没有 Mac 的 Windows / Linux / macOS 上，用 MobAI `ios-builder` 的远程
xcodebuild 通道打 IPA、配签名、跑 Flutter / React Native 热重载，并附带排错手册与项目脚手架。

> 数据截至 **2026-09**（ios-builder v0.11.0，发布于 2026-09-17）。
> 版本号会过时——按 [SKILL.md](SKILL.md) 文末的官方链接核对后再动手。

## What is this?

A skill pack for [OpenClaw](https://github.com/openclaw/openclaw)-style agent runtimes. It gives an
agent the routing table (which `builder` command for which intent), a single config source
(`builder/builder.template.json`), scaffolding scripts, knowledge references and a troubleshooting
code table (E1–E10). The heavy lifting is done by
[MobAI-App/ios-builder](https://github.com/MobAI-App/ios-builder) — a Go CLI that drives
GitHub Actions macOS runners, so **no local Xcode is required to build an IPA**.

## Standard Tech Stack

| Category | Value |
|----------|-------|
| **Language** | Swift 6.2 语言模式（需 Xcode 26+；模板默认按 6.0 编译以适配 16.x 镜像） |
| **UI** | SwiftUI，最低 iOS 17.0（兼容 UIKit 桥接） |
| **Build system** | xcodebuild，跑在 GitHub Actions macOS runner 上（`macos-15` / 上游用 `macos-latest`） |
| **Remote channel** | MobAI ios-builder（`builder` CLI）；可选 Codemagic / Bitrise |
| **Packages** | Swift Package Manager（主）/ CocoaPods（兼容分支） |
| **Signing** | legacy 三件套 Secrets，或按 distribution 分后缀的 signing set；也可 `--unsigned` |
| **Hot reload** | Flutter / React Native 经 `builder dev` + MobAI（真机）；模拟器走 `builder ios share` |

## 与 android-gradle-skills 的对应关系

本仓库是 [Thatgfsj/android-gradle-skills](https://github.com/Thatgfsj/android-gradle-skills)
的 iOS 对应物，骨架与编排方式一致，替换的是底层构建通道：

| android-gradle-skills | ios-gradle-skills |
| --- | --- |
| AGP / Gradle / JDK 版本矩阵 | Xcode / iOS / runner 版本矩阵 |
| `init_android_project.py` | `init_ios_project.py` |
| `./gradlew assembleDebug` | `builder ios build [--unsigned]` |
| `libs.versions.toml` 单一版本源 | `builder.template.json` 单一配置源 |
| Convention Plugin（`build-logic/`） | 共享 `ios-build.yml` workflow 模板 |
| Jetpack Compose 模板 | SwiftUI 模板 |
| `.github/workflows/validate.yml` | 同名，但跑在 `macos-15` + builder CLI |

## Quick Start

### 1. 装 CLI（一次）

```bash
curl -sSL https://raw.githubusercontent.com/MobAI-App/ios-builder/main/install.sh | bash
# macOS / Linux 备选：brew install mobai-app/tap/ios-builder
# Windows：下载 builder-windows-amd64.exe，改名 builder.exe 并加入 PATH
```

### 2. 新建工程

```bash
python ios-builder/scripts/init_ios_project.py MyApp /path/to/projects
python ios-builder/scripts/init_ios_project.py --interactive          # 问答模式
python ios-builder/scripts/init_ios_project.py MyApp -o /path --framework flutter
```

产出真实可构建的 SwiftUI 工程：`MyApp.xcodeproj` + 源码 + `builder.json` +
`.github/workflows/ios-build.yml` + `.gitignore`。

### 3. 接入远程构建并出包

```bash
cd /path/to/projects/MyApp
builder auth github
builder init                      # 写回权威 workflow，并把 owner/repo 探测进 builder.json
builder ios build --unsigned      # IPA 落在 ./dist/
```

签名构建：`builder signing setup --certificate <p12> --profile <mobileprovision>` 后
执行 `builder ios build`（详见 [code-signing.md](ios-builder/references/code-signing.md)）。

### 4. 装机与热重载

```bash
builder mobai ping                             # MobAI 在线 + iPhone 已连
builder dev flutter                            # Dart 改动自动 hot reload
builder dev rn --metro-port 8082               # Metro 端口冲突时
```

## Project Structure

```
ios-gradle-skills/
├── SKILL.md                        # agent 入口：路由 + 命令矩阵 + Skill Triggers
├── claw-skill.yaml                 # 机器可读清单（capabilities / references / examples）
├── builder/
│   ├── builder.template.json       # 单一配置源（对标 libs.versions.toml）
│   └── ios-build.yml.template      # workflow 精简等价模板
├── ios-builder/
│   ├── scripts/
│   │   ├── init_ios_project.py     # 脚手架（渲染 templates/）
│   │   ├── ai/                    # agent 调用：日志分析、配置补丁
│   │   └── ops/                   # 运维：触发构建、Secrets 体检、Skill 自检
│   └── references/                 # 知识库 8 篇
├── templates/
│   ├── swiftui-starter/            # 唯一模板源（占位符 __APP_NAME__ 等）
│   ├── flutter-starter/
│   └── react-native-starter/
├── examples/
│   ├── basic-swiftui-app/          # ✅ 真实可构建（CI 每次验证）
│   ├── flutter-hot-reload/         # 设计文档（尚无代码）
│   └── rn-hot-reload/              # 设计文档（尚无代码）
└── .github/
    ├── workflows/validate.yml      # lint + macOS 上真实编译示例
    ├── dependabot.yml
    └── secrets.example.md          # 签名 Secrets 命名表
```

## Skill Triggers

对话里出现下列意图时激活本 Skill：

- "iOS打包" / "构建IPA" / "xcodebuild" / "builder ios build"
- "iOS签名" / "provisioning profile" / "p12" / "builder signing"
- "iOS CI" / "GitHub Actions iOS" / "免Mac打包"
- "Flutter iOS" / "RN iOS 热重载" / "builder dev"
- "MobAI" / "builder.json"
- "新建iOS项目" / "iOS脚手架"

**不激活**：纯本机 xcodebuild 调试、Android Gradle 任务（用 android-gradle-skills）。

## Setup Requirements

1. **不需要 Mac**：xcodebuild 由 GitHub Actions macOS runner 执行；本机只要 `builder` CLI 与 git。
2. **签名要付费开发者账号**：Apple 只给付费账号发证书。没有账号就 `--unsigned` 出包，
   装机时让 MobAI 用免费 Apple ID 重签（bundle id 会多出 TeamID 后缀）。
3. **真机调试要 MobAI**：Windows / macOS 上运行 [MobAI](https://mobai.run)，iPhone 数据线连好。
   WSL 需要 mirrored 网络，或开启 "Allow external connections" 后改用
   `http://<主机名>.local:8686`（详见 [mobai-device-bridge.md](ios-builder/references/mobai-device-bridge.md)）。
4. **配额**：GitHub Free 私有仓库 2,000 计费分钟/月，macOS 计费更贵；
   单次 IPA 构建 30-60 分钟冷启动，免费档单个 workflow 上限 90 分钟。

## CI

`.github/workflows/validate.yml` 做三件事：

- **lint**（ubuntu）：Python 语法、JSON/YAML 可解析、`ios-builder/scripts/ops/lint_skill.py`
  校验 SKILL.md frontmatter / 命令矩阵 / references 路由 / 示例工程 pbxproj 结构
- **build-example**（`macos-15`）：用 xcodebuild 真实编译 `examples/basic-swiftui-app`，
  打成 Unsigned IPA 并上传 artifact
- **builder-e2e**（可选，默认关闭）：装 `builder` 后走完整远程通道；
  因需要交互式 GitHub 授权且会向同一仓库推快照 ref，只在仓库 Variable
  `ENABLE_BUILDER_E2E=true` 且提供 `secrets.ACTIONS_BUILDER_TOKEN` 时运行

## Contributing

见 [CONTRIBUTING.md](CONTRIBUTING.md)。特别欢迎：更新过时的版本数据（标注数据日期）、
补充 E 码排错案例、把两个 design-doc 示例落地成可构建工程。

## License

MIT — free to use, modify, and distribute.
