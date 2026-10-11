# flutter-starter

Flutter 工程模板，iOS 侧通过 **远程 xcodebuild** 构建（`builder ios build`），
热重载走 `builder dev flutter` + MobAI。

## 本模板包含什么

```
flutter-starter/
├── pubspec.yaml              # Flutter 依赖声明
├── lib/main.dart             # 最小可运行 App
├── builder.json              # ios.path = "ios"，scheme = "Runner"
├── github-workflows/         # 复制为 .github/workflows/ios-build.yml
└── gitignore                 # 复制为 .gitignore
```

模板**不带 `ios/` 目录**——Flutter 的 iOS 宿主工程由 SDK 自己生成，
手写 `Runner.xcodeproj` 会随 Flutter 版本漂移。

## 使用步骤

```bash
# 1. 用脚手架生成工程骨架
python ../../ios-builder/scripts/init_ios_project.py MyApp ~/projects --framework flutter

# 2. 生成 iOS 宿主工程（关键一步）
cd ~/projects/MyApp
flutter create --platforms=ios --org com.example --project-name my_app .

# 3. 首次接入远程构建
builder auth github
builder init

# 4. 打 Unsigned IPA
builder ios build --unsigned

# 5. 真机热重载（需 Windows/macOS 上运行 MobAI 并连接 iPhone）
builder dev flutter
```

## 何时必须重建

| 变更内容 | 处理方式 |
| --- | --- |
| `lib/**/*.dart` | 文件监听自动 hot reload，无需重建 |
| `pubspec.yaml` 新增插件（含原生代码） | 必须 `builder ios build` 重建 |
| `ios/` 下 Swift/ObjC/Podfile 改动 | 必须重建 |
| Flutter SDK 升级 | 必须重建（`flutter create .` 重跑一次） |

详见 `../../ios-builder/references/flutter-hot-reload.md`。
