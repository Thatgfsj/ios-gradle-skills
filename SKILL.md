---
name: ios-gradle-skills
description: >
  iOS 构建技能包（OpenClaw / agent-skills 格式）。提供基于 MobAI ios-builder 的
  跨平台远程构建能力：xcodebuild 打包 IPA、签名、Flutter/RN 热重载、排错手册。
  适用于 Windows / Linux / macOS 上无 Mac 环境的 iOS 构建需求。
  不要用于纯本机 xcodebuild 或 Android Gradle 任务。
metadata:
  author: your-org
  version: "1.0"
  keywords: [ios, xcodebuild, ipa, builder, mobai, flutter, react-native, github-actions]
---

# iOS Builder Skills

iOS 构建知识库：远程 xcodebuild 通道、builder.json 单一配置源、项目模板、自动化脚本、排错手册。
数据截至 **2026-09**（ios-builder v0.11.0 / Xcode 16.4 工具链线）。版本号会过时——涉及具体版本时，
先看下方矩阵，拿不准就用文末官方链接核对，不要凭记忆编造版本。

## 标准技术栈（本知识库推荐基线）

| 类别 | 取值 |
|------|------|
| 语言 | Swift 6.2 语言模式（需 Xcode 26+ 工具链；镜像停在 16.x 时按 6.0 编译） |
| UI 框架 | SwiftUI（最低 iOS 17）/ 兼容 UIKit 桥接 |
| 最低支持 | iOS 17.0 |
| 构建系统 | xcodebuild + GitHub Actions macOS runner（上游模板 `macos-latest`，本仓库模板钉 `macos-15`） |
| 远程构建通道 | MobAI ios-builder（`builder` CLI，Go 实现） |
| 包管理 | Swift Package Manager（主）/ CocoaPods（兼容分支） |
| 签名 | `IOS_CERTIFICATE` + `IOS_PROVISIONING_PROFILE` Secrets 或 `--unsigned` |
| 热重载 | Flutter / React Native 通过 `builder dev` + MobAI |

单一配置来源：`builder/builder.template.json`（本仓库根目录）。

## Instructions

1. **识别工程形态**：检测根目录是否存在 `*.xcodeproj` / `*.xcworkspace`（原生）、
   `ios/`（RN/Expo/Flutter）、`platforms/ios/`（Cordova/Ionic）。
   详见 `ios-builder/references/framework-detection.md`。
2. **初始化 builder 配置**：若不存在 `builder.json`，复制
   `builder/builder.template.json` 并按检测结果填入
   `ios.path`、`ios.scheme`、`github.owner/repo`。
3. **按用户意图路由命令**（见下方 Command Matrix）。
4. **构建产物一律下载到 `./dist/`**，签名失败时回退 `builder ios build --unsigned` 并提示用户走 MobAI 安装重签。
5. **遇到失败**：先读 `ios-builder/references/troubleshooting.md` 的错误码表，再决定重试策略。

## Command Matrix（任务路由）

| 用户意图 | 必须执行的命令 | 前置条件 | 产物位置 | 常见错误速查 |
| --- | --- | --- | --- | --- |
| 首次接入仓库 | `builder init` | 已 `builder auth github` | `.github/workflows/ios-build.yml` | repo 检测失败 → 手填 `builder.json` |
| 打 Debug/Unsigned IPA | `builder ios build --unsigned` | workflow 已就绪 | `./dist/*.ipa` | 见 `ios-builder/references/troubleshooting.md` E2 |
| 打签名 IPA | `builder ios build` | Secrets 三件套已配 | `./dist/*.ipa` | 见 E3 |
| 配置签名 | `builder signing setup` | 本地有 .p12/.mobileprovision | GitHub Secrets | 见 E4 |
| Flutter 热重载 | `builder dev flutter` | MobAI 运行 + 设备连接 | — | 见 E5 |
| Flutter 二次启动 | `builder dev flutter --skip-install --bundle-id <id>` | 已装过 app | — | bundle ID 需含 TeamID 后缀 |
| RN 热重载 | `builder dev rn` | Metro 可用 + 同 WiFi | — | 见 E6 |
| 自定义 Metro 端口 | `builder dev rn --metro-port 8082` | 端口冲突 | — | — |
| 列设备 | `builder mobai ping` | MobAI API 开启外连 | — | WSL 需 `hostname.exe` + `.local` |
| 原生代码变更后重建 | 先 `builder ios build` 再重装 | Podfile/Swift 有改动 | `./dist/` | 见 E7 |
| 仅 Dart/JS 改动 | `—`（不重建，文件监听自动 hot reload） | watcher 开启 | — | 若无效按 `R` 强制 restart |

## Skill Triggers

命中下列任一意图时激活本 Skill：

- "iOS打包" / "构建IPA" / "xcodebuild" / "builder ios build"
- "iOS签名" / "provisioning profile" / "p12" / "builder signing"
- "iOS CI" / "GitHub Actions iOS" / "免Mac打包"
- "Flutter iOS" / "RN iOS 热重载" / "builder dev"
- "MobAI" / "builder.json"
- "新建iOS项目" / "iOS脚手架"

## 项目脚手架

```bash
python ios-builder/scripts/init_ios_project.py MyApp /path/to/projects
python ios-builder/scripts/init_ios_project.py --interactive
python ios-builder/scripts/init_ios_project.py MyApp -o /path --framework flutter --unsigned
```

生成内容：真实 `*.xcodeproj`（共享 scheme + `GENERATE_INFOPLIST_FILE`）、SwiftUI 源码
（`@main` App + ContentView + Assets.xcassets，**零第三方依赖**，SPM 包按需自加）、
填好 owner/repo/scheme 的 `builder.json`、由 `builder/ios-build.yml.template` 渲染的
`.github/workflows/ios-build.yml`、`.gitignore`。
`--framework flutter|react-native` 只给配置与 Dart/JS 侧文件——iOS 宿主工程必须分别用
`flutter create --platforms=ios` 与 RN CLI 生成，手写会随 SDK 版本漂移。
模板源在 `templates/`（占位符 `__APP_NAME__` 等），脚本只做渲染。
退出码：`0` 成功 / `1` 目录冲突 / `2` 模板缺失 / `3` 参数非法。

## 环境要求

1. **iOS 构建不需要本地 Mac**——由 GitHub Actions macOS runner（上游生成的 workflow 写
   `macos-latest`；本仓库模板固定 `macos-15` 以便复现）执行 xcodebuild。
2. **签名构建需上传三件套 Secrets**：`IOS_CERTIFICATE`（base64 .p12）、
   `IOS_CERTIFICATE_PASSWORD`、`IOS_PROVISIONING_PROFILE`（base64 .mobileprovision）。
3. **设备端调试需 MobAI**（真机；模拟器改走 `builder ios share`）：Windows/macOS 上运行 MobAI。
   WSL 两选一——Win11 22H2+ 推荐 `.wslconfig` 开 `networkingMode=mirrored`（保持默认
   `http://localhost:8686`）；否则在 MobAI Integrations → API server 启用
   "Allow external connections"，并把 `mobai.url` 写成 `http://<hostname.exe 的输出>.local:8686`；
   MobAI 设了 API token 时还要在运行目录的 `.env` 里给 `MOBAI_ACCESS_KEY`。
4. **CLI 安装**：

   ```bash
   curl -sSL https://raw.githubusercontent.com/MobAI-App/ios-builder/main/install.sh | bash
   ```

   macOS/Linux 也可 `brew install mobai-app/tap/ios-builder`（命令名仍是 `builder`）；
   Windows 直接下载 Release 资产 `builder-windows-amd64.exe` 重命名为 `builder.exe`。

## 配额提示

上游只公布账号侧额度，不替你聚合账单：

| 通道 | 公布的免费额度（2026-09） |
| --- | --- |
| GitHub Actions | GitHub Free 私有仓库 2,000 计费分钟/月；公共仓库标准 runner 免费。原文只说 macOS 计费与 Linux 不同，**没给倍率** |
| Codemagic | 个人账号 500 macOS M2 分钟/月（Teams 不给） |
| Bitrise | Hobby 档 300 credits/月，1 个私有 app（实际分钟看机型费率） |

按 GitHub 长期公布的 macOS 10 倍费率折算（**估算，不是上游承诺值**）：
约 200 macOS 分钟/月 ≈ **15-20 次 IPA 构建/月**；冷启动的 RN/Expo 构建单次就要 30-60 分钟。
免费档单个 workflow 上限 90 分钟（含装依赖与编译）。

Agent 规则：本月第 10 次以上构建前必须先提醒用户额度；能靠热重载验证的改动不要重建；
需要快速验证时优先 `builder ios build --unsigned`。
核对最新额度：https://github.com/MobAI-App/ios-builder/blob/main/docs/providers.md

## 知识库路由（References）

按需下钻，不要整目录通读；每篇都可独立执行。

| 遇到的问题 | 读哪篇 |
| --- | --- |
| 不知道工程形态 / `ios.path`、`scheme` 该填什么 | `ios-builder/references/framework-detection.md` |
| `builder.json` 字段含义、默认值、profile 与 signing set | `ios-builder/references/builder-json-schema.md` |
| 想改 CI / 怀疑 workflow 与 CLI 版本不匹配 | `ios-builder/references/workflow-yml-anatomy.md` |
| 证书、描述文件、Secrets 命名、无付费账号的降级路径 | `ios-builder/references/code-signing.md` |
| Flutter 热重载生命周期、何时必须重建 | `ios-builder/references/flutter-hot-reload.md` |
| Metro / Fast Refresh / 同 WiFi 与 WSL 防火墙 | `ios-builder/references/react-native-hot-reload.md` |
| MobAI 装不上、WSL 网络、设备被占用、模拟器能力边界 | `ios-builder/references/mobai-device-bridge.md` |
| 任何报错 | `ios-builder/references/troubleshooting.md`（先查 E1~E10 索引） |

## 排错索引

详细错误码、根因与修复脚本见 `ios-builder/references/troubleshooting.md`。
本文件不重复其内容，仅在根因定位后引导 agent 读取对应小节。
千行失败日志先交给 `ios-builder/scripts/ai/analyze_build_log.py` 映射到 E 码，再决定重试策略。

## 版本时效

- Xcode / iOS 版本：https://developer.apple.com/news/releases/
- GitHub Actions macOS 镜像：https://github.com/actions/runner-images
- ios-builder 上游：https://github.com/MobAI-App/ios-builder

---
Source: https://github.com/your-org/ios-gradle-skills
