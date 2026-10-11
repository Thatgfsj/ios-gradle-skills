# MobAI 设备桥（builder mobai 与设备通道）

数据截至 2026-09（ios-builder v0.11.0）。

MobAI 是本机侧的设备桥：`builder` 靠它安装 IPA、带调试器启动 app、维持物理设备连接，
Flutter/RN 热重载与 `builder mobai` 命令族全部依赖这条通道。

## 安装与首连

1. 从 https://mobai.run/download 下载安装 MobAI，USB 连接 iPhone；
2. 执行 `builder mobai ping` 验证连通（默认 API 地址 `http://localhost:8686`）；
3. 首次 `builder dev flutter` / `builder dev rn` 会经 MobAI 安装 `./dist/` 的 IPA，
   并询问是否重签。

| 配置键（builder.json） | 默认 | 说明 |
| --- | --- | --- |
| `mobai.url` | `http://localhost:8686` | 按网络模式调整，见下文对照表 |
| `mobai.device_id` | `""` | 为空时 "uses first available if empty" |

## 重签与 TeamID 后缀

| 事实 | 说明 |
| --- | --- |
| 重签需要 iCloud 账号 | 上游建议在 icloud.com **新注册**，不要用主账号 |
| 重签产物换 bundle id | 新 id 带 TeamID 后缀（如 `com.example.myapp.TEAMID`），Builder 在后续提示中预填 |
| 签名/未签名 IPA 都能装 | 未签名 IPA 可在安装时用免费 Apple ID 重签（MobAI 会要求登录） |
| 模拟器包不签名 | 上游原文 "Simulator builds are never signed" |

## WSL 两套网络配置

| 项 | 方案 A：mirrored（上游推荐） | 方案 B：默认 NAT |
| --- | --- | --- |
| 系统要求 | Windows 11 22H2+ | 无特殊要求 |
| Windows 侧动作 | `%UserProfile%\.wslconfig` 写 `[wsl2]` 与 `networkingMode=mirrored`，再执行 `wsl --shutdown` | 在 MobAI "Integrations → API server" 勾选 "Allow external connections" |
| builder.json | 保持默认 `http://localhost:8686`；若此前把 `mobai.url` 写成 PC 名，"remove it or set it back" | `{ "mobai": { "url": "http://YOUR-PC-NAME.local:8686" } }` |
| 取主机名 | 不需要 | 在 WSL 执行 `hostname.exe` 得到 Windows 主机名，拼 `.local` |
| 验证 | 执行 `builder mobai ping`，上游说 "prints success" | 同左 |

mirrored 下首次执行 `builder dev flutter` 会 "rewrites Flutter's mobai-ios custom
device with the new URL, so flutter attach uses it too"，attach 与 builder 共用新地址。

## MOBAI_ACCESS_KEY 与 MOBAI_API_KEY（别混用）

| | `MOBAI_ACCESS_KEY` | `MOBAI_API_KEY` |
| --- | --- | --- |
| 存放位置 | **本地**环境变量或运行 builder 的目录下的 `.env`（先查 env 再查 `./.env`） | 仓库 GitHub Secret，执行 `gh secret set MOBAI_API_KEY` |
| 用途 | 本机 MobAI API server 设了 token 后的请求凭据（请求头 `X-API-Key`） | `builder ios share` 在 MobAI 云端开模拟器 |
| 生成处 | MobAI API server 设置 | MobAI App 的 Account → API Keys |
| 缺失后果 | 上游原文 "Without it every call fails with `invalid or missing API token`." | 模拟器共享不可用 |

Flutter 的 custom-device 命令从项目目录运行，读到的是同一份 `.env`。

## builder mobai 命令族

| 命令 | 用途 |
| --- | --- |
| `builder mobai ping` | 检查 builder 与 MobAI 的连通 |
| `builder mobai install <ipa>` | 把 IPA 装到设备 |
| `builder mobai run-debug <bundle-id>` | 带调试器附着启动 app |
| `builder mobai forward <device-port> <host-port>` | 把设备端口转发到本机 |

## 设备被占用（bridge in use）

上游原文："Builder claims the device before installing or launching an app."
若已在 MobAI app 里开启该设备的 bridge，builder 会报告设备在使用中：
先在 MobAI app 里停掉 bridge，再重跑原命令（如 `builder dev flutter`）。

## 真机 vs 云端模拟器：能力边界

| 能力 | 物理设备（MobAI 本地桥） | 云端模拟器（`builder ios share`） |
| --- | --- | --- |
| 热重载 | 仅真机支持（"no simulators"） | 不支持 |
| 呈现位置 | MobAI 设备列表 | MobAI 的 CI Devices 分组 |
| 存续 | 随会话 | 使用中驻留，闲置 30 分钟关闭；`--duration` 可调，Codemagic/Bitrise 上限 60 分钟 |
| 前置 | MobAI 运行 + 设备连接（有 token 时配 `MOBAI_ACCESS_KEY`） | 仓库 Secret `MOBAI_API_KEY`；MobAI 3.0 及以上任意账号免费 |
| 典型用法 | 日常开发热重载 | 编码代理（Claude Code、Codex、Cursor）驱动模拟器 |

登记设备时执行 `builder signing setup --devices-from-mobai`——该命令自动跳过模拟器与云真机农场设备。

## UDID 获取

- MobAI 设备信息中直接显示 UDID；
- Windows 上 iTunes 的设备页点击序列号可切换出 UDID。

## 排错小表

| 症状 | 首步 | 错误码 |
| --- | --- | --- |
| "No devices found" | 确认 MobAI 已启动、设备已连接；执行 `builder mobai ping` | 见 `ios-builder/references/troubleshooting.md` E1 |
| `invalid or missing API token` | 在运行目录 `.env` 写入 `MOBAI_ACCESS_KEY=your-mobai-api-token` | 见 `ios-builder/references/troubleshooting.md` E1 |
| WSL 连不上 `localhost:8686` | 按上文二方案择一配置后重试 | 见 `ios-builder/references/troubleshooting.md` E1 |
| 报告设备被占用 | 在 MobAI app 停 bridge 后重跑 builder | 见 `ios-builder/references/troubleshooting.md` E1 |
| 云端模拟器不出现 | 确认已配仓库 Secret `MOBAI_API_KEY`（`gh secret set MOBAI_API_KEY`）再执行 `builder ios share` | 无 E 码；见 `ios-builder/references/mobai-device-bridge.md` 的 API_KEY 对照表 |

## 相关文档

- Flutter 通道：`ios-builder/references/flutter-hot-reload.md`
- RN 通道：`ios-builder/references/react-native-hot-reload.md`
- 错误码手册：`ios-builder/references/troubleshooting.md`
