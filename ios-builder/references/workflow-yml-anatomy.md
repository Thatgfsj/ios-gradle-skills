# ios-build.yml 逐段解读

数据截至 2026-09（ios-builder v0.11.0）。`builder init` 在项目仓库写 `.github/workflows/ios-build.yml`
（另有 `ios-share.yml`）。本文拆上游结构，对照物是本仓库的 `builder/ios-build.yml.template`；
差异汇总在文末。

## 头部与触发

| 项 | 值 |
| --- | --- |
| `name` | `iOS Build` |
| `run-name` | `iOS Build ${{ inputs.build_id \|\| github.ref_name }}` |
| 触发 1 | `workflow_dispatch`（CLI 可达时的主通道） |
| 触发 2 | `push: tags: ['ios-build/*']`（仅 Git 通道） |
| `permissions` | `contents: write # deletes the trigger tag` |
| `runs-on` | `macos-latest`（上游未用 macos-15；本仓库模板固定 `macos-15`，见文末。2026-10-11 CI 实测 `macos-15` 可用，预装 Xcode 26.3 / iPhoneOS 26.2 SDK） |
| `timeout-minutes` | `90`，模板注释原由："a cold React Native/Expo build on the free runner takes 30-60 minutes"；GitHub 免费档对 workflow 同样封顶 90 分钟（含 setup 与编译） |

## 10 个 workflow_dispatch inputs

`workflow_dispatch` 最多接受 10 个 input，上游把 profile 相关字段打包进**单个** JSON input——
原注释口径："so the workflow stays under the ten-input limit of workflow_dispatch"。
builder CLI 按名字传参；本仓库模板注释：名字对不上就报 `Unknown input: xxx`。

| # | input | 类型 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| 1 | `build_id` | string | 必填 | CLI 分配的构建 id |
| 2 | `snapshot_ref` | string | `""` | 工作区快照所在隐藏 ref；空 = 构建检出的提交 |
| 3 | `ios_path` | string | `"."` | 覆盖 `ios.path` |
| 4 | `scheme` | string | `""` | 覆盖 `ios.scheme` |
| 5 | `use_signing` | boolean | `false` | 用仓库 Secrets 签名 |
| 6 | `configuration` | string | `"Debug"` | Xcode configuration |
| 7 | `flutter_version` | string | `""` | 锁定 Flutter 版本 |
| 8 | `jdk_version` | string | `"17"` | KMP 用 JDK |
| 9 | `profile` | string | `"{}"` | "Selected builder.json profile as JSON: {\"name\": \"...\", \"env\": {...}, \"distribution\": \"...\"}" |
| 10 | `build_number` | string | `""` | "CFBundleVersion to stamp on the build: N, or X.Y.Z+N to set the marketing version too" |

旧版本 workflow 没有 `profile` input——升级 CLI 后执行 `builder init` 刷新 workflow 文件，
否则带 `--profile` 的 dispatch 会被拒。

## 步骤流水线（上游原名与顺序，按阶段分组）

| 阶段 | 步骤（verbatim） | 说明 |
| --- | --- | --- |
| 检出 | Checkout repository（actions/checkout@v7）→ Checkout working-tree snapshot → Resolve parameters（id: `params`，用 jq 读 builder.json） | 快照步骤仅当 `inputs.snapshot_ref != ''` 执行 |
| 工具链 | Setup Xcode（maxim-lobanov/setup-xcode@v1，`xcode-version: latest-stable`）→ Restore DerivedData cache（actions/cache/restore@v6）→ Detect project type → Materialize missing xcconfig files → Generate Xcode project (XcodeGen) → Check base configuration files | Detect project type 决定后续分支步骤是否出现 |
| 依赖 | Setup Flutter（subosito/flutter-action@v2，if flutter）→ Flutter pub get → Resolve JS toolchain → Setup Node.js（actions/setup-node@v7）→ Restore node_modules cache（actions/cache@v6）→ Install JS dependencies → Expo prebuild → Setup JDK（actions/setup-java@v6）→ Setup Gradle（gradle/actions/setup-gradle@v6）→ Restore Pods cache（actions/cache@v6） | 各形态只走自己的子链，见 `ios-builder/references/framework-detection.md` |
| 签名 | Install certificate and provisioning profile | 静态步骤 + 条件门控，见下节 |
| 构建 | Build IPA | |
| 产物 | Upload IPA artifact → Check for DerivedData → Save DerivedData cache（actions/cache/save@v6） | 产物步骤 verbatim 见下 |
| 清理 | Cleanup signing → Build summary → Delete trigger tag | Cleanup 用 `if: always()` 兜底 |

## 签名的两个注入点

- "Install certificate and provisioning profile" 是**静态写进模板**的步骤，靠
  `if: steps.params.outputs.use_signing == 'true'` 门控，而非每次构建前动态注入。
- "Cleanup signing" 条件为 `if: always() && steps.params.outputs.use_signing == 'true'`，删除 `$KEYCHAIN_PATH`——构建失败也会执行。
- 按 distribution 选 Secret 集合：`""` → legacy 无后缀；`development` → `*_DEVELOPMENT`；
  `ad-hoc`/`internal` → `*_AD_HOC`；`store` → `*_STORE`；`enterprise` → `*_ENTERPRISE`。
  全表见 `.github/secrets.example.md`。
- 含 extension 时每个 set 多第四件 `IOS_EXTENSION_PROFILES_<SET>`（JSON object，bundle id → base64
  profile；无扩展写 `{}`）。
- 运行时校验（上游原文）："The runner checks that the profile in the set is of the requested type
  and fails by name before compiling anything, and a distribution profile refuses a Debug configuration."

## Resolve parameters 的 jq 口径（verbatim 摘录）

```text
param use_signing "$IN_USE_SIGNING" '(if $p != "" then ((.profiles[$p].distribution // "") != "") else .ios.signing end)' 'false'
param configuration ... '(.profiles[$p].configuration // (if $p != "" and (.profiles[$p].distribution // "") != "" then (if .profiles[$p].distribution == "development" then "Debug" else "Release" end) else .ios.configuration end))' 'Debug'
param flutter_version "$IN_FLUTTER_VERSION" '.flutter.version' ''
param jdk_version ... '.kmp.jdkVersion' '17'
param build_number "$IN_BUILD_NUMBER" '""' ''
param ios_path ... '.ios.path' '.'
```

解读：选中 profile 且 `distribution` 非空 → `use_signing=true`；`configuration` 由 distribution 推导
（development → Debug，其余 → Release），未签名 profile 回落 `ios.configuration`；显式 input 优先于 builder.json。

## 产物步骤（verbatim）

```yaml
- name: Upload IPA artifact
  uses: actions/upload-artifact@v7
  with:
    name: ipa
    path: build/*.ipa
    retention-days: 7
    if-no-files-found: error
```

CLI 把 IPA 下载到本地 `./dist/`。

## 快照与隐藏 ref

- `builder ios build` 构建磁盘上的现状而非最近一次提交：uncommitted 与 untracked 文件都会进快照。
- 快照是一次性提交，推到隐藏 ref `refs/ios-builder/jobs/<build-id>`（不在 `refs/heads` 下，因此不触发 push 事件）；
  不建分支，也不会代为提交任何代码。
- `.gitignore` 依然生效：`.env`、`GoogleService-Info.plist` 这类被忽略的文件**不会**出现在构建里。
- 结束后清理：`git push origin --delete refs/ios-builder/jobs/BUILD_ID`。
- 本地 `expo prebuild` 残留的 `ios/` 不会被上传（managed 项目已 gitignore 它）。
- 私钥、p12、编码后的副本一律留在 Git 与快照之外。

## 仅 Git 触发（GitHub API 不可达时）

```bash
git tag ios-build/my-build && git push origin ios-build/my-build   # IPA
git tag ios-share/my-build && git push origin ios-share/my-build   # 模拟器共享
```

- "Build settings come from builder.json in the tagged commit (ios.path, ios.scheme, ios.signing,
  ios.configuration, flutter.version, kmp.jdkVersion)"。
- 运行结束时 tag 被删除（`permissions: contents: write` 就是为这一步）。
- "A tag carries no flags, so a tagged IPA build cannot pick a profile per run; it applies the
  profile named by defaultProfile, if there is one."

## 缓存三件套

| 缓存 | 步骤 | 恢复/保存 | 收益 |
| --- | --- | --- | --- |
| DerivedData | Restore DerivedData cache / Check for DerivedData / Save DerivedData cache | restore@v6 + save@v6 分离，便于失败也保存 | 增量编译提速 |
| node_modules | Restore node_modules cache | actions/cache@v6 | RN/Expo JS 依赖 |
| Pods | Restore Pods cache | actions/cache@v6 | CocoaPods |

## 本仓库模板与上游的差异

1. **runner**：`builder/ios-build.yml.template` 固定 `runs-on: macos-15`，上游用 `macos-latest`。
   取舍：`macos-latest` 会随镜像迁移改变预装 Xcode，`macos-15` 可复现；label 不可用时改回 `macos-latest`。
2. **精简主链路**：本模板只保留原生 SwiftUI 路径（无 Flutter/RN/Expo/Pods/XcodeGen/DerivedData 缓存分支），
   上游权威模板约 69 KB；两者定位不同——本模板用于无 CLI 手工接入与 diff 校验。
3. **10 个 inputs 同名同序**：刻意与上游一致，保证 `builder` CLI 照常传参。
4. **签名步骤覆盖**：本模板演示 legacy + development/store 两组；上游按全部 distribution 分 set，
   并含 extension 第四件。
5. **actions 版本**：与上游 v0.11.0 一致——checkout@v7、setup-node@v7、setup-java@v6、
   gradle/actions/setup-gradle@v6、cache@v6、upload-artifact@v7。
6. 上游升级后在项目仓库执行 `builder init` 刷新 workflow（发布说明："Existing repositories: run
   builder init once to refresh the workflow files."）。

## 表达式上下文与解析失败（2026-10-11 真实 Tauri iOS workflow 实测）

GitHub 对 workflow 的校验分三层，前两层的通过**不代表**能跑：

| 层 | 谁能查 | 覆盖什么 |
| --- | --- | --- |
| YAML 语法 | 本地 `js-yaml` / `pyyaml` | 缩进、重复键、非法字符 |
| Actions schema | 只有 Actions 自己 | `if:` 可用上下文、`needs:` 指向存在的 job、input 类型 |
| Shell/构建 | 跑起来才知道 | 路径、scheme、签名 |

已验证的两条 schema 级红线：

1. **`if:` 里不能出现 `secrets`**（`jobs.<job_id>.if` 与 `jobs.<job_id>.steps.if` 都不行）。
   steps.if 的可用上下文：github、needs、strategy、matrix、job、runner、env、vars、steps、inputs。
2. **`needs:` 必须指向同一文件里存在的 job**；把某个 job 单独摘出来做实验时，
   要么删掉 `needs:`，要么补一个 stub job 顶着，否则实验本身也"非法"，白跑一轮。

### 解析失败的识别（无日志时的判据）

```bash
gh api repos/{owner}/{repo}/actions/runs/{RUN_ID} --jq '.name'
# 名字 == workflow 文件路径  =>  解析失败，与构建内容无关
gh api repos/{owner}/{repo}/actions/runs/{RUN_ID}/jobs --jq '.jobs | length'
# 0  =>  一个 job 都没实例化，进一步确认在解析层而不是构建层
```

### 解析失败的二分定位

思路：把可疑片段各自写成**只监听自己路径**的探针 workflow，一次提交全投，
一轮就能读出"哪一段非法"；探针里的 macOS runner 一律换成 ubuntu，几秒出结论，
不占真机额度。

```yaml
# .github/workflows/ios-probe-4.yml —— 只测 ios-unsigned 这个 job 能不能被解析
name: PROBE-4
on:
  push:
    paths: [".github/workflows/ios-probe-4.yml"]   # 关键：只被自己触发
permissions:
  contents: read
jobs:
  _stub:                                           # 给 needs 一个真实存在的目标
    runs-on: ubuntu-latest
    steps: [{ run: echo stub }]
  ios-unsigned:
    needs: _stub
    runs-on: ubuntu-latest                         # 解析检查不需要真机
```

按 `gh run list --json name` 读结论：显示 `PROBE-4` = 该段合法；显示文件路径 = 该段非法。
定位到 job 后再按 step 切第二轮。**探针文件用完必须删掉**：Git Data API 的删除条目
（`sha: null`）只能对**当前 tree 里存在**的路径使用，重复删除会返回
`GitRPC::BadObjectState`。

排错入口：`ios-builder/references/troubleshooting.md`；签名流程：`ios-builder/references/code-signing.md`。
