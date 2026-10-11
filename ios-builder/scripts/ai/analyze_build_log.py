#!/usr/bin/env python3
"""Build Log Analyzer（AI 调用）

解析远程构建日志（GitHub Actions run log / xcodebuild 输出 / builder CLI stderr），
把报错映射到 ios-builder/references/troubleshooting.md 的 E 码，输出根因与首条修复命令。
Agent 在拿到失败日志后应先跑本脚本，再决定重试策略——不要凭肉眼在千行日志里翻。

Usage:
    gh run view <id> --log > build.log                 # 先取日志
    python ios-builder/scripts/ai/analyze_build_log.py build.log
    cat build.log | python analyze_build_log.py -
    python analyze_build_log.py build.log --json       # 机器可读
    python analyze_build_log.py build.log --project /path/to/MyApp   # 附带该项目的 E 码上下文

Options:
    - , --stdin          从标准输入读日志
    --json               输出 JSON（匹配到的规则、行号、原文片段、修复建议）
    --project DIR        读该目录 builder.json，用于区分 unsigned / 签名 / profile 通道
    --max-hits N         每个规则最多打印几条命中（默认 3）
    --strict             没有命中任何规则时也返回非 0（默认返回 0，未知错误交给人）

退出码：
    0  完成（含未命中）
    1  命中 >=1 条已知规则
    2  日志读不到 / 参数非法

规则只使用上游文档里出现过的字符串与关键词形态，不做无依据的猜测；
未命中的错误一律进 UNKNOWN 段，提示 agent 去 troubleshooting.md 兜底。
"""

import argparse
import json
import re
import sys
from pathlib import Path

# (正则, E 码, 一句话根因, 首条修复命令)
# 规则表：E 码与 ios-builder/references/troubleshooting.md 的错误码索引一一对应
# （E1 设备 / E2 产物 / E3 签名 / E4 签名配置 / E5 Flutter / E6 Metro /
#  E7 原生层 / E8 配额与超时 / E9 初始化 / E10 workflow 通道）。
# SRC 与 ASC 是**非通道**问题（源码编译、App Store Connect 侧），故意不占 E 码。
# 只允许使用上游文档里出现过的字符串与关键词形态。
RULES = [
    (r"No devices found", "E1",
     "MobAI 没看到物理设备；热重载只支持真机，不支持模拟器",
     "builder mobai ping"),
    (r"Only physical iOS devices are supported", "E1",
     "把模拟器当成了热重载目标；模拟器走 builder ios share",
     "builder ios share"),
    (r"invalid or missing API token", "E1",
     "MobAI API server 设了 token，但环境/运行目录 .env 里没有 MOBAI_ACCESS_KEY",
     "printf 'MOBAI_ACCESS_KEY=<你的 token>\\n' > .env"),
    (r"device is in use|in use by another", "E1",
     "设备 bridge 被 MobAI app 占用",
     "在 MobAI app 里停止 bridge 后重跑 builder dev flutter"),
    (r"Connection refused|dial tcp.*(8686|localhost)|no route to host|nodename nor servname|Name or service not known",
     "E1", "builder 连不到 MobAI API（WSL 网络模式或 mobai.url 写错）",
     "builder mobai ping   # WSL NAT 下先 hostname.exe 取主机名，再在 MobAI 打开 Allow external connections"),
    (r"BUILD FAILED|\*\* BUILD FAILED \*\*", "E2",
     "xcodebuild 未产出 .app，因此没有 IPA",
     "python ios-builder/scripts/ai/analyze_build_log.py build.log --project ."),
    (r"if-no-files-found|No files were found with name \(ipa\)|artifact.*not found", "E2",
     "artifact 上传被拒：runner 上 build/*.ipa 为空",
     "python ios-builder/scripts/ops/trigger_build.py --project . --dry-run"),
    (r"Code signing is required|requires a provisioning profile|no account for team|No profile for",
     "E3", "签名构建缺证书或描述文件，或 Keychain 未导入",
     "builder ios build --unsigned"),
    (r"distribution profile.*Debug|profile.*refuses.*Debug", "E3",
     "distribution 类型的描述文件不接受 Debug 配置",
     "builder ios build --profile store"),
    (r"缺少证书 Secret|IOS_CERTIFICATE|IOS_PROVISIONING_PROFILE", "E4",
     "所选 signing set 的 Secrets 不齐（名字按 distribution 加后缀）",
     "python ios-builder/scripts/ops/check_signing_secrets.py --project . --distribution development"),
    (r"2 Development|3 Distribution|maximum number of.*devices|100 devices", "E4",
     "触达 Apple 账号上限（Development 2 张 / Distribution 3 张 / 每会员年 100 台设备）",
     "builder signing setup --distribution development --devices-from-mobai"),
    (r"mobai-ios|flutter attach|flutter_tools", "E5",
     "Flutter 侧 attach / 自定义设备通道异常",
     "builder dev flutter --no-attach   # 先看它打印的 attach 命令能否手工跑通"),
    (r"Metro|8081|Fast Refresh", "E6",
     "Metro 通道问题（端口被占、设备与电脑不在同一 WiFi、WSL Hyper-V 防火墙）",
     "npx react-native start"),
    (r"Undefined symbol|module map|framework not found|pod install failed", "E7",
     "原生层（Swift/ObjC/Podfile/原生模块）与已装机版本不一致，或原生依赖坏掉",
     "builder ios build   # 完成后重装，再 builder dev ... --skip-install --bundle-id <id>"),
    (r"exceeded the timeout|timeout-minutes|Job has been canceled|never received a completion", "E8",
     "触达免费档 90 分钟上限或排队超时（冷启动 RN/Expo 常需 30-60 分钟）",
     "builder ios build --unsigned   # 少改动时优先热重载而不是重建"),
    (r"仓库缺少 builder.json|builder\.json.*(not found|no such file|missing)", "E9",
     "仓库根没有 builder.json，runner 无法解析参数",
     "builder init"),
    (r"Not Found|404 .*repository|please make sure the repository exists", "E9",
     "builder.json 里的 github.owner/repo 与真实仓库不符",
     "python ios-builder/scripts/ai/patch_builder_config.py --project . --owner <你> --repo <库> --write"),
    (r"Unknown input|unknown.*profile.*input|rejects the dispatch|Process workflow_dispatch event input", "E10",
     "仓库里提交的 workflow 版本过旧，缺少 profile 等 input",
     "builder init   # 刷新 workflow 后推到默认分支"),
    (r"ITMS-90189|build number.*(already used|must increase)", "ASC",
     "同一 version 下 CFBundleVersion 未递增，App Store Connect 拒绝重复上传",
     "builder ios release --profile store"),
    (r"Missing Compliance", "ASC",
     "出口合规问题未回答，TestFlight 里构建一直显示缺合规",
     "builder ios upload --wait --no-encryption"),
    (r"error: cannot find .* in scope|error: .* has no member|SwiftCompile.*error", "SRC",
     "Swift 源码编译错误（不属于构建通道问题，按编译器提示改代码）",
     "改完再执行 builder ios build --unsigned"),
]
REFERENCE = "ios-builder/references/troubleshooting.md"


def read_log(spec: str) -> str:
    if spec in ("-", None):
        return sys.stdin.read()
    p = Path(spec)
    if not p.is_file():
        print(f"[ERROR] 日志文件不存在：{p}", file=sys.stderr)
        print("[HINT ] 先取日志：gh run view <run-id> --log > build.log", file=sys.stderr)
        sys.exit(2)
    return p.read_text(encoding="utf-8", errors="replace")


def project_context(project: str) -> dict:
    cfg = Path(project) / "builder.json"
    if not cfg.is_file():
        return {}
    try:
        return json.loads(cfg.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"[WARN ] {cfg} 不是合法 JSON：{exc}", file=sys.stderr)
        return {}


def analyze(text: str, max_hits: int) -> list:
    lines = text.splitlines()
    findings = []
    for pattern, code, cause, fix in RULES:
        rx = re.compile(pattern, re.I)
        hits = [(i + 1, ln.strip()) for i, ln in enumerate(lines) if rx.search(ln)]
        if not hits:
            continue
        findings.append({
            "code": code,
            "pattern": pattern,
            "cause": cause,
            "fix": fix,
            "hits": [{"line": n, "text": t[:300]} for n, t in hits[:max_hits]],
            "total": len(hits),
        })
    def order(f):
        tail = f["code"][1:]
        num = int(tail) if tail.isdigit() else 999
        return (num, f["hits"][0]["line"])
    findings.sort(key=order)
    return findings


def tail_error(text: str) -> list:
    """未命中规则时，把 ::error:: 与 error: 行兜底打出来。"""
    rx = re.compile(r"(::error::|^error:|\berror:\s)", re.I)
    return [ln.strip()[:300] for ln in text.splitlines() if rx.search(ln)][:15]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="analyze_build_log.py", description="把远程构建日志映射到 E 码")
    ap.add_argument("log", nargs="?", default="-", help="日志文件路径，或 - 读 stdin")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--project", default="", help="目标工程目录，读它的 builder.json")
    ap.add_argument("--max-hits", type=int, default=3)
    ap.add_argument("--strict", action="store_true", help="无命中也返回非 0")
    args = ap.parse_args(argv if argv is not None else sys.argv[1:])

    text = read_log(args.log)
    if not text.strip():
        print("[ERROR] 日志为空", file=sys.stderr)
        return 2

    findings = analyze(text, args.max_hits)
    cfg = project_context(args.project) if args.project else {}

    if args.json:
        print(json.dumps({
            "project": args.project or None,
            "builder_json": {
                "ios_path": (cfg.get("ios") or {}).get("path"),
                "scheme": (cfg.get("ios") or {}).get("scheme"),
                "signing": (cfg.get("ios") or {}).get("signing"),
                "defaultProfile": cfg.get("defaultProfile"),
            } if cfg else None,
            "findings": findings,
            "unknown_errors": [] if findings else tail_error(text),
            "reference": REFERENCE,
        }, ensure_ascii=False, indent=2))
        return 1 if findings else (1 if args.strict else 0)

    if not findings:
        print("未命中已知规则。日志里的报错行：")
        for ln in tail_error(text) or ["(没找到 error 行，可能是被 timeout 截断)"]:
            print("  " + ln)
        print(f"\n下一步：在 {REFERENCE} 里按原文关键字搜；搜不到就按 UNKNOWN 流程处理。")
        return 1 if args.strict else 0

    if cfg:
        ios = cfg.get("ios") or {}
        print(f"项目上下文：ios.path={ios.get('path')} scheme={ios.get('scheme')} "
              f"signing={ios.get('signing')} defaultProfile={cfg.get('defaultProfile') or '(未设)'}")
        print("-" * 60)
    for f in findings:
        print(f"[{f['code']}] {f['cause']}   （命中 {f['total']} 行）")
        for h in f["hits"]:
            print(f"    L{h['line']}: {h['text']}")
        print(f"    修复：{f['fix']}")
        print()
    print(f"详细根因与备选方案见 {REFERENCE}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
