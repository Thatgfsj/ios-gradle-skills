#!/usr/bin/env python3
"""自检 lint_skill.py 的检查项是否真的"有牙齿"。

经验教训：scheme 的属性正则写成 `BlueprintIdentifier="X"`（等号两侧无空格）时永远不会
命中——Xcode 生成的 xcscheme 全部带空格，于是一条"看起来通过"的检查其实空转。
这类漏检只有靠**故意破坏**才能发现，所以固化成脚本长期跑。

做法：整份仓库复制到临时目录，逐个注入缺陷，再对副本跑 lint_skill.py，
断言每条缺陷都产生预期的 FAIL。任何一条没触发 = 该检查失效，退出码 1。

用法：
    python ios-builder/scripts/ops/selftest_lint.py
    python ios-builder/scripts/ops/selftest_lint.py -v      # 失败时打印完整 lint 输出
退出码：0 所有检查都有牙齿 / 1 存在空转检查 / 2 环境或仓库结构问题
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_NAME = "ios-gradle-skills"          # lint 要求目录名与 frontmatter name 一致
PBX = "examples/basic-swiftui-app/BasicApp.xcodeproj/project.pbxproj"
SCH = "examples/basic-swiftui-app/BasicApp.xcodeproj/xcshareddata/xcschemes/BasicApp.xcscheme"

# (用例名, 目标文件, 注入正则, 替换, 期望 FAIL 文案里的关键词)
CASES = [
    ("缺 rootObject", PBX,
     r"\n\trootObject = [0-9A-F]{24} /\* Project object \*/;", "",
     "缺顶层 rootObject"),
    ("缺 archiveVersion", PBX, r"\n\tarchiveVersion = 1;", "", "缺顶层 archiveVersion"),
    ("缺 objectVersion", PBX, r"\n\tobjectVersion = \d+;", "", "缺顶层 objectVersion"),
    ("缺顶层 objects", PBX, r"\n\tobjects = \{", "\n\tobjectsX = {",
     "缺顶层 objects"),
    ("rootObject 指向未定义对象", PBX,
     r"(rootObject = )([0-9A-F]{24})", r"\g<1>DEADBEEF00000000000000DE",
     "rootObject=DEADBEEF00000000000000DE"),
    ("悬空对象引用", PBX,
     r"(productReference = )([0-9A-F]{24})", r"\g<1>AAAAAAAAAAAAAAAAAAAAAAAA",
     "引用了未定义的对象 ID"),
    ("PBXProject 缺 mainGroup", PBX, r"\n\t\t\tmainGroup = [0-9A-F]{24};", "",
     "PBXProject 缺 mainGroup"),
    ("PBXProject.targets 为空", PBX,
     r"(targets = \(\n)(?:\s*[0-9A-F]{24}[^\n]*\n)+", r"\g<1>",
     "targets 为空"),
    ("target 缺 productType", PBX,
     r'\n\t\t\tproductType = "com.apple.product-type.application";', "",
     "PBXNativeTarget 缺 productType"),
    ("花括号不配平", PBX, r"(\n\t\};\n\trootObject)", r"\n\t};\n\t};\1",
     "花括号不配平"),
    ("section 不配对", PBX, r"\n/\* End PBXBuildFile section \*/", "",
     "Begin/End 不配对"),
    ("引用的文件不存在", PBX, r"path = Assets\.xcassets;", r"path = NotThere.xcassets;",
     "引用的文件在工程里不存在"),
    ("bundle id 与 builder.json 不一致", PBX,
     r"(PRODUCT_BUNDLE_IDENTIFIER = )com\.example\.basicapp;", r"\g<1>com.other.app",
     "与 builder.json 的 ios.bundleId"),
    ("scheme 指向 PBXProject", SCH,
     r'(BlueprintIdentifier = )"E10000000000000000000001"', r'\g<1>"A10000000000000000000001"',
     "scheme 必须指向 PBXNativeTarget"),
    ("scheme BlueprintIdentifier 不存在", SCH,
     r'(BlueprintIdentifier = )"E10000000000000000000001"', r'\g<1>"EE00000000000000000000EE"',
     "在 pbxproj 里不存在"),
    ("scheme 没有 BlueprintIdentifier", SCH,
     r'\n\s*BlueprintIdentifier = "[0-9A-F]{24}"', "",
     "没有 BlueprintIdentifier"),
    ("scheme BlueprintName 不存在", SCH,
     r'(BlueprintName = )"BasicApp"', r'\g<1>"WrongTarget"',
     "target 名在 pbxproj 里不存在"),
    ("scheme BuildableName 与产物不一致", SCH,
     r'(BuildableName = )"BasicApp\.app"', r'\g<1>"Wrong.app"',
     "与产物"),
]


def repo_root() -> Path:
    root = Path(__file__).resolve().parents[3]
    if not (root / "SKILL.md").is_file():
        raise SystemExit(f"[ERROR] 找不到仓库根（推导为 {root}）")
    return root


def run_lint(skill_dir: Path) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, str(skill_dir / "ios-builder" / "scripts" / "ops" / "lint_skill.py"),
         str(skill_dir)],
        capture_output=True, text=True)
    return proc.returncode, proc.stdout + proc.stderr


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="lint_skill.py 检查项有效性自检")
    ap.add_argument("-v", "--verbose", action="store_true", help="空转时打印完整 lint 输出")
    args = ap.parse_args(argv)

    root = repo_root()
    dead: list[str] = []
    with tempfile.TemporaryDirectory(prefix="lint-selftest-") as tmp:
        work = Path(tmp) / REPO_NAME
        shutil.copytree(root, work, ignore=shutil.ignore_patterns(".git", "__pycache__"))

        lint = work / "ios-builder/scripts/ops/lint_skill.py"
        code, out = run_lint(work)
        if code != 0:
            print("[ERROR] 干净副本就 lint 失败，先修 lint_skill.py 再来自检：", file=sys.stderr)
            print(out, file=sys.stderr)
            return 2
        print(f"基线 OK：干净副本 lint 通过（{len(CASES)} 条注入用例待验）\n")
        del lint

        for name, rel, pattern, repl, expect in CASES:
            target = work / rel
            original = target.read_text(encoding="utf-8")
            mutated, n = re.subn(pattern, repl, original, count=1)
            if n == 0 or mutated == original:
                print(f"BROKEN  {name}：注入正则本身没匹配上（用例失效）")
                dead.append(name)
                continue
            target.write_text(mutated, encoding="utf-8", newline="\n")
            code, out = run_lint(work)
            hits = [l for l in out.splitlines() if l.startswith("FAIL") and expect in l]
            if code != 0 and hits:
                print(f"咬住了    {name:28s} -> {hits[0][6:88]}")
            else:
                print(f"*** 空转  {name:28s} 期望 FAIL 含「{expect}」，实际 exit={code}")
                dead.append(name)
                if args.verbose:
                    print(out)
            target.write_text(original, encoding="utf-8", newline="\n")

    if dead:
        print(f"\n结果：{len(dead)} 条检查空转/用例失效 -> {dead}")
        return 1
    print(f"\n结果：{len(CASES)} 条注入缺陷全部被抓住，lint_skill.py 的检查都有牙齿")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or None))
