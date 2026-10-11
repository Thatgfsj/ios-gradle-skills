# rn-hot-reload（设计文档）

⚠️ **本目录为设计文档，尚无代码。** 落地后必须能被 `.github/workflows/validate.yml` 真实构建。
配置模板见 `templates/react-native-starter/`。

## 目标

验证「本机起 Metro、iPhone 远程取包」的完整回路：IPA 由 GitHub Actions 产出，
JS 由本地 Metro 提供，改动即 Fast Refresh，无需重装。

## 计划结构

```
rn-hot-reload/
├── App.tsx / index.js
├── package.json              # RN CLI 生成，记录 packageManager 供 runner 选包管理器
├── ios/                      # Podfile + <App>.xcodeproj，入库
├── builder.json              # ios.path="ios"，scheme="<App>"，configuration="Debug"
└── README.md                 # 本文件替换成实测记录
```

## 待验证矩阵

| # | 场景 | 命令 | 预期 | 记录 |
| --- | --- | --- | --- | --- |
| 1 | 生成宿主工程 | `npx @react-native-community/cli init` | `ios/` 出现 xcodeproj | 未测 |
| 2 | 出 Debug IPA | `builder ios build --unsigned` | 产物从 Metro 取 JS（不烤 bundle） | 未测 |
| 3 | 热重载 | `builder dev rn` | 自动起 Metro、装机、配置 Metro URL | 未测 |
| 4 | 端口冲突 | `builder dev rn --metro-port 8082` | 设备指向新端口 | 未测 |
| 5 | 二次启动 | `builder dev rn --skip-install --bundle-id com.example.<app>.TEAMID` | 直接 attach | 未测 |
| 6 | 出独立包 | `builder.json` 里 `ios.configuration = "Release"` 后重建 | JS bundle 烤进 IPA | 未测 |
| 7 | 原生模块 | 加依赖 → 重建 | 必须重建才生效 | 未测 |
| 8 | WSL | mirrored 网络 | Hyper-V 防火墙默认挡住手机访问 Metro，需放行端口 | 未测 |
| 9 | 包管理器 | 分别用 npm / Yarn / pnpm / Bun | runner 按 `packageManager` 或 lockfile 选择 | 未测 |
| 10 | 配额 | 一次 RN 冷启动构建 | 实测分钟数（上游称 30-60 分钟），回填 SKILL.md 配额段 | 未测 |

## 关键约束（来自上游文档，实测后要确认仍然成立）

- 手机与跑 Metro 的电脑必须在**同一 WiFi**。
- Fast Refresh 需在 dev menu 里开启（摇一摇或 Metro 终端按 `d`），reload 用 `r`。
- `ios.configuration` 默认 `Debug`：产物依赖 Metro，不能脱离开发机独立运行。
- Expo 项目：managed 形态下 `ios/` 不入库，由 runner 跑 `expo prebuild --platform ios --no-install`；
  必须在 `app.json` 的 `expo.ios.bundleIdentifier`（或 `app.config.js/ts` 的 `ios.bundleIdentifier`）
  里给定 bundle id，否则构建立即失败并点名缺哪个配置。

排错入口：`ios-builder/references/troubleshooting.md`（E2 / E6 / E7 / E8），
流程细节：`ios-builder/references/react-native-hot-reload.md`。
