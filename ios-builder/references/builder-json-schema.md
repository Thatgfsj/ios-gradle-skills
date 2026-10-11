# builder.json 字段全解

数据截至 2026-09（ios-builder v0.11.0）。本文件展开 `builder.json` 的字段级语义与默认值；
本仓库模板是 `builder/builder.template.json`（自带 `_comment`，复制到项目根后删除该键）。
根 `SKILL.md` 的配置矩阵不在此重复。

## 位置与校验强度

放在项目仓库根。校验只强制 `project` + `github.owner` + `github.repo` 三个字段，其余可省略并回落默认值。
tag 触发构建时，`builder.json` 是唯一参数来源（见 `ios-builder/references/workflow-yml-anatomy.md`）。

## 顶层键

| 键 | 类型 | 必填 | 默认/回落 | 说明 |
| --- | --- | --- | --- | --- |
| `project` | string | ✅ | — | 项目名 |
| `platform` | string | ❌ | — | 本场景固定 `"ios"` |
| `github` | object `{owner, repo}` | ✅ owner/repo | — | 触发与产物所在仓库 |
| `provider` | string | ❌ | `"github"` | `"github"|"codemagic"|"bitrise"`，解析结果落到 github |
| `codemagic` / `bitrise` | object | 切该 provider 时 | — | 字段见 provider 块小节 |
| `ios` | object | ❌ | 见下 | iOS 构建与 legacy 签名开关 |
| `flutter` | object | ❌ | 见下 | Flutter 版本与 watch |
| `reactNative` | object | ❌ | 见下 | 代码里存在、README 未记录 |
| `kmp` | object | ❌ | `jdkVersion: "17"` | Kotlin Multiplatform |
| `mobai` | object | ❌ | 见下 | 只有 `url` 与 `device_id` 两个字段 |
| `signing` | object | ❌ | `dir: ""` | 由 `builder signing setup` 维护 |
| `defaultProfile` | string | ❌ | `""` | 不带 `--profile` 时应用的 profile 名 |
| `profiles` | map | ❌ | 无 | 具名构建设置集，`--profile` 选择 |

## ios.*

| 字段 | 默认 | 说明 |
| --- | --- | --- |
| `path` | `"."`（"detected by init"） | Xcode 工程目录，相对仓库根 |
| `scheme` | `""`（"auto-detected"） | 留空由 runner 探测 |
| `bundleId` | 无 | 签名定位用；`signing setup` 的 bundle id 优先级 `--bundle-id` > `ios.bundleId` > `./dist/` 最新 IPA |
| `extensions` | `[]` | extension target 的 bundle id 数组，`builder init` 从 Xcode 项目读入 |
| `configuration` | `"Debug"` | "Builds are Debug unless you set Release" |
| `signing` | `false` | 仅 legacy 路径生效："Legacy: sign builds that select no profile, with the unsuffixed IOS_CERTIFICATE, IOS_CERTIFICATE_PASSWORD and IOS_PROVISIONING_PROFILE secrets. Profiles ignore it" |

上游 `CLAUDE.md` 的判定口径：`config.ResolveProfile: --profile, else defaultProfile, else top level unchanged.
A profile signs iff it has a distribution; ios.signing is only the no-profile path`。

## mobai.*

| 字段 | 默认 | 说明 |
| --- | --- | --- |
| `url` | `"http://localhost:8686"` | 本机 MobAI API server |
| `device_id` | `""` | "uses first available if empty" |

`builder.json` 里**没有** mobai api key 字段。本地 token 走环境变量 `MOBAI_ACCESS_KEY`（请求头
`X-API-Key`；先读环境变量，再读工作目录下的 `./.env`）；CI 侧共享密钥是仓库 Secret `MOBAI_API_KEY`。
名称全表见 `.github/secrets.example.md`。

## profiles 与 defaultProfile

上游定义："Profiles are named sets of build settings, in the spirit of eas.json, selected with
`--profile` on ios build"。每个 profile 只允许五个键：

| 键 | 取值与语义 |
| --- | --- |
| `distribution` | `development` / `ad-hoc`（或 `internal`，同一件事）/ `store` / `enterprise`；"Omitted means an unsigned build" |
| `configuration` | "Overrides the derived configuration: Debug for development, Release for every other distribution, ios.configuration for unsigned profiles" |
| `scheme` | 覆盖 `ios.scheme` |
| `provider` | 覆盖顶层 `provider` |
| `env` | "String map exported as environment variables on the runner before dependencies are installed and the app is built, so pod install, npm install, flutter pub get, Gradle and xcodebuild all see them"；"env values are build-time configuration, not secrets"。保留名被拒：`SCHEME`、`CONFIGURATION`、`USE_SIGNING`、`BUILD_ENV`、`PATH`、`HOME`、`DEVELOPER_DIR`、signing secrets，以及前缀 `GITHUB_`、`RUNNER_`、`CM_`、`BITRISE_`、`BUILDER_` |

规则（上游口径）：

- 解析顺序："Without --profile, the profile named by defaultProfile applies. With neither, the
  top-level ios.* and provider settings are used exactly as before"；"A profile only overrides the fields it sets"。
- 未知 profile 名报错并列出可用名；`--unsigned` 与 `--provider` 命令行覆盖 profile；分发前打印解析后的设置。
- profiles 只作用于 `ios build`；`ios share` 不接受 `--profile`（模拟器构建永远 Debug + unsigned）。
- 选 profile 需要本版本 init 生成的 workflow（其中声明了 `profile` input）；旧提交里的 workflow 会拒绝这次 dispatch。
- `builder signing setup` 会把 `distribution` 写进对应 profile，且不动 `defaultProfile`。

上游 README 的 profile 示例（verbatim）：

```json
{"ios":{"path":"ios","bundleId":"com.example.app"},"defaultProfile":"development","profiles":{"development":{"distribution":"development"},"preview":{"distribution":"internal","env":{"API_URL":"https://staging.example.com"}},"production":{"distribution":"store","scheme":"MyApp","provider":"codemagic"}}}
```

## flutter.* / reactNative.* / kmp.* / signing.*

| 路径 | 默认 | 说明 |
| --- | --- | --- |
| `flutter.version` | `""` | 锁定的 Flutter 版本（如 `"3.24.0"`）；空 = 最新 stable |
| `flutter.watch.dirs` | `["lib"]` | `builder dev` 监听目录 |
| `flutter.watch.patterns` | `[".dart"]` | 后缀匹配 |
| `flutter.watch.ignore` | `[".g.dart", ".freezed.dart"]` | 生成文件 |
| `flutter.watch.debounce` | `100` | 毫秒 |
| `reactNative.metroPort` | `8081` | 代码里存在、README 未记录；命令行 `--metro-port` 见 SKILL.md 矩阵 |
| `reactNative.expo` | bool | 代码里存在、README 未记录；形态判断别依赖它 |
| `kmp.jdkVersion` | `"17"` | `builder init` 询问写入 |
| `signing.dir` | `""` | "the --out-dir of the last automatic signing setup, as given (a leading ~ is kept); empty means the working directory" |

## provider 块（codemagic / bitrise）

| 字段 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- |
| `app_id` | ✅ | — | "app_id must be an app identifier, not a URL"，允许字符 `[A-Za-z0-9_-]` |
| `branch` | ✅ | — | 目标分支 |
| `build_workflow` | ❌ | `"ios-build"` | |
| `share_workflow` | ❌ | `"ios-share"` | |

token 只从环境变量 `CODEMAGIC_API_TOKEN` / `BITRISE_API_TOKEN` 读取，**绝不**写进 `builder.json`。

## 只能靠命令写回的字段

| 字段 | 由谁写入 |
| --- | --- |
| `ios.extensions` | `builder init`（读 Xcode 项目） |
| `kmp.jdkVersion` | `builder init`（交互询问，默认 17） |
| `signing.dir` | `builder signing setup`（`--out-dir` 非默认时记录） |
| `profiles.<name>.distribution` | `builder signing setup` |
| workflow 文件（仓库的 `.github/workflows/`） | `builder init` |

手填这些字段没有意义——命令会覆盖或重算；签名细节见 `ios-builder/references/code-signing.md`。

## 最小可用示例：原生 + 未签名

```json
{
  "project": "MyApp",
  "platform": "ios",
  "github": { "owner": "username", "repo": "my-ios-app" },
  "ios": { "path": ".", "scheme": "", "configuration": "Debug", "signing": false }
}
```

其余全部走默认；配好 workflow 后执行 `builder ios build --unsigned` 即可出包到 `./dist/`。

## 示例：按 distribution 分 set 签名

```json
{"project":"MyApp","github":{"owner":"username","repo":"my-ios-app"},"ios":{"path":".","bundleId":"com.example.myapp"},"defaultProfile":"development","profiles":{"development":{"distribution":"development"},"store":{"distribution":"store"}}}
```

带 `distribution` 的 profile 走分后缀 Secrets（`IOS_CERTIFICATE_STORE` 等），映射见
`ios-builder/references/workflow-yml-anatomy.md`；生成流程见 `ios-builder/references/code-signing.md`。

本仓库 `builder/builder.template.json` 的取向：默认保留 legacy 无后缀路径（`ios.signing`），同时附
`profiles` 示例。沿用三件套就删掉 `defaultProfile`/`profiles` 并把 `ios.signing` 置 `true`；
走分 set 则保留 profiles、忽略 `ios.signing`（上游原文："Profiles ignore it"）。上文 profiles 小节引用的
README 示例片段可整段粘贴后补齐 `project` 与 `github`。

## 校验

改完 `builder.json`，先在本地执行（不需要 Mac）：

```bash
python3 -c "import json;d=json.load(open('builder.json'));assert d['project'] and d['github']['owner'] and d['github']['repo'];print('OK')"
```

- JSON 解析失败 = 整条远程通道停摆（Resolve parameters 步骤直接红）。
- 三个强制字段之一为空 = CLI 拒绝；其余字段错误只影响对应分支。
- `env` 里出现上文的保留名会被拒绝。
- 本仓库模板自身的改动，提交前跑 `python ios-builder/scripts/ops/lint_skill.py`。
