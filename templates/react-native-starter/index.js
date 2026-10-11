import { AppRegistry } from "react-native";
import App from "./App";
import { name as appName } from "./app.json";

// appName 来自 app.json，必须与 ios/<App>.xcodeproj 里的目标一致：
// runner 用 builder.json 的 ios.scheme 构建，Debug 包启动后会去连 Metro 取 JS bundle。
AppRegistry.registerComponent(appName, () => App);
