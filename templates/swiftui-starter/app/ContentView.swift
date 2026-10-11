//
//  ContentView.swift
//  __APP_NAME__
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
                    LabeledContent("App", value: "__APP_NAME__")
                    LabeledContent("Bundle ID", value: "__BUNDLE_ID__")
                    LabeledContent("Deployment target", value: "iOS __IOS_MIN__")
                }

                Section("Remote build check") {
                    Text("看到本页面，说明 GitHub Actions runner 产出的 IPA 已安装并成功启动。")
                        .font(.callout)
                        .foregroundStyle(.secondary)
                }
            }
            .navigationTitle("__APP_NAME__")
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
