# React Native 热重载（builder dev rn）

数据截至 2026-09（ios-builder v0.11.0）。

`builder dev rn` 是 `builder dev react-native` 的简写。通道构成：本地跑 Metro Bundler
供 JS bundle，IPA 远程构建后经 MobAI 安装并自动配好 Metro URL。**两个硬前提**：
物理设备（不支持模拟器）＋手机与运行 Metro 的电脑在**同一 WiFi**。
设备通道见 `ios-builder/references/mobai-device-bridge.md`。

## 生命周期

```
[本地] Metro :8081        ←  JS bundle 由手机上的 app 拉取
          ↑
builder ios build         →  远程 xcodebuild，IPA 落 ./dist/
          ↓
builder dev rn            →  ① Metro 未跑则启动
                              ② MobAI 安装 IPA（可选重签）
                              ③ 以自动配好 Metro URL 的方式启动 app
```

上游原文三步："Start Metro bundler if not running / Install the IPA on your device
(with optional re-signing) / Launch the app with Metro URL configured automatically"。

## 命令对照

| 场景 | 命令 |
| --- | --- |
| 首次 | `builder dev rn` |
| 复用已装 | `builder dev rn --skip-install --bundle-id com.example.myapp.TEAMID` |
| 8081 被占 | `builder dev rn --metro-port 8082` |
| 看 app 日志 | `builder dev rn --logs` |
| 单独验证 Metro | `npx react-native start` |

## 端口

| 项 | 取值 / 说明 |
| --- | --- |
| `--metro-port` 默认 | `8081`（上游排错原文 "Verify the Metro port is correct (default: 8081)"） |
| `builder.json` `reactNative.metroPort` | 配置里存在，但上游 README 未文档化——优先用 flag |
| 换端口时 | WSL 防火墙规则里的 `-LocalPorts` 要同步改（见下文） |

## Fast Refresh 开启条件

1. 摇一摇设备，或在 Metro 终端按 `d` 打开 dev menu；
2. 在 dev menu 里开启 Fast Refresh；
3. 改动没生效时在 Metro 终端按 `r` 手动 reload。

## 何时必须重建（上游 "When to Rebuild"）

| 改动类型 | 处理 |
| --- | --- |
| 原生代码（Swift、Objective-C、Podfile、原生模块） | 执行 `builder ios build` 并重装 |
| 仅 JavaScript | 不重建，Metro 自动处理 |

## Expo 差异

| 要点 | 行为 |
| --- | --- |
| 托管 Expo 的 git 里没有 `ios/` | `builder init` 仍把 `ios.path` 记为 `"ios"` |
| 预构建 | runner 执行 `expo prebuild --platform ios --no-install` |
| bundle id 必须显式声明 | `app.json` 设 `expo.ios.bundleIdentifier` 或 `app.config.js/ts` 设 `ios.bundleIdentifier`，否则构建失败并点名缺的配置项 |
| Debug 包依赖 Metro | Debug IPA 从 Metro 加载 JS；要独立可装包在 `builder.json` 设 `"ios": {"configuration": "Release"}` |
| JS 依赖与 Node 版本 | runner 用项目自身的包管理器装依赖（npm/Yarn/pnpm/Bun，看 `package.json` 的 `packageManager` 或 lockfile），Node 取 `.nvmrc`、`.node-version` 或 `engines.node` |
| 冷构建时长 | 免费 runner 上 30–60 分钟，预算见 `ios-builder/references/troubleshooting.md` E8 |

## WSL：Hyper-V 防火墙拦 Metro

上游原文："On WSL with mirrored networking, the Hyper-V firewall blocks the phone from
reaching Metro by default"。在 Windows PowerShell 放行 8081（若用 `--metro-port` 换了端口，
改 `-LocalPorts`）：

```powershell
New-NetFirewallHyperVRule -Name "Metro" -DisplayName "Metro bundler" -Direction Inbound -VMCreatorId '{40E0AC32-46A5-438A-A0B2-2B479E8F2E90}' -Protocol TCP -LocalPorts 8081
```

## 排错小表

| 症状 | 首步 | 错误码 |
| --- | --- | --- |
| Metro 起不来 | 确认 Node.js 与 React Native CLI 已安装；执行 `npx react-native start` 复现 | 见 `ios-builder/references/troubleshooting.md` E6 |
| App 连不上 Metro | 确认手机与电脑同一 WiFi；确认 Metro 端口 | 见 `ios-builder/references/troubleshooting.md` E6 |
| WSL 下连不通 | 执行上文 `New-NetFirewallHyperVRule` 命令 | 见 `ios-builder/references/troubleshooting.md` E6 |
| 热重载不生效 | 按 `d` 开 dev menu，开启 Fast Refresh，再按 `r` reload | 见 `ios-builder/references/troubleshooting.md` E6 |
| "No devices found" | 执行 `builder mobai ping` | 见 `ios-builder/references/troubleshooting.md` E1 |
| 原生模块改动无效果 | `builder ios build` 后 `builder dev rn` 重装 | 见 `ios-builder/references/troubleshooting.md` E7 |

## 相关文档

- 设备通道与 WSL 网络：`ios-builder/references/mobai-device-bridge.md`
- Flutter 对照：`ios-builder/references/flutter-hot-reload.md`
- 错误码手册：`ios-builder/references/troubleshooting.md`
- 签名与重签降级：`ios-builder/references/code-signing.md`
