# 签名 Secrets 一览

本文件只列 **名称与用途**；生成证书/描述文件的完整流程、base64 命令与降级路径见
[`../ios-builder/references/code-signing.md`](../ios-builder/references/code-signing.md)。

配置数据截至 2026-09（ios-builder v0.11.0）。名称以上游 README 与
`internal/workflow/templates/ios-build.yml` 为准，大小写敏感。

## Legacy 三件套（`ios.signing: true` 且不选 profile）

| Secret | 内容 | 来源 |
| --- | --- | --- |
| `IOS_CERTIFICATE` | base64 编码的 `.p12` | `builder signing p12` 或 Keychain Access 导出 |
| `IOS_CERTIFICATE_PASSWORD` | `.p12` 的口令 | 导出时自定；`signing setup --yes` 会生成并打印一次 |
| `IOS_PROVISIONING_PROFILE` | base64 编码的 `.mobileprovision` | Developer Portal 下载，或 `signing setup` 生成 |

本仓库的 `builder/builder.template.json` 默认走这条路径（`"signing": false` 表示
未启用；把它改成 `true` 即启用三件套）。

## 按 distribution 分后缀的 Signing Set（`profiles.<name>.distribution`）

| `distribution` | 证书 / 描述文件类型 | Secrets |
| --- | --- | --- |
| `development` | Apple Development / iOS App Development（需登记设备） | `IOS_CERTIFICATE_DEVELOPMENT`、`IOS_CERTIFICATE_PASSWORD_DEVELOPMENT`、`IOS_PROVISIONING_PROFILE_DEVELOPMENT` |
| `ad-hoc` / `internal` | Apple Distribution / Ad Hoc（需登记设备） | `IOS_CERTIFICATE_AD_HOC`、`IOS_CERTIFICATE_PASSWORD_AD_HOC`、`IOS_PROVISIONING_PROFILE_AD_HOC` |
| `store` | Apple Distribution / App Store | `IOS_CERTIFICATE_STORE`、`IOS_CERTIFICATE_PASSWORD_STORE`、`IOS_PROVISIONING_PROFILE_STORE` |
| `enterprise` | In-house（仅 Portal 手工路径） | `IOS_CERTIFICATE_ENTERPRISE`、`IOS_CERTIFICATE_PASSWORD_ENTERPRISE`、`IOS_PROVISIONING_PROFILE_ENTERPRISE` |

含 extension target（Widget、通知/分享扩展、Watch App、App Clip）时，每个 set 多一件第四项：

| Secret | 内容 |
| --- | --- |
| `IOS_EXTENSION_PROFILES_<SET>` | JSON 对象 `{"<extension bundle id>": "<base64 mobileprovision>"}`，没有扩展时写 `{}` |

## 模拟器共享与设备通道

| Secret / 变量 | 用途 | 何时必需 |
| --- | --- | --- |
| `MOBAI_API_KEY` | `builder ios share` 在 MobAI 云端开模拟器；在 MobAI App 的 Account → API Keys 生成后 `gh secret set MOBAI_API_KEY` | 仅用模拟器共享时 |
| `MOBAI_ACCESS_KEY` | **本地**环境变量或运行目录下的 `.env`，MobAI API server 开了 token 时必填（请求头 `X-API-Key`） | WSL/NAT 网络访问 MobAI 时 |
| `CODEMAGIC_API_TOKEN` / `BITRISE_API_TOKEN` | 仅 CLI 读取，不写进 `builder.json` | 切到该 provider 时 |
| `ASC_ISSUER_ID` / `ASC_KEY_ID` / `ASC_KEY_PATH`（或 `ASC_PRIVATE_KEY`） | 无 keychain 的机器（CI、agent）上替代 `builder auth apple` | 自动签名 / TestFlight 上传时 |

## 一行设置示例

```bash
gh secret set IOS_CERTIFICATE < <(base64 -i ios-signing.p12 | tr -d '\n')
gh secret set IOS_CERTIFICATE_PASSWORD --body "$P12_PASSWORD"
gh secret set IOS_PROVISIONING_PROFILE < <(base64 -i Builder-development-com.example.app.mobileprovision | tr -d '\n')
```

校验是否配齐（不需要 Mac）：

```bash
python ios-builder/scripts/ops/check_signing_secrets.py --project /path/to/MyApp --distribution development
```

## 没有付费开发者账号时

不要配任何签名 Secret：用 `builder ios build --unsigned` 出包，
把 IPA 交给 MobAI 安装，装机时用**免费 Apple ID 重签**（MobAI 会提示登录；
重签后 bundle id 带 TeamID 后缀，例如 `com.example.myapp.TEAMID`）。
热重载时用同一个后缀 id：`builder dev flutter --skip-install --bundle-id com.example.myapp.TEAMID`。
