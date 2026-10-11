# 排错手册（E1–E10）

数据截至 2026-09（ios-builder v0.11.0）。

先定位报错发生的**通道**（设备 / 产物 / 签名 / 热重载 / 配额 / 初始化）。每条含：现象（保留上游英文原文）→ 根因 → 预防 → 一键修复。千行失败日志先交给 `python ios-builder/scripts/ai/analyze_build_log.py`；其自带的 E 码映射若与本索引不一致，以本手册为准。

## 错误码索引

| 码 | 现象 | 通道 | 首条修复命令 |
| --- | --- | --- | --- |
| E1 | `No devices found` / `invalid or missing API token` / 设备被占用 | 设备（MobAI） | `builder mobai ping` |
| E2 | 构建结束但 `./dist/` 没有 IPA | 构建产物 | `python ios-builder/scripts/ai/analyze_build_log.py build.log` |
| E3 | 签名构建失败：证书 / 描述文件 | 签名 | `builder ios build --unsigned` |
| E4 | Signing set 缺 Secrets / 触达 Apple 上限 | 签名配置 | `python ios-builder/scripts/ops/check_signing_secrets.py --project /path/to/MyApp --distribution development` |
| E5 | Flutter 热重载连不上 / watcher 不触发 | 热重载（Flutter） | `builder mobai ping` |
| E6 | Metro 不通 / Fast Refresh 无效 | 热重载（RN） | `npx react-native start` |
| E7 | 原生改动未生效 | 重建判定 | `builder ios build` |
| E8 | 配额超限 / 90 分钟上限 | 配额 | `builder ios build --unsigned` |
| E9 | `builder.json` 缺失 / repo 检测失败 | 初始化 | `builder init` |
| E10 | 旧 workflow 拒绝 profile dispatch | workflow 通道 | `builder init` |
| E11 | workflow 非法：run 秒退、名字是文件路径、无日志 | Actions 解析 | `gh api repos/{o}/{r}/actions/runs/{id} --jq .name` |

### E1 设备通道：`No devices found` / 连不上 MobAI

- **现象**：报 `No devices found`；或 "Only physical iOS devices are supported
  (no simulators)"；或每次调用失败并显示 `invalid or missing API token`。
- **根因**：MobAI 未运行 / 设备未连接 / 拿模拟器当目标；WSL 下 API 不通（默认 `http://localhost:8686`，NAT 需 `.local` 或走 mirrored）；MobAI 设了 token 但环境与运行目录 `.env` 都没有 `MOBAI_ACCESS_KEY`（请求头 `X-API-Key`）。
- **预防**：热重载前先执行 `builder mobai ping`；网络二方案见
  `ios-builder/references/mobai-device-bridge.md`。
- **一键修复**（若报设备被占用：先在 MobAI app 里停掉 bridge 再重跑）：

```bash
builder mobai ping
```

### E2 构建结束但 `./dist/` 没有 IPA

- **现象**：`builder ios build`（含 `--unsigned`）后 `dist/` 无产物，artifact 步骤无文件可传。
- **根因**：多数是远程构建本身失败——隐藏 ref 快照不含被 `.gitignore` 的文件
  （`.env`、`GoogleService-Info.plist`、本地 `*.xcconfig`）；或 runner.sh 守卫拒绝：
  `Snapshot SHA mismatch; refusing to build different source`。
- **预防**：确认构建所需文件都进快照；同一工程勿并发两个构建互相改写快照。
- **一键修复**（先取日志再跑映射脚本）：

```bash
gh run view <id> --log > build.log
python ios-builder/scripts/ai/analyze_build_log.py build.log
```

### E3 证书 / 描述文件失败（签名构建）

- **现象**：签名路径的 `builder ios build` 失败；distribution profile 配 Debug 时
  runner "fails by name before compiling anything"；profile 不复用的原因只会是
  invalid / expired / certificate changed / devices changed / forced。
- **根因**：三件套 `IOS_CERTIFICATE` / `IOS_CERTIFICATE_PASSWORD` /
  `IOS_PROVISIONING_PROFILE` 与证书类型、`ios.configuration` 不匹配。
- **预防**：用 `builder signing setup` 重新生成证书与 profile 后再上传。
- **一键修复**（unsigned 能过 → 故障只在签名通道，转 E4）：

```bash
builder ios build --unsigned
```

### E4 Signing set 缺 Secrets / 触达 Apple 上限

- **现象**：错误点名缺少的 Secret；或到上限——上游描述为 at Apple's limit
  (2 Development, 3 Distribution)，报错指向 Portal；设备是 100 devices per
  membership year and never frees a slot。
- **根因**：按 distribution 分后缀的 set 少配（如 `IOS_CERTIFICATE_DEVELOPMENT`、`IOS_PROVISIONING_PROFILE_STORE`）；含 extension 缺第四件 `IOS_EXTENSION_PROFILES_<SET>`（无扩展也写 `{}`）；Codemagic/Bitrise 上 Builder 无法在构建前检查 Secrets。
- **预防**：切换 profile 前逐 distribution 校验；登记设备执行
  `builder signing setup --devices-from-mobai`（跳过模拟器与云农场）。
- **一键修复**：

```bash
python ios-builder/scripts/ops/check_signing_secrets.py --project /path/to/MyApp --distribution development
```

### E5 Flutter 热重载连不上 / watcher 不触发

- **现象**：App won't launch / connection error；"Hot reload not working"；
  "File watcher not triggering"（上游提示 "Try running without --no-watch flag"）。
- **根因**：设备上旧 app 实例没关；USB / MobAI 掉线；`--bundle-id` 没带重签后的
  TeamID 后缀；watcher 默认只盯 `lib/` 的 `.dart`，且忽略 `.g.dart` / `.freezed.dart`。
- **预防**：attach 前先在设备上关掉 app；拔插 USB 重连设备，再重启 MobAI。
- **一键修复**（连上后仍看不到 Dart 改动就在终端按 `R` 做 hot restart）：

```bash
builder mobai ping
builder dev flutter --skip-install --bundle-id com.example.myapp.TEAMID
```

### E6 Metro 不通（React Native）

- **现象**："Metro not starting" 或 App 连不上 Metro；上游检查项：Ensure Node.js
  and React Native CLI are installed / Device must be on the same WiFi network as
  the computer running Metro / Verify the Metro port is correct (default: 8081)。
- **根因**：Node.js/RN CLI 缺失；手机与 Metro 主机不同 WiFi；8081 被占；WSL mirrored 下 Hyper-V 防火墙默认拦手机入站。
- **预防**：端口冲突执行 `builder dev rn --metro-port 8082`；防火墙规则与 Fast Refresh 步骤（按 `d` 开 dev menu → 开 Fast Refresh → 按 `r` reload）见 `ios-builder/references/react-native-hot-reload.md`。
- **一键修复**（本地单独验证 Metro；起不来即 Metro/网络问题，与 builder 无关）：

```bash
npx react-native start
```

### E7 原生改动未生效

- **现象**：改了 Swift / Objective-C / Podfile / 原生模块（Flutter 原生依赖、RN
  原生模块）后设备行为不变。
- **根因**：热重载只替换 Dart/JS 运行时代码；原生代码已编译进 IPA。上游口径：Native code changes 需 "Run builder ios build and reinstall"。
- **预防**：仅 Dart/JS 改动不重建；重建矩阵见 `ios-builder/references/flutter-hot-reload.md` 与 `ios-builder/references/react-native-hot-reload.md`。
- **一键修复**（重建并重装，会重新询问是否重签；RN 把第二行换成 `builder dev rn`）：

```bash
builder ios build
builder dev flutter
```

### E8 配额超限 / 90 分钟上限

- **现象**：Actions 分钟耗尽或工作流被终止：free-plan 上限 90 分钟（含 setup 与
  编译）；冷启动 RN/Expo 构建在免费 runner 上要 30–60 分钟。
- **先确认仓库可见性**：GitHub 定价页原文 "Minutes are free for public repositories."——
  **public 仓库的标准 runner（含 macOS）不计费**，别对 public 仓库讲额度；10 倍率只作用于私有仓库计费分钟。
- **根因**：GitHub Free 私有仓库 2,000 metered 分钟/月，macOS 计费与 Linux 不同；本仓库按常公布的 10 倍估算 ≈200 macOS 分钟 ≈15–20 次 IPA 构建/月——**估算值**，倍率以 GitHub billing 文档与 https://github.com/runner-images 核对。
- **根因（续）**：替代通道 Codemagic personal 500 macOS M2 分钟/月（Teams 无）、Bitrise Hobby 300 credits/月一个私有 app；"The approximate 800-minute target is not a guaranteed combined quota"。额度跟账号走，Builder 之外的构建同样消耗，也不聚合账单或不兜底零消费。
- **预防**：当月第 10 次以上构建前提醒用户；优先 `--unsigned`（省 1–2 分钟）。
- **一键修复**（低开销重试）：

```bash
builder ios build --unsigned
```

### E9 `builder.json` 缺失 / repo 检测失败

- **现象**：runner 报 `仓库缺少 builder.json`（本仓库 workflow 模板的中文错误串）；
  或 `builder init` 检测 repo 失败。
- **根因**：`builder.json` 未入库，或 `github.owner/repo`、`ios.path`、`ios.scheme`
  不对（托管 Expo 记 `"ios"`，KMP 记 `iosApp/`）。
- **预防**：配置从 `builder/builder.template.json` 派生；新项目用脚手架
  `python ios-builder/scripts/init_ios_project.py`（`--framework swiftui|flutter|react-native`、`--unsigned`、`-o/--output`、`--interactive`，退出码 0/1/2/3）；参照 `examples/basic-swiftui-app`（scheme BasicApp、`ios.path` 为 `"."`、unsigned）。
- **一键修复**（检测失败则手填 `builder.json`，再用
  `python ios-builder/scripts/ai/patch_builder_config.py` 微调）：

```bash
builder init
```

### E10 旧 workflow 拒绝 profile dispatch

- **现象**：按 profile 触发被拒——需要声明了 `profile` input 的 workflow 版本。
- **根因**：仓库里的 `.github/workflows/ios-build.yml` 早于当前 CLI，inputs 落后。
- **预防**：升级 builder 后重新生成 workflow 并推默认分支；模板差异见文末注记。
- **一键修复**（刷新后重触发；GitHub API 不通可打 tag `git tag ios-build/<name> && git push origin ios-build/<name>`；批量触发用 `python ios-builder/scripts/ops/trigger_build.py`，参数见其 Usage）：

```bash
builder init
```

### E11 workflow 非法（Actions 秒退、没有日志）

- **现象**：push 后 run 几秒内 `conclusion=failure`；**run 的 `name` 显示成
  `.github/workflows/<file>.yml` 而不是文件里 `name:` 的值**；
  `GET /actions/runs/{id}/jobs` 返回空数组；`gh run view --log` 没有任何日志；
  check-run 的 `output.annotations` 也是空的——GitHub 不把解析错误写进日志。
- **根因**：Actions 的校验比 YAML 语法严格得多（本地 js-yaml / PyYAML 都会通过）。实测两类非法写法：
  1. `if:` 表达式里引用 `secrets`。官方 contexts 可用性表：
     `jobs.<job_id>.steps.if` 只给 github、needs、strategy、matrix、job、runner、env、vars、steps、inputs；
     `jobs.<job_id>.if` 同样没有 secrets。写 `if: ${{ secrets.X != '' }}` → 整份 workflow 解析失败。
  2. `needs:` 指向本文件里不存在的 job（拆文件做探针时最容易自己踩）。
- **正确写法**：secrets 通过步骤的 `env:` 映射传进脚本，在脚本里判空分支；
  作业级开关放仓库 **Variables**（`vars.ENABLE_SIGNED_BUILD == 'true'`），Variables 在 `if` 里可见。
- **定位手段**：探针 workflow 二分——见 `workflow-yml-anatomy.md`「解析失败的二分定位」。
- **首条命令**：

```bash
gh api repos/{owner}/{repo}/actions/runs/{run_id} --jq '.name'
# 输出等于 workflow 文件路径 => workflow 解析失败，跟构建内容无关
```

## 附：upload / 快照速查（不占 E 码）

| 现象 | 根因 | 处理 |
| --- | --- | --- |
| `Build numbers must increase`（ITMS-90189） | 同一 version 下 build number 未递增 | 递增后重跑 `builder ios upload` |
| `Missing Compliance` | 出口合规未回答 | `ITSAppUsesNonExemptEncryption=false` 时 `builder ios upload --wait` 自动回答，否则传 `--no-encryption` |
| 提交被拒并提示 "drop --unsigned" | `--unsigned` 与 `--submit` 互斥 | 二者去掉一个再执行 `builder ios upload` |
| 快照隐藏 ref 残留 | `refs/ios-builder/jobs/<build-id>` 占远端 | `git push origin --delete refs/ios-builder/jobs/<build-id>` |
| `xcodebuild: error: Unable to read project 'X.xcodeproj'` / `Failed to load project … for an unknown reason` | **工程文件本身**坏掉：手写或渲染出的 `project.pbxproj` 缺顶层 `rootObject`、对象 ID 悬空、`section` 不配对（Xcode 不会告诉你缺哪个键） | `python ios-builder/scripts/ops/lint_skill.py`（结构校验）＋ `python ios-builder/scripts/ops/selftest_lint.py`（确认校验本身有效） |

## 本仓库与上游差异注记

- `builder/ios-build.yml.template` 钉 `runs-on: macos-15`；上游生成为 `macos-latest`。
- `仓库缺少 builder.json` 是本仓库模板中文文案；macOS 10 倍计费与
  `reactNative.metroPort`（上游 README 未文档化）均按本手册口径标注。
- 提交文档改动前跑 `python ios-builder/scripts/ops/lint_skill.py` 校验 E 码引用。
- 改过 `lint_skill.py` 的工程校验逻辑后，再跑一次 `selftest_lint.py`：
  正则写错会让检查静默空转（本项目踩过：`BlueprintIdentifier="X"` 少了等号两侧空格，
  三条 scheme 检查全都“通过”却什么都没校验）。
