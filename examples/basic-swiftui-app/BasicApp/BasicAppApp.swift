//
//  BasicAppApp.swift
//  BasicApp
//
//  SwiftUI 入口。@main + WindowGroup，无需 UIStoryboard / Info.plist 场景声明
//  （工程使用 GENERATE_INFOPLIST_FILE = YES，由 build settings 生成 Info.plist）。
//

import SwiftUI

@main
struct BasicAppApp: App {
    var body: some Scene {
        WindowGroup {
            ContentView()
        }
    }
}
