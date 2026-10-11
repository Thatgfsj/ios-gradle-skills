# flutter-hot-reload（设计文档）

⚠️ **本目录为设计文档，尚无代码。** 落地时要做成可用 `builder ios build` 真实构建的工程，
并加进 `.github/workflows/validate.yml`。可构建的最小模板见 `templates/flutter-starter/`。

## 目标

验证「Windows/Linux 上改 Dart，iPhone 上秒级生效」这条链路，并把踩到的坑固化成脚本与 E 码。

## 计划结构

```
flutter-hot-reload/
├── pubspec.yaml
├── lib/main.dart
├── ios/                      # flutter create --platforms=ios 生成，入库
├── builder.json              # ios.path="ios"，scheme="Runner"
└── README.md                 # 本文件被替换成实测记录
```

## 待验证矩阵

| # | 场景 | 命令 | 预期 | 记录 |
| --- | --- | --- | --- | --- |
| 1 | 首次接入 | `builder init` | 写出 `ios-build.yml` / `ios-share.yml` | 未测 |
| 2 | 出未签名包 | `builder ios build --unsigned` | `./dist/*.ipa` | 未测 |
| 3 | 装机 + 重签 | `builder dev flutter` | 提示重签，选择 iCloud 账号 | 未测 |
| 4 | 改 Dart 保存 | 无 | 自动 hot reload | 未测 |
| 5 | 二次启动 | `builder dev flutter --skip-install --bundle-id com.example.<app>.TEAMID` | 直接 attach | 未测 |
| 6 | 加原生插件 | `pubspec.yaml` 改依赖 → `builder ios build` | 必须重建才生效 | 未测 |
| 7 | WSL NAT | `mobai.url = http://<PC>.local:8686` + `MOBAI_ACCESS_KEY` | `builder mobai ping` 打印 success | 未测 |
| 8 | WSL mirrored | `.wslconfig` 设 `networkingMode=mirrored` | 保持默认 `http://localhost:8686` 即可 | 未测 |
| 9 | 模拟器共享 | `builder ios share`（需 `MOBAI_API_KEY` Secret） | MobAI CI Devices 里出现模拟器 | 未测 |
| 10 | 配额 | 连续 15 次构建 | 记录实际耗时与分钟数，回填 SKILL.md 配额段 | 未测 |

## 关键约束（来自上游文档，实测后要确认仍然成立）

- 热重载**只支持物理设备**；模拟器用 `builder ios share`。
- 重签会给 bundle id 追加 TeamID 后缀，`--skip-install --bundle-id` 必须写完整后缀值。
- 默认 watcher 只看 `lib/` 下的 `.dart`，忽略 `.g.dart` / `.freezed.dart`，debounce 100ms。
- 原生（Swift/ObjC/Podfile/原生插件）改动必须重建 IPA 再重装。

排错入口：`ios-builder/references/troubleshooting.md`（E1 / E5 / E7 / E8），
流程细节：`ios-builder/references/flutter-hot-reload.md`。
