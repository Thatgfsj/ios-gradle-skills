# basic-swiftui-app

✅ **真实可构建**：本目录由 `ios-builder/scripts/init_ios_project.py` 渲染生成
（app 名 `BasicApp`，`--unsigned`），并在 `.github/workflows/validate.yml` 的
`build-example` job 里每次提交都编译一次并产出 Unsigned IPA。

## 目录

```
basic-swiftui-app/
├── BasicApp/                       # 源码：@main App + ContentView + Assets.xcassets
├── BasicApp.xcodeproj/             # 手写 pbxproj（objectVersion 56，Xcode 14+ 可读）
│   └── xcshareddata/xcschemes/BasicApp.xcscheme   # 共享 scheme，headless CI 依赖它
├── builder.json                    # ios.path="."，scheme="BasicApp"，signing=false
├── .github/workflows/ios-build.yml # 由 builder/ios-build.yml.template 渲染
└── .gitignore
```

## 本机怎么验（可选，需要 Mac）

```bash
xcodebuild -list -project BasicApp.xcodeproj
xcodebuild build -project BasicApp.xcodeproj -scheme BasicApp \
  -configuration Debug -sdk iphoneos \
  -destination "generic/platform=iOS" -derivedDataPath /tmp/DD \
  CODE_SIGNING_ALLOWED=NO CODE_SIGNING_REQUIRED=NO CODE_SIGN_IDENTITY=""
```

CI 用的就是这一条链路（等价写法见 `builder/ios-build.yml.template` 的 `Build IPA` step）。

## 远程怎么打（无需 Mac）

```bash
cd examples/basic-swiftui-app
# builder.json 里的 github.owner/repo 是占位值，先改成自己的仓库：
python ../../ios-builder/scripts/ai/patch_builder_config.py --project . \
  --owner <你的 GitHub 用户> --repo <你的仓库> --write
git init -q && git add -A && git commit -qm "init" && git push
builder auth github
builder init
builder ios build --unsigned          # IPA 落在 ./dist/
```

## 装机

未签名 IPA 用 MobAI 安装并重签（免费 Apple ID 即可）：

```bash
builder mobai install dist/BasicApp-unsigned.ipa
```

重签后 bundle id 形如 `com.example.basicapp.TEAMID`；再跑 attach 时要带上这个后缀：

```bash
builder dev flutter --skip-install --bundle-id com.example.basicapp.TEAMID   # Flutter 工程同理
```

## 设计约束

- **不含第三方依赖**：没有 SPM 包、没有 Podfile，CI 冷启动只编译两个 Swift 文件，
  省配额，也避免依赖解析失败干扰对通道本身的判断。
- **只用 iOS 17 API**：`@Observable` / `NavigationStack` / `LabeledContent` / `#Preview`。
- **`SWIFT_VERSION = 6.0`**：Swift 6.2 语言模式要 Xcode 26+，而镜像可能停在 16.x；
  写 6.0 保证两个版本的工具链都能编译。要吃到 6.2 就用
  `init_ios_project.py --swift-version 6.2` 重新生成。
- **Info.plist 由 build settings 生成**（`GENERATE_INFOPLIST_FILE = YES`），
  所以目录里看不到 plist 文件；bundle id 在 `PRODUCT_BUNDLE_IDENTIFIER`。
