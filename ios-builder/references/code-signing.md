# iOS 代码签名

数据截至 2026-09（ios-builder v0.11.0）。Secret **名称全表**在 `.github/secrets.example.md`，本文不重复抄录，
只讲三条路径、base64 编码、自动 provisioning 检查与降级方案。

## 前提

- 默认构建**不签名**；签名构建需要 Apple 证书 + 描述文件，且"you do not need a Mac to create either one"。
- 需要付费的 Apple Developer Program 成员身份（Apple 只向付费账号签发证书）。没有付费账号 → 走 A′ 降级。

| 路径 | 何时用 | 入口 | Secrets 归属 |
| --- | --- | --- | --- |
| A legacy 三件套 | 不选 profile 且 `ios.signing: true` | 自备 .p12 + .mobileprovision | 无后缀三件套 |
| B 自动 setup | 有 App Store Connect API key | `builder signing setup` | 按 distribution 分后缀 |
| C Portal 手工 | 自管证书 / 不走 CLI 自动化 | `builder signing csr` 起步 | 按描述文件类型归 set |
| A′ 无账号降级 | 无付费开发者账号 | `builder ios build --unsigned` | 不需要任何 Secret |

## 路径 B 前置：ASC API key

- 创建位置：App Store Connect > Users and Access > Integrations > App Store Connect API > **Team Keys**，
  角色 Admin；App Manager 仅在授予 "Access to Certificates, Identifiers & Profiles" 时也可用；
  Developer 角色的 key 能上传构建，但**不能**创建证书。
- 执行 `builder auth apple --issuer-id <id> --key-id <id> --key ~/Downloads/AuthKey_<KEYID>.p8`。
- 无 keychain 的机器（CI、agent）改用环境变量 `ASC_ISSUER_ID`、`ASC_KEY_ID`、`ASC_KEY_PATH`（或 `ASC_PRIVATE_KEY`）。
- 执行 `builder auth status` 查看状态；`builder auth logout apple` 移除。

## 路径 B：builder signing setup（推荐，分 set）

```bash
builder signing setup --devices-from-mobai     # 生成 development set
builder signing setup --distribution store     # 生成 store set
```

按序执行六步（语义按上游 README 转述）：

1. bundle id 未注册则注册 App ID。bundle id 来源优先级：`--bundle-id` > `builder.json` 的 `ios.bundleId` > `./dist/` 里最新 IPA。
2. 签发证书：development 用 Apple Development；ad-hoc/store 用 Apple Distribution。密钥本地生成
   `ios-signing-<distribution>.key`；`--key` 复用既有密钥，旧命名 `ios-signing.key` 会被认领；
   **从不吊销**任何证书——撞到 Apple 上限（2 Development / 3 Distribution）时错误信息会直接点名。
3. 登记设备：`--device <udid>`（可重复）+ `--devices-from-mobai`（只收实体设备，跳过模拟器与 cloud farm
   设备）。development/ad-hoc 必须有设备，store 不需要。Apple 每会员年允许 100 台。
4. 创建描述文件，命名 "Builder <distribution> <bundle id>"；已有 ACTIVE、未过期、证书与设备一致的会复用，
   否则删除重建（原因会打印：invalid / expired / certificate changed / devices changed / forced）。
5. 把 `ios-signing-<distribution>.key`、`.p12`、`Builder-<distribution>-<bundle id>.mobileprovision`
   写入 `--out-dir`（默认 `"."`），上传该 set 的 GitHub Secrets；把 `distribution` 写进 builder.json 的
   该 profile，**不动** `defaultProfile`；`--out-dir` 非默认时记录为 `signing.dir`。
6. 打印 Secret 名与取值来源（.p12 base64、口令、.mobileprovision base64），便于粘到 Codemagic/Bitrise。

要点：上传目标恒为 `builder.json` 里的仓库；失败时打印错误、文件照写、退出码非零。
可用 flags：`--yes`（无终端时必需；此时 .p12 口令自动生成并只打印一次，除非给 `--password`）、`--json`、
`--force`、`--name <profile>`、`--bundle-id`、`--extension-profile`、`--certificate`、`--profile`、`--out-dir`、`--key`。

## 路径 A：legacy 三件套

上游原文："Legacy: sign builds that select no profile, with the unsuffixed IOS_CERTIFICATE,
IOS_CERTIFICATE_PASSWORD and IOS_PROVISIONING_PROFILE secrets. Profiles ignore it"。

- 即 `ios.signing: true` 且既无 `--profile` 也无 `defaultProfile` 时生效。
- 本仓库 `builder/builder.template.json` 默认保留这条路径（`"signing": false` 表示未启用）。
- 三件的名称/内容/来源见 `.github/secrets.example.md`；运行时映射见 `ios-builder/references/workflow-yml-anatomy.md`。

## 路径 C：Portal 手工（csr → cer → p12 → profile）

1. 执行 `builder signing csr`：询问姓名/邮箱，写出 `ios-signing.key` + `ios-signing.csr`。
2. Portal > Certificates：上传 `.csr`，下载 `.cer`。开发到真机（配登记设备）选 Apple Development；
   App Store/Ad Hoc 选 Apple Distribution——**TestFlight/App Store 上传必须 Apple Distribution + App Store 描述文件**。
3. 执行 `builder signing p12 --certificate development.cer --key ios-signing.key [--out]`。
4. Portal 登记 Devices、创建 Profiles（iOS App Development / Ad Hoc / App Store）。UDID 获取：MobAI 内直接显示；
   Windows 上 iTunes 点序列号可显示。
5. 执行 `builder signing setup --certificate ios-signing.p12 --profile MyApp.mobileprovision` 上传对应 set。
   也可以 `.cer` + 私钥直接进 setup：`builder signing setup --certificate development.cer --key ios-signing.key --profile MyApp.mobileprovision`
   ——自动组装 p12 并存为 `ios-signing-<distribution>.p12`。

描述文件类型决定该 set 写入的 distribution 与导出方式（development / ad-hoc / enterprise / store）。
enterprise（In-house）只有 Portal 手工路径能建（见 `.github/secrets.example.md` 的表）。

## base64 编码（通用编码步骤，非上游引文）

```bash
# macOS
base64 -i ios-signing.p12 | tr -d '\n'
# Linux
base64 -w0 ios-signing.p12
```

```powershell
# Windows PowerShell
[convert]::ToBase64String([IO.File]::ReadAllBytes("ios-signing.p12"))
```

```bash
# gh CLI 一步直传（示例为 legacy 证书项）
gh secret set IOS_CERTIFICATE < <(base64 -i ios-signing.p12 | tr -d '\n')
```

runner 侧解码同款：`echo "$IOS_CERTIFICATE" | base64 --decode > signing.p12`。

## builder ios build 的自动 provisioning 检查

执行 `builder ios build --profile <name>` 时，CLI 在 dispatch 前检查仓库是否已具备该 set 的 Secrets：

| 情形 | 行为 |
| --- | --- |
| 缺失 + 本地已存 ASC key | 静默跑与 `signing setup` 相同的供给流程，上传后继续构建 |
| development/ad-hoc profile 但无任何登记设备 | 停下，指向 `builder signing setup --distribution development --devices-from-mobai` |
| 没有 Apple key | 在推送任何东西之前停下，给出两条出路（配 ASC key 或走路径 C） |
| `--unsigned` | 跳过检查 |
| provider 为 Codemagic/Bitrise | 跳过检查（它们没有 secrets API） |

## 扩展 target 的第四件 Secret

工程含 extension（Widget、通知/分享扩展、Watch App、App Clip）时，每个 set 多一件
`IOS_EXTENSION_PROFILES_<SET>`：JSON object `{bundle id: base64 profile}`，无扩展时写 `{}`。
extension 的 bundle id 由 `builder init` 读进 `ios.extensions`（见 `ios-builder/references/framework-detection.md`）。

## TestFlight / App Store

- 签名要求：Apple Distribution 证书 + App Store 描述文件；development 签名的 IPA 上传即被拒。
- build number 必须递增，否则报 ITMS-90189；打戳用 workflow 的 `build_number` input（`N` 或 `X.Y.Z+N`）。
- 出口合规：Info.plist 设 `ITSAppUsesNonExemptEncryption=false`（此时 `ios upload --wait` 会自动回答），
  否则给 `ios upload` / `ios submit` 传 `--no-encryption`。
- 命令链（每条都支持 `--json`，全程不提问）：

```bash
builder ios build --profile store
builder ios upload --wait
builder ios submit --testflight --group "Beta Testers" --notes "..."
builder ios submit --app-store --release after-approval
builder ios release --profile store ...
```

`builder ios build --profile store --submit` 是 `builder ios release --profile store`（进 TestFlight、
不指派群组）的短形式；
`--unsigned` 与 `--submit` 同用会被直接拒绝。模拟器共享永远是未签名（"Simulator builds are never signed"），
`builder ios share` 相关见 `ios-builder/references/mobai-device-bridge.md`。

## A′：无付费账号的降级路径

1. 执行 `builder ios build --unsigned`（跳过证书导入与描述文件校验步骤）。
2. 把 `./dist/` 的 IPA 交给 MobAI 安装，装机时用**免费 Apple ID 重签**（MobAI 会提示登录）。
3. 重签后 bundle id 带 TeamID 后缀（如 `com.example.myapp.TEAMID`）；热重载必须带后缀续跑：
   `builder dev flutter --skip-install --bundle-id com.example.myapp.TEAMID`。
4. 此路径不出 TestFlight/App Store 上传产物——上传需要付费账号签发的 Apple Distribution 证书。

## 常见失败速查

| 现象/报错线索 | 根因 | 处置 |
| --- | --- | --- |
| 错误点名证书数量（2 Development / 3 Distribution） | Apple 每账号上限，上游从不吊销 | 先在 Portal 手动吊销闲置证书，再重跑 `builder signing setup` |
| 设备登记被拒 | 每会员年 100 台上限 | 清理旧设备或等新会员年 |
| ITMS-90189 | build number 未递增 | 用 `build_number` 重新打戳后重建 |
| Missing Compliance | 未声明出口合规 | `ITSAppUsesNonExemptEncryption=false` 或 `--no-encryption` |
| distribution profile refuses a Debug configuration | set 类型与 configuration 组合非法 | profile 选 development，或 configuration 设 Release |
| "Snapshot SHA mismatch; refusing to build different source" | Codemagic/Bitrise runner 校验快照：`SNAPSHOT_REF` 须在 `refs/ios-builder/jobs/*` 下且 `SNAPSHOT_SHA` 为 40 位 hex | 重新触发构建，勿手改 ref |
| Managed Expo 构建立即失败并点名缺失设置 | app 配置缺 bundleIdentifier | 补 `expo.ios.bundleIdentifier`（app.json）或 `ios.bundleIdentifier`（app.config.js/ts） |
| 带 `--profile` 的 dispatch 被拒 | 仓库里的 workflow 太旧，无 `profile` input | 执行 `builder init` 刷新 workflow 文件 |

更完整的错误码索引见 `ios-builder/references/troubleshooting.md`。
