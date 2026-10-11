# Flutter 热重载（builder dev flutter）

数据截至 2026-09（ios-builder v0.11.0）。

适用于无 Mac 的 Flutter iOS 开发：远程 `builder ios build` 产出 IPA，经 MobAI 装到真机，
再由 `flutter attach` + 文件监听实现保存即热重载。**仅支持物理设备**，
上游原文 "Only physical iOS devices are supported (no simulators)"。设备通道配置见
`ios-builder/references/mobai-device-bridge.md`。

## 生命周期

```
builder ios build     →  远程构建，IPA 落 ./dist/
        ↓
builder dev flutter   →  经 MobAI 安装 IPA（询问是否重签）
        ↓
flutter attach        →  连上运行中的 app
        ↓
文件监听              →  存 .dart 自动 hot reload；终端按 R 为 hot restart
```

上游语义：attach 连上后 builder 还会先发一次 hot restart，确保跑的是最新代码
（"it also sends an initial hot restart to ensure your latest code is running"）。

## 首次 / 二次启动对照

| 场景 | 命令 | 说明 |
| --- | --- | --- |
| 首次 | `builder dev flutter` | 自动从 `dist/` 找 IPA，经 MobAI 安装并询问是否重签 |
| 复用已装 | `builder dev flutter --skip-install --bundle-id com.example.myapp.TEAMID` | 上游明确 "--bundle-id is required with --skip-install" |
| 重签后取 id | 用带 TeamID 后缀的新 bundle id | 重签产物如 `com.example.myapp.TEAMID`，Builder 在后续提示中预填，直接复制 |

重签需 iCloud 账号；上游建议在 icloud.com 新注册一个，不要用主账号。

## Flag 速查

| Flag | 默认 | 用途 |
| --- | --- | --- |
| `-d` / `--device` | 第一台可用设备（`mobai.device_id` 为空时） | 指定设备 |
| `--mobai-url` | `http://localhost:8686` | MobAI API 地址不符时覆盖 |
| `--ipa` | 自动从 `dist/` 检测 | 指定 IPA 路径 |
| `--no-watch` | 关（默认开启监听） | 禁用文件自动监听 |
| `--no-attach` | 关（默认直接 attach） | "print the flutter attach command instead of running it (useful for IDE integration)" |

## 文件监听默认值（builder.json `flutter.watch`）

| 键 | 默认 |
| --- | --- |
| `dirs` | `["lib"]` |
| `patterns` | `[".dart"]` |
| `ignore` | `[".g.dart", ".freezed.dart"]` |
| `debounce` | `100`（毫秒） |

- "Edit a .dart file and save - hot reload triggers automatically"；
- 生成文件 `.g.dart` / `.freezed.dart` 默认被忽略，这类改动不会被自动触发；
- 目录、模式、debounce 均可在 `builder.json` 配置（逐字段见
  `ios-builder/references/builder-json-schema.md`）。

## 何时必须重建（上游 "When to Rebuild"）

| 改动类型 | 处理 |
| --- | --- |
| 原生代码（Swift、Objective-C、Podfile、原生依赖） | 执行 `builder ios build` 并重装 |
| 仅 Dart | 不重建，文件监听自动 hot reload |
| 启动后看不到最近的 Dart 改动 | 在终端按 `R` 做 hot restart |

## --no-watch 与 --no-attach 的取舍

| 开关 | 何时用 | 代价 |
| --- | --- | --- |
| `--no-watch` | IDE 或外部工具自行触发 reload | 失去保存即重载；watcher 排错时上游建议 "Try running without --no-watch flag" |
| `--no-attach` | 把打印出的 flutter attach 命令交给 IDE 接管 | 本终端不再直接收发热重载按键 |

## KMP：没有热重载（勿路由到此通道）

共享 Kotlin 在构建期编译进 native framework，"there is no hot reload...
every code change needs a rebuild"。上游另有 `builder dev kmp`（别名 `kotlin`），
支持 `--logs` 与 `--skip-install --bundle-id <id>`；`builder.json` 键 `kmp.jdkVersion`（如
`"17"`，iOS 端 xcodebuild 的 run-script 阶段会调 Gradle，JDK 版本必须匹配），KMP 工程
`ios.path` 为 `iosApp/`。"Unsupported class file major version" 调 `kmp.jdkVersion`；
"SDK does not contain 'libarclite'" 升级 Kotlin 插件；app 秒退先跑 `builder dev kmp --logs`。

## 排错小表

| 症状 | 首步 | 错误码 |
| --- | --- | --- |
| "No devices found" | 执行 `builder mobai ping` | 见 `ios-builder/references/troubleshooting.md` E1 |
| App 起不来 / connection error | 先在设备上关掉 app 再跑 `builder dev flutter` | 见 `ios-builder/references/troubleshooting.md` E5 |
| 热重载不生效 | 确认 `--bundle-id` 带 TeamID 后缀 | 见 `ios-builder/references/troubleshooting.md` E5 |
| watcher 不触发 | 确认没有带 `--no-watch` 运行 | 见 `ios-builder/references/troubleshooting.md` E5 |
| 原生改动无效果 | `builder ios build` 后重装 | 见 `ios-builder/references/troubleshooting.md` E7 |
| builder 报设备被占用 | 在 MobAI app 里停掉 bridge 再重跑 | 见 `ios-builder/references/troubleshooting.md` E1 |

## 相关文档

- 设备通道与 WSL 网络：`ios-builder/references/mobai-device-bridge.md`
- RN 对照：`ios-builder/references/react-native-hot-reload.md`
- 错误码手册：`ios-builder/references/troubleshooting.md`
- 字段全表：`ios-builder/references/builder-json-schema.md`
