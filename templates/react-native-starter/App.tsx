import React from "react";
import { SafeAreaView, ScrollView, StatusBar, StyleSheet, Text, View } from "react-native";

// 只写跨版本稳定的 RN 组件；具体版本线由 RN CLI 生成工程后按官方发布页核对。
export default function App() {
  return (
    <SafeAreaView style={styles.root}>
      <StatusBar barStyle="dark-content" />
      <ScrollView contentContainerStyle={styles.body}>
        <Text style={styles.title}>Remote iOS build check</Text>
        <Text style={styles.line}>
          看到这个页面，说明 GitHub Actions runner 产出的 Debug IPA 已装机，并且 JS bundle
          正从本机 Metro 加载。
        </Text>
        <View style={styles.box}>
          <Text style={styles.line}>改这里保存 → Metro 触发 Fast Refresh，无需重建 IPA</Text>
          <Text style={styles.line}>改 ios/ 或 package.json 原生依赖 → 必须 builder ios build 重建</Text>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: "#fff" },
  body: { padding: 20, gap: 12 },
  title: { fontSize: 22, fontWeight: "600" },
  line: { fontSize: 15, lineHeight: 22, color: "#222" },
  box: { borderWidth: 1, borderColor: "#ddd", borderRadius: 12, padding: 14, gap: 8 },
});
