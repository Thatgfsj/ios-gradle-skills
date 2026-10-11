# 工程形态识别

数据截至 2026-09（ios-builder v0.11.0）。SKILL.md 路由第 1 步（识别工程形态）落到本文：
给出判定依据、逐形态要点、检测后的字段校准清单，以及 `builder init` 与本仓库脚手架的分工。

## 决策主表

上游六种形态全部标注 auto-detected: Yes。`ios.path` 上游文档写作带斜杠（`ios/`），
写进 `builder.json` 时不带（如 `"path": "ios"`）。

| 形态 | 判定标志 | `ios.path` | scheme 默认 | 依赖安装步骤 | 易错点 |
| --- | --- | --- | --- | --- | --- |
| 原生 iOS/Swift | 仓库根有 `*.xcodeproj` / `*.xcworkspace` | `.`（根） | 留空 = 自动探测 | CocoaPods 项目恢复 Pods 缓存 | 缺 xcconfig 时 runner 会自动物化，别当垃圾删 |
| React Native | `package.json` + `ios/` | `ios` | 同上 | JS toolchain + Node + JS 依赖 + Pods | Debug IPA 从 Metro 拉 JS，独立分发要设 Release |
| Expo（managed） | `package.json` 含 expo，且 git 里没有 `ios/` | `ios` | 同上 | JS 依赖 + `expo prebuild` | app 配置缺 bundleIdentifier → 构建立即失败 |
| Expo（ejected） | `ios/` 已提交进 git | `ios` | 同上 | 同 RN | prebuild 遇到已含 Xcode 工程的目录会跳过 |
| Flutter | `pubspec.yaml` + `ios/` | `ios` | 同上 | Setup Flutter + `flutter pub get` | `flutter.version` 留空 = 装最新 stable |
| Kotlin Multiplatform | `iosApp/` | `iosApp` | 同上 | Setup JDK + Setup Gradle | run-script 阶段要调 Gradle 编 shared framework |
| Cordova/Ionic | `platforms/ios/` | `platforms/ios` | 同上 | 视生成方式 | `platforms/` 常为生成产物，构建前先确保目录存在 |

探测次序（本仓库建议，按路径特异性由深到浅）：`platforms/ios/` → `iosApp/` → `ios/`
（用 `pubspec.yaml` / `package.json` 区分 Flutter / RN / Expo）→ 仓库根工程文件。
上游只承诺 init 能探测，未规定次序；拿不准时以 `builder init` 写入的 `ios.path` 为准。

## 逐形态要点

### 原生 iOS/Swift
- `ios.path` 用默认 `"."` 即仓库根；工程放子目录时，指向含 `*.xcodeproj` / `*.xcworkspace` 的那级目录。
- `builder init` 会把 extension target（Widget、通知/分享扩展等）的 bundle id 从 Xcode 项目读进 `ios.extensions`。
- 仓库使用 `project.yml` 时，workflow 的 "Generate Xcode project (XcodeGen)" 步骤负责生成工程；
  缺失的 xcconfig 由 "Materialize missing xcconfig files" 补。
- 本仓库的可构建示例：`examples/basic-swiftui-app`（scheme `BasicApp`，`ios.path` 为 `.`，未签名）。

### Flutter
- `flutter.version` 作用于构建分支（透传到 workflow 的 `flutter_version` input）；`flutter.watch` 只作用于 `builder dev` 的本地监听。
- 分支步骤：Setup Flutter（subosito/flutter-action@v2）→ `flutter pub get`，版本取 `flutter.version`（如 `"3.24.0"`）。
- 热重载的文件监听参数在 `flutter.watch`（dirs / patterns / ignore / debounce），
  字段语义见 `ios-builder/references/builder-json-schema.md`，流程见 `ios-builder/references/flutter-hot-reload.md`。

### React Native
- Resolve JS toolchain：按 `package.json` 的 `packageManager` 字段或 lockfile 选 npm / Yarn / pnpm / Bun；
  Node 版本按 `.nvmrc`、`.node-version` 或 `engines.node`。随后 Setup Node.js、恢复 node_modules 缓存、Install JS dependencies。
- **Debug IPA 从 Metro 加载 JS**：要独立可跑的 IPA，在 `builder.json` 设 `"ios": {"configuration": "Release"}`；
  Debug 联调时设备必须与 Metro 处于同一 WiFi。细节见 `ios-builder/references/react-native-hot-reload.md`。

### Expo（managed 与 ejected）

| 模式 | `ios/` 是否在 git | 构建时行为 | 硬性前置 |
| --- | --- | --- | --- |
| managed | 否 | init 记 `"ios": {"path": "ios"}`；runner 执行 `expo prebuild --platform ios --no-install` 现场生成原生工程 | app 配置必须有 bundle id：`app.json` 的 `expo.ios.bundleIdentifier` 或 `app.config.js/ts` 的 `ios.bundleIdentifier`，缺失则构建立即失败并点名该设置 |
| ejected | 是 | 沿用提交里的 `ios/`；prebuild 跳过已含 Xcode 工程的目录 | 同 RN |

- 本地 `expo prebuild` 残留的 `ios/` 不会进构建快照（managed 项目通常已把它 gitignore）。
- `reactNative.expo` 在 Go 配置里存在、README 未记录；形态判断不要依赖该字段。

### Kotlin Multiplatform
- `builder init` 会询问 CI 构建用哪个 JDK（默认 17），写入 `kmp.jdkVersion`。
- workflow 分支 Setup JDK + Setup Gradle 不可跳：Xcode 的 run-script 阶段要调 Gradle 编译 shared framework。

### Cordova/Ionic
- `platforms/ios/` 一般是 `cordova platform add ios` / `ionic cordova prepare ios` 的产物；
  先把该目录纳入提交（或让 CI 能生成），再把 `ios.path` 指过去。

## 检测之后要改哪几个字段

复制 `builder/builder.template.json` 到项目根，逐项校准（全字段语义见 `ios-builder/references/builder-json-schema.md`）：

1. `project`、`github.owner`、`github.repo`：仅有的强制校验项。
2. `ios.path`：按主表取值；`ios.scheme` 可留空交给自动探测。
3. `ios.bundleId`：签名与 `builder signing setup` 定位 bundle id 的来源之一（优先级 `--bundle-id` > `ios.bundleId` > `./dist/` 最新 IPA）。
4. `ios.configuration`：默认 Debug；RN/Expo 出独立包务必改 Release。
5. `flutter.version`、`kmp.jdkVersion`：按对应小节固定，避免 latest 漂移。
6. `mobai.url`、`mobai.device_id`：WSL 下用 `<hostname>.local:8686`，见 `ios-builder/references/mobai-device-bridge.md`。
7. `defaultProfile`、`profiles`：要签名分发就配 profile，见 `ios-builder/references/code-signing.md`。

改完执行一次 `builder ios build --unsigned` 验证链路（失败先查 `ios-builder/references/troubleshooting.md`）。

## `builder init` 与本仓库脚手架的分工

| 项 | `builder init` | `ios-builder/scripts/init_ios_project.py` |
| --- | --- | --- |
| 作用对象 | **已有仓库**：探测形态、写 workflow 与 `builder.json`，并可选地直接 commit / push / 触发首次构建 | **从零新建**工程骨架（SwiftUI / Flutter / RN 模板渲染） |
| 生成文件 | `.github/workflows/ios-build.yml`、`.github/workflows/ios-share.yml`、`builder.json`（git add 行即这三件） | 工程文件 + 真实 `builder.json` + 由 `builder/ios-build.yml.template` 渲染的精简 workflow |
| workflow 内容 | 上游权威模板（约 69 KB，含 Flutter / RN / Expo / CocoaPods / KMP 分支与缓存） | 只保留原生 SwiftUI 主链路，inputs 与上游同名同序 |
| 交互项 | KMP 询问 JDK；managed Expo 记录 path `ios`；读 extensions | `--unsigned` 预设不签名；`--framework swiftui|flutter|react-native`；`--scheme` 默认等于 app 名（flutter 模板用 `Runner`） |
| 需要 CLI | 是 | 否（纯 Python 渲染） |

上游发布说明固定提醒："Existing repositories: run builder init once to refresh the workflow files."
——升级 `builder`（`builder update`）后在项目仓库重跑 `builder init`，否则旧 workflow 可能拒绝新特性
（如 `--profile` 需要的 `profile` input）。
