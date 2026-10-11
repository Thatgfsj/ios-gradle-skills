//
//  ContentView.swift
//  BasicApp
//
//  只使用 iOS 17 起可用的 API（@Observable / LabeledContent / NavigationStack），
//  对应 SKILL.md「标准技术栈」：SwiftUI + 最低 iOS 17.0。
//

import SwiftUI

@Observable
final class CounterModel {
    var count: Int = 0
    func increment() { count += 1 }
}

struct ContentView: View {
    @State private var model = CounterModel()

    var body: some View {
        NavigationStack {
            List {
                Section("Build info") {
                    LabeledContent("App", value: "BasicApp")
                    LabeledContent("Bundle ID", value: "com.example.basicapp")
                    LabeledContent("Deployment target", value: "iOS 17.0")
                }

                Section("Remote build check") {
                    Text("看到本页面，说明 GitHub Actions runner 产出的 IPA 已安装并成功启动。")
                        .font(.callout)
                        .foregroundStyle(.secondary)
                }
            }
            .navigationTitle("BasicApp")
            .toolbar {
                ToolbarItem(placement: .primaryAction) {
                    Button {
                        model.increment()
                    } label: {
                        Label("Increment", systemImage: "plus")
                    }
                }
            }
        }
    }
}

#Preview {
    ContentView()
}
