#!/usr/bin/env python3
"""iOS Project Initializer (MobAI ios-builder era)

从 templates/ 渲染一个「可被 builder ios build 直接构建」的 iOS 工程骨架：
Xcode 工程文件、SwiftUI 源码、真实 builder.json、预生成的 ios-build.yml workflow。

本脚本是模板的渲染器，不是模板的来源：所有文件内容来自仓库的
templates/<framework>/ 与 builder/ios-build.yml.template，单一来源，避免双份漂移。

Usage:
    python init_ios_project.py <app_name> [target_dir] [options]
    python init_ios_project.py <app_name> -o /path/to/projects
    python init_ios_project.py --interactive

Options:
    -o, --output DIR        输出根目录（工程建在 <DIR>/<app_name> 下）；缺省用当前目录
    --framework NAME        swiftui | flutter | react-native（默认 swiftui）
    --unsigned              生成的 builder.json 里预设 "signing": false
    --org DOMAIN            bundle id 前缀（默认 com.example → com.example.myapp）
    --bundle-id ID          直接指定完整 bundle id，优先级高于 --org
    --ios-min VER           IPHONEOS_DEPLOYMENT_TARGET（默认 17.0）
    --swift-version VER     SWIFT_VERSION（默认 6.0；6.2 需 Xcode 26+，见下方说明）
    --scheme NAME           Xcode scheme 名（默认等于 app 名；flutter 用 Runner）
    --owner USER            GitHub owner（缺省从 git remote origin 探测）
    --repo NAME             GitHub repo 名（缺省从 git remote origin 探测，再退化为 app 名）
    --force                 目标目录已存在时先清空重建
    --interactive           问答模式

Exit codes:
    0  成功
    1  目录冲突（目标已存在且未加 --force）
    2  模板缺失（templates/ 或 builder/ios-build.yml.template 不在）
    3  参数非法

所有错误写 stderr，并附一条可执行的修复建议。

Generated project layout (--framework swiftui):
    MyApp/
    +-- MyApp/
    |   +-- MyAppApp.swift
    |   +-- ContentView.swift
    |   +-- Assets.xcassets/
    +-- MyApp.xcodeproj/
    |   +-- project.pbxproj
    |   +-- project.xcworkspace/contents.xcworkspacedata
    |   +-- xcshareddata/xcschemes/MyApp.xcscheme
    +-- builder.json
    +-- .github/workflows/ios-build.yml
    +-- .gitignore
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# --------------------------------------------------------------- versions --
# 数据截至 2026-09。改版本号前核对：
#   Xcode 发布  https://developer.apple.com/news/releases/
#   runner 镜像 https://github.com/actions/runner-images
#   ios-builder https://github.com/MobAI-App/ios-builder
DEFAULT_IOS_MIN = "17.0"
# SWIFT_VERSION 是「语言模式」而非编译器版本：6.2 语言模式需要 Xcode 26+，
# 而 macos-15 镜像上的工具链可能停在 16.x。为让产物在 CI 上必然可编译，
# 模板默认写 6.0（Xcode 16 全系可编译），要吃到 Swift 6.2 再显式 --swift-version 6.2。
DEFAULT_SWIFT_VERSION = "6.0"
DEFAULT_ORG = "com.example"
DEFAULT_FRAMEWORK = "swiftui"
FRAMEWORKS = ("swiftui", "flutter", "react-native")
IOS_PATH_BY_FRAMEWORK = {"swiftui": ".", "flutter": "ios", "react-native": "ios"}
DEFAULT_SCHEME_BY_FRAMEWORK = {"swiftui": None, "flutter": "Runner", "react-native": None}

PLACEHOLDER = "__{}__"


def ph(key: str) -> str:
    return PLACEHOLDER.format(key)


APP_NAME_PH = ph("APP_NAME")
BUNDLE_ID_PH = ph("BUNDLE_ID")
IOS_MIN_PH = ph("IOS_MIN")
SWIFT_VERSION_PH = ph("SWIFT_VERSION")
GH_OWNER_PH = ph("GH_OWNER")
GH_REPO_PH = ph("GH_REPO")
SIGNING_PH = ph("SIGNING")

TRUE_TOKEN = "__TRUE__"
FALSE_TOKEN = "__FALSE__"


def die(code: int, message: str, hint: str = "") -> None:
    """按规范退出：错误进 stderr，附带修复建议。"""
    print(f"[ERROR] {message}", file=sys.stderr)
    if hint:
        print(f"[HINT ] {hint}", file=sys.stderr)
    sys.exit(code)


# ------------------------------------------------------------ templates ----
def repo_root() -> Path:
    """本脚本位于 <root>/ios-builder/scripts/，仓库根为上溯两级。"""
    return Path(__file__).resolve().parents[2]


def locate_templates() -> Path:
    root = repo_root()
    for candidate in (root / "templates", Path.cwd() / "templates"):
        if (candidate / "swiftui-starter").is_dir():
            return candidate
    die(
        2,
        f"未找到模板目录：{root / 'templates'} 下缺少 swiftui-starter/",
        "在 ios-gradle-skills 仓库内运行本脚本，或 git clone 完整仓库："
        "https://github.com/your-org/ios-gradle-skills",
    )
    raise AssertionError("unreachable")


def workflow_template(templates_dir: Path) -> Path:
    p = templates_dir.parent / "builder" / "ios-build.yml.template"
    if not p.is_file():
        die(
            2,
            f"缺少 workflow 模板：{p}",
            "恢复 builder/ 目录（该文件是 ios-build.yml 的单一来源模板）后重试。",
        )
    return p


def substitutions(app_name: str, opts: argparse.Namespace, bundle_id: str) -> dict:
    signing = FALSE_TOKEN if opts.unsigned else TRUE_TOKEN
    return {
        APP_NAME_PH: app_name,
        BUNDLE_ID_PH: bundle_id,
        IOS_MIN_PH: opts.ios_min,
        SWIFT_VERSION_PH: opts.swift_version,
        GH_OWNER_PH: opts.owner,
        GH_REPO_PH: opts.repo,
        SIGNING_PH: signing,
    }


def render_text(text: str, mapping: dict) -> str:
    for key, value in mapping.items():
        text = text.replace(key, value)
    # builder.json 里的布尔占位符必须落成真正的 JSON 字面量
    return text.replace(TRUE_TOKEN, "true").replace(FALSE_TOKEN, "false")


# ----------------------------------------------------------- git probing ---
def detect_github_repo(cwd: Path) -> tuple:
    """从 git remote origin 解析 owner/repo；失败返回 ("", "")。"""
    try:
        out = subprocess.run(
            ["git", "config", "--get", "remote.origin.url"],
            cwd=str(cwd), capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return "", ""
    url = (out.stdout or "").strip()
    if not url:
        return "", ""
    m = re.search(r"[:/]([^/:]+)/([^/:]+?)(?:\.git)?$", url)
    if not m:
        return "", ""
    return m.group(1), m.group(2)


# --------------------------------------------------------------- naming ----
def sanitize_app_name(name: str) -> str:
    """Xcode target/product 名：字母开头，仅字母数字下划线，不含空格与连字符。"""
    cleaned = re.sub(r"[^A-Za-z0-9_]", "_", name.strip())
    if not cleaned:
        die(3, f"app 名无效：{name!r}", "用字母开头、仅含字母数字下划线的名字，例如 MyApp。")
    if not cleaned[0].isalpha():
        cleaned = "App" + cleaned
    if cleaned != name.strip():
        print(f"[WARN ] app 名已规范化：{name!r} -> {cleaned!r}（Xcode target 名不允许空格/连字符）")
    return cleaned


def bundle_id_from(org: str, app_name: str) -> str:
    org = org.strip().strip(".").lower() or DEFAULT_ORG
    tail = re.sub(r"[^a-z0-9_]", "", app_name.lower()) or "app"
    return f"{org}.{tail}"


# ------------------------------------------------------------- copying -----
def relocators(framework: str, app_name: str):
    """模板目录 -> 目标工程目录的重定位规则（见 templates/ 的目录约定）。

    templates/swiftui-starter/ 的布局是给脚本看的，不是给工程用的：
      app/**                       -> <AppName>/**
      xcodeproj/**                 -> **（摊平，去掉 xcodeproj/ 这层壳）
      gitignore                    -> .gitignore（避免模板目录里的 .gitignore 影响本仓库）
      builder.json / 其余文件      -> 原位
    flutter / react-native 模板按原结构落盘，只重命名 gitignore。
    """
    def move(rel: str) -> str:
        if rel == "gitignore":
            return ".gitignore"
        if framework != "swiftui":
            return rel
        if rel.startswith("app/"):
            return f"{app_name}/" + rel[len("app/"):]
        if rel.startswith("xcodeproj/"):
            return rel[len("xcodeproj/"):]
        return rel
    return move


def copy_tree(src: Path, dst: Path, mapping: dict, skip: set, relocate) -> list:
    """递归渲染模板目录：文件名、目录名与内容都做占位符替换。返回落盘文件列表。"""
    written = []
    for item in sorted(src.rglob("*")):
        if not item.is_file():
            continue
        rel = str(item.relative_to(src)).replace(os.sep, "/")
        if rel in skip:
            continue
        rel_name = render_text(relocate(rel), mapping)
        target = dst / rel_name
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            text = item.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            shutil.copy2(item, target)
        else:
            target.write_text(render_text(text, mapping), encoding="utf-8", newline="\n")
        written.append(target)
    return written


def normalize_builder_json(project_dir: Path, framework: str, scheme: str) -> None:
    """校验并回写 builder.json：占位符渲染后必须仍是合法 JSON，且 ios.path/scheme 正确。"""
    cfg_path = project_dir / "builder.json"
    if not cfg_path.is_file():
        return
    try:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        die(2, f"模板渲染后的 builder.json 不是合法 JSON：{exc}",
            f"修模板：{repo_root() / 'templates' / (framework + '-starter') / 'builder.json'}")
    cfg.setdefault("ios", {})["path"] = IOS_PATH_BY_FRAMEWORK.get(framework, ".")
    cfg["ios"]["scheme"] = scheme
    cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8", newline="\n")


def write_workflow(project_dir: Path, tpl: Path, mapping: dict) -> Path:
    dest = project_dir / ".github" / "workflows" / "ios-build.yml"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(render_text(tpl.read_text(encoding="utf-8"), mapping),
                    encoding="utf-8", newline="\n")
    return dest


# ------------------------------------------------------------ questions ----
def ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    try:
        answer = input(f"{prompt}{suffix}: ").strip()
    except EOFError:
        return default
    return answer or default


def interactive_defaults() -> dict:
    print("iOS 工程脚手架（builder 远程构建版）—— 直接回车取默认值")
    name = ask("App 名（字母开头，仅字母数字下划线）", "MyApp")
    out = ask("输出根目录", ".")
    framework = ask(f"工程形态 {'/'.join(FRAMEWORKS)}", DEFAULT_FRAMEWORK)
    org = ask("Bundle ID 前缀", DEFAULT_ORG)
    owner = ask("GitHub owner", "")
    repo = ask("GitHub repo", name)
    return {"name": name, "output": out, "framework": framework,
            "org": org, "owner": owner, "repo": repo}


# ------------------------------------------------------------------ main ---
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="init_ios_project.py",
        description="生成可被 builder ios build 直接构建的 iOS 工程骨架",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("Usage:")[0],
    )
    p.add_argument("name", nargs="?", help="app / target 名，例如 MyApp")
    p.add_argument("target", nargs="?", help="输出根目录（等价于 -o，兼容旧写法）")
    p.add_argument("-o", "--output", help="输出根目录，工程建在 <output>/<name> 下")
    p.add_argument("--framework", choices=FRAMEWORKS, default=DEFAULT_FRAMEWORK,
                   help=f"工程形态（默认 {DEFAULT_FRAMEWORK}）")
    p.add_argument("--unsigned", action="store_true",
                   help='生成的 builder.json 预设 "signing": false')
    p.add_argument("--org", default=DEFAULT_ORG, help="bundle id 前缀（默认 com.example）")
    p.add_argument("--bundle-id", dest="bundle_id", help="完整 bundle id，优先于 --org")
    p.add_argument("--ios-min", dest="ios_min", default=DEFAULT_IOS_MIN,
                   help=f"IPHONEOS_DEPLOYMENT_TARGET（默认 {DEFAULT_IOS_MIN}）")
    p.add_argument("--swift-version", dest="swift_version", default=DEFAULT_SWIFT_VERSION,
                   help=f"SWIFT_VERSION 语言模式（默认 {DEFAULT_SWIFT_VERSION}）")
    p.add_argument("--scheme", help="Xcode scheme 名（默认等于 app 名；flutter 为 Runner）")
    p.add_argument("--owner", default="", help="GitHub owner（缺省从 git remote 探测）")
    p.add_argument("--repo", default="", help="GitHub repo 名（缺省探测，退化为 app 名）")
    p.add_argument("--force", action="store_true", help="目标已存在时先删除再重建")
    p.add_argument("--interactive", action="store_true", help="问答模式")
    return p


def normalize_framework(argv):
    """把 `--framework rn` / `reactnative` 归一成 react-native（文档里两种写法都出现过）。"""
    out = list(argv)
    for i, token in enumerate(out):
        if token == "--framework" and i + 1 < len(out):
            if out[i + 1].lower() in ("rn", "reactnative", "react-native"):
                out[i + 1] = "react-native"
        elif token.startswith("--framework="):
            if token.split("=", 1)[1].lower() in ("rn", "reactnative", "react-native"):
                out[i] = "--framework=react-native"
    return out


def main(argv=None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    args = build_parser().parse_args(normalize_framework(raw))

    if args.interactive:
        d = interactive_defaults()
        args.name = args.name or d["name"]
        args.output = args.output or args.target or d["output"]
        args.framework = d["framework"] if args.framework == DEFAULT_FRAMEWORK else args.framework
        args.org = d["org"]
        args.owner = args.owner or d["owner"]
        args.repo = args.repo or d["repo"]
    if not args.name:
        die(3, "缺少 app 名", "python init_ios_project.py <App名> [输出目录]，或加 --interactive")

    app_name = sanitize_app_name(args.name)
    out_root = Path(args.output or args.target or ".").expanduser()
    project_dir = out_root / app_name

    templates_dir = locate_templates()
    framework_dir = templates_dir / f"{args.framework}-starter"
    if not framework_dir.is_dir():
        die(2, f"模板不存在：{framework_dir}",
            f"--framework 只能是 {'/'.join(FRAMEWORKS)}")

    if project_dir.exists() and any(project_dir.iterdir()):
        if not args.force:
            die(1, f"目标目录已存在且非空：{project_dir}",
                "换目录，或加 --force 覆盖重建（--force 会先删除该目录）")
        shutil.rmtree(project_dir)

    bundle_id = args.bundle_id or bundle_id_from(args.org, app_name)
    scheme = args.scheme or DEFAULT_SCHEME_BY_FRAMEWORK[args.framework] or app_name

    owner, repo = args.owner, args.repo
    if not owner or not repo:
        det_owner, det_repo = detect_github_repo(Path.cwd())
        owner = owner or det_owner
        repo = repo or det_repo
    # 探测不到就留显式占位符：builder 校验 github.owner/repo 必填，
    # 空串会让 runner 报难以定位的 404，占位符至少能让人一眼看到要改哪里。
    if not owner:
        owner = "YOUR_GITHUB_USER"
    if not repo:
        repo = args.name or app_name
    mapping = substitutions(app_name, args, bundle_id) | {
        GH_OWNER_PH: owner, GH_REPO_PH: repo,
    }
    mapping["__GH_OWNER__"], mapping["__GH_REPO__"] = owner, repo

    project_dir.mkdir(parents=True, exist_ok=True)
    skip = {"README.md"}
    if args.framework != "swiftui":
        # flutter / react-native 模板只提供配置与源码占位，宿主工程由官方 CLI 生成
        skip |= {"ios-build.yml.template"}

    written = copy_tree(framework_dir, project_dir, mapping, skip, relocators(args.framework, app_name))

    wf = write_workflow(project_dir, workflow_template(templates_dir), mapping)
    written.append(wf)
    normalize_builder_json(project_dir, args.framework, scheme)

    unresolved = []
    for f in written:
        try:
            body = f.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for tok in re.findall(r"__[A-Z_]+__", body):
            unresolved.append((f, tok))
    if unresolved:
        for f, tok in unresolved[:5]:
            print(f"[WARN ] {f} 残留占位符 {tok}", file=sys.stderr)
        die(2, "模板渲染不完整（存在未替换占位符）",
            f"补全 {framework_dir} 里的占位符，或在 substitutions() 增加映射")

    print(f"\n已生成 {args.framework} 工程：{project_dir}")
    print(f"  app        : {app_name}")
    print(f"  bundle id  : {bundle_id}")
    print(f"  scheme     : {scheme}")
    print(f"  ios.path   : {IOS_PATH_BY_FRAMEWORK.get(args.framework, '.')}")
    owner_display = owner or "YOUR_GITHUB_USER(未探测到，需手填)"
    print(f"  github     : {owner_display}/{repo}")
    print(f"  builder.json: {project_dir / 'builder.json'}")
    print(f"  workflow    : {wf}")
    print(f"  文件数      : {len(written)}")

    owner_hint = "" if owner else f"\n  先手填 builder.json 的 github.owner/repo，否则 {APP_NAME_PH} 位置为 YOUR_GITHUB_USER"
    print("\n下一步：")
    print(f"  1. cd {project_dir}")
    if args.framework != "swiftui":
        gen = ("flutter create --platforms=ios --org %s --project-name %s ."
               % (args.org, app_name.lower()) if args.framework == "flutter"
               else "npx @react-native-community/cli init %s" % app_name)
        print(f"     然后生成 iOS 宿主工程：{gen}")
    print("  2. builder auth github")
    print("  3. builder init            # 权威 workflow 由 CLI 写回，与本仓库模板 diff 应一致")
    print("  4. builder ios build --unsigned")
    if not args.unsigned:
        print("     签名构建：builder signing setup --certificate <p12> --profile <mobileprovision>")
    print(owner_hint if owner_hint else "")
    return 0


if __name__ == "__main__":
    sys.exit(main())
