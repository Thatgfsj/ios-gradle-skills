# react-native-starter

React Native 工程模板。iOS 侧通过 **远程 xcodebuild** 构建（`builder ios build`），
开发期热重载走 `builder dev rn` + Metro + MobAI。

## 为什么本模板不带 `ios/` 与 `package.json`

RN 的 iOS 宿主工程（`ios/<App>.xcodeproj`、Podfile）与 Metro 配置由 RN CLI / 模板生成，
版本强耦合。手写一份进仓库会随 RN 版本漂移并给出假象——所以这里只给
**iOS 远程构建所需的配置**，工程本体用官方 CLI 生成：

```bash
npx @react-native-community/cli init MyApp
cd MyApp
```

生成后再把本模板的 `builder.json` 落进去（版本线以官方发布页为准，不要照抄本仓库的示例号）。

## 使用步骤

```bash
# 1. 脚手架生成配置 + 目录
python ../../ios-builder/scripts/init_ios_project.py MyApp ~/projects --framework react-native

# 2. 若目录已存在 RN 工程，仅覆盖配置；否则用官方 CLI 在同一目录 init
npx @react-native-community/cli init MyApp

# 3. 接入远程构建
builder auth github
builder init

# 4. Unsigned IPA
builder ios build --unsigned

# 5. 真机热重载：本机起 Metro，iPhone 与电脑同一 WiFi，MobAI 已连接设备
builder dev rn
```

## builder.json 关键字段

| 字段 | RN 取值 | 说明 |
| --- | --- | --- |
| `ios.path` | `ios` | RN 工程固定把 iOS 宿主放在 `ios/` |
| `ios.scheme` | `<App 名>` | 与 `ios/` 下 `.xcodeproj` 同名 |
| `ios.configuration` | `Debug` | Debug 产物从 Metro 取 JS；发正式版改 `Release` |

## 何时必须重建

| 变更内容 | 处理方式 |
| --- | --- |
| `.ts` / `.tsx` / `.js` 业务代码 | Fast Refresh 自动生效，无需重建 |
| `package.json` 新增原生模块 | 必须重建（Podfile 锁变、Swift 桥接变） |
| `ios/` 下原生代码 / `Podfile` | 必须重建 |
| 仅 `--unsigned` 包用于内测 | 重装即可，无需签名链路 |

详见 `../../ios-builder/references/react-native-hot-reload.md`。
