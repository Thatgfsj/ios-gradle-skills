#!/usr/bin/env python3
"""builder.json Config Patcher（AI 调用）

按目标工程的实际形态生成 builder.json 的**修改补丁**：先探测工程形态，再合并字段，
默认只输出 unified diff（不落盘），加 --write 才写入并保留备份。
Agent 用它替代手写 JSON——字段名与默认值与本仓库 builder/builder.template.json 同源。

Usage:
    python ios-builder/scripts/ai/patch_builder_config.py --project /path/to/MyApp
    python ios-builder/scripts/ai/patch_builder_config.py --project . --scheme MyApp --unsigned
    python ios-builder/scripts/ai/patch_builder_config.py --project . --write
    python ios-builder/scripts/ai/patch_builder_config.py --project . --detect-only

Options:
    --project DIR     目标工程根（必填，除非 --detect-only 配合位置参数）
    --framework NAME  强制指定形态：swiftui|expo|flutter|react-native|kmp|cordova|native
    --scheme NAME     覆盖 ios.scheme
    --bundle-id ID    覆盖 ios.bundleId
    --ios-path P      覆盖 ios.path
    --unsigned        写 ios.signing = false
    --signing         写 ios.signing = true（沿用无后缀三件套 Secrets）
    --profile NAME    追加 profiles.NAME = {"distribution": "<NAME>"} 并把 defaultProfile 指向它
    --owner / --repo  覆盖 github.owner / github.repo
    --mobai-url URL   覆盖 mobai.url（WSL NAT 下形如 http://PC名.local:8686）
    --metro-port N    写 reactNative.metroPort（代码里存在、README 未记录的字段）
    --write           真正写文件（先备份 builder.json.bak）
    --detect-only     只打印探测结果

退出码：
    0  无变更，或补丁生成/写入成功
    1  写入失败 / 目标 JSON 已损坏
    2  目标工程找不到（无 builder.json 且无法探测形态）
    3  参数非法
"""

import argparse
import difflib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parents[2] / "builder" / "builder.template.json"

# 形态 -> (判定文件名, ios.path, scheme 线索)
DETECT_ORDER = [
    ("kmp", ["iosApp"], "iosApp", None),
    ("cordova", ["config.xml", "platforms/ios"], "platforms/ios", None),
    ("expo", ["app.json", "app.config.js", "app.config.ts"], "ios", None),
    ("flutter", ["pubspec.yaml"], "ios", "Runner"),
    ("react-native", ["metro.config.js", "metro.config.ts", "react-native.config.js"], "ios", None),
    ("native", ["*.xcodeproj", "*.xcworkspace"], ".", None),
]


def die(code: int, msg: str, hint: str = "") -> None:
    print(f"[ERROR] {msg}", file=sys.stderr)
    if hint:
        print(f"[HINT ] {hint}", file=sys.stderr)
    sys.exit(code)


def detect_form(root: Path) -> tuple:
    """返回 (framework, ios_path, scheme)。找不到任何 iOS 痕迹时返回 (None, ...)。"""
    for form, needles, ios_path, scheme in DETECT_ORDER:
        for needle in needles:
            if needle.startswith("*"):
                if list(root.glob(needle)):
                    return form, ios_path, scheme
            elif needle.endswith("/ios") or "/" in needle:
                if (root / needle).exists():
                    return form, ios_path, scheme
            elif (root / needle).exists():
                return form, ios_path, scheme
    return None, None, None


def guess_scheme(root: Path, ios_path: str) -> str:
    base = root / ios_path if ios_path not in (".", "") else root
    for proj in sorted(base.glob("*.xcodeproj")):
        return proj.stem
    for ws in sorted(base.glob("*.xcworkspace")):
        if ws.parent != base:            # Contents.xcworkspace 在 .xcodeproj 内部，跳过
            continue
        return ws.stem
    return ""


def bundle_id_from_project(root: Path, ios_path: str) -> str:
    """从 pbxproj 里读 PRODUCT_BUNDLE_IDENTIFIER（取第一个非变量值）。"""
    base = root / ios_path if ios_path not in (".", "") else root
    for pbx in base.glob("*.xcodeproj/project.pbxproj"):
        text = pbx.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r"PRODUCT_BUNDLE_IDENTIFIER\s*=\s*([^;]+);", text):
            value = m.group(1).strip().strip('"')
            if "$(" not in value and value:
                return value
    return ""


def git_owner_repo(root: Path) -> tuple:
    try:
        out = subprocess.run(["git", "-C", str(root), "config", "--get", "remote.origin.url"],
                             capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return "", ""
    url = (out.stdout or "").strip()
    m = re.search(r"[:/]([^/:]+)/([^/:]+?)(?:\.git)?$", url)
    return (m.group(1), m.group(2)) if m else ("", "")


def load_base() -> dict:
    if not TEMPLATE.is_file():
        die(1, f"缺少模板：{TEMPLATE}", "恢复 builder/builder.template.json（它是配置的单一来源）。")
    data = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    data.pop("_comment", None)
    return data


def merge(cfg: dict, args: argparse.Namespace, root: Path) -> tuple:
    """返回 (新 cfg, 变更说明列表)。只改被显式指定或探测出的字段。"""
    notes = []
    form, ios_path, scheme = detect_form(root)
    if args.framework:
        form = args.framework
    for f, _needles, p, s in DETECT_ORDER:
        if f == form:
            ios_path = ios_path or p
            scheme = scheme or s
    if args.ios_path:
        ios_path = args.ios_path
    if ios_path is None:
        die(2, f"探测不到 iOS 工程：{root}",
            "确认目录里有 *.xcodeproj / ios/ / platforms/ios / iosApp/，或用 --framework 与 --ios-path 指定")

    if form not in ("native", "swiftui"):
        cfg.setdefault("ios", {})["path"] = ios_path
        notes.append(f"ios.path -> {ios_path}（形态 {form}）")
    else:
        cfg.setdefault("ios", {})["path"] = ios_path

    final_scheme = args.scheme or scheme or guess_scheme(root, ios_path)
    if final_scheme and cfg["ios"].get("scheme") != final_scheme:
        cfg["ios"]["scheme"] = final_scheme
        notes.append(f"ios.scheme -> {final_scheme}")

    if args.bundle_id:
        cfg["ios"]["bundleId"] = args.bundle_id
        notes.append(f"ios.bundleId -> {args.bundle_id}")
    else:
        probed = bundle_id_from_project(root, ios_path)
        if probed and not cfg["ios"].get("bundleId"):
            cfg["ios"]["bundleId"] = probed
            notes.append(f"ios.bundleId -> {probed}（读自 pbxproj）")

    if args.unsigned and args.signing:
        die(3, "--unsigned 与 --signing 互斥", "unsigned 出包用 --unsigned；走签名 Secrets 用 --signing")
    if args.unsigned:
        cfg["ios"]["signing"] = False
        notes.append("ios.signing -> false")
    if args.signing:
        cfg["ios"]["signing"] = True
        notes.append("ios.signing -> true（无后缀三件套 Secrets）")

    if args.profile:
        cfg.setdefault("profiles", {})[args.profile] = {"distribution": args.profile}
        cfg["defaultProfile"] = args.profile
        cfg["ios"]["signing"] = False
        notes.append(f"profiles.{args.profile}.distribution -> {args.profile}；defaultProfile -> {args.profile}")

    owner, repo = args.owner, args.repo
    if not owner or not repo:
        g_owner, g_repo = git_owner_repo(root)
        owner = owner or g_owner
        repo = repo or g_repo
    if owner:
        cfg.setdefault("github", {})["owner"] = owner
    if repo:
        cfg.setdefault("github", {})["repo"] = repo
    if owner or repo:
        notes.append(f"github -> {owner or '(未填)'}/{repo or '(未填)'}")

    if args.mobai_url:
        cfg.setdefault("mobai", {})["url"] = args.mobai_url
        notes.append(f"mobai.url -> {args.mobai_url}")
    if args.metro_port:
        cfg.setdefault("reactNative", {})["metroPort"] = args.metro_port
        notes.append(f"reactNative.metroPort -> {args.metro_port}（README 未记录的字段）")

    cfg.setdefault("project", root.name)
    cfg["platform"] = "ios"
    return cfg, notes


def diff_text(old: str, new: str, label: str) -> str:
    return "".join(difflib.unified_diff(
        old.splitlines(keepends=True), new.splitlines(keepends=True),
        fromfile=f"a/{label}", tofile=f"b/{label}"))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="patch_builder_config.py",
                                 description="探测工程形态并生成 builder.json 补丁")
    ap.add_argument("--project", default=".", help="目标工程根目录（默认当前目录）")
    ap.add_argument("--framework", choices=["swiftui", "native", "expo", "flutter",
                                           "react-native", "kmp", "cordova"])
    ap.add_argument("--scheme")
    ap.add_argument("--bundle-id", dest="bundle_id")
    ap.add_argument("--ios-path", dest="ios_path")
    ap.add_argument("--unsigned", action="store_true")
    ap.add_argument("--signing", action="store_true")
    ap.add_argument("--profile", help="追加 profiles.<name> 并设为 defaultProfile")
    ap.add_argument("--owner", default="")
    ap.add_argument("--repo", default="")
    ap.add_argument("--mobai-url", dest="mobai_url")
    ap.add_argument("--metro-port", dest="metro_port", type=int)
    ap.add_argument("--write", action="store_true", help="写入 builder.json（先备份 .bak）")
    ap.add_argument("--detect-only", action="store_true")
    ap.add_argument("--create", action="store_true", help="目标没有 builder.json 时基于模板新建")
    args = ap.parse_args(argv if argv is not None else sys.argv[1:])

    root = Path(args.project).expanduser().resolve()
    if not root.is_dir():
        die(2, f"目录不存在：{root}", "先执行 python ios-builder/scripts/init_ios_project.py <App名> <目录>")

    form, ios_path, scheme = detect_form(root)
    if args.detect_only:
        print(json.dumps({"framework": form, "ios_path": ios_path,
                          "scheme": scheme or guess_scheme(root, ios_path or "."),
                          "bundleId": bundle_id_from_project(root, ios_path or "."),
                          "github": dict(zip(("owner", "repo"), git_owner_repo(root)))},
                         ensure_ascii=False, indent=2))
        return 0

    target = root / "builder.json"
    if target.is_file():
        try:
            base = json.loads(target.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            die(1, f"{target} 不是合法 JSON：{exc}",
                "先修好 JSON（或用 --create 从模板重建，旧文件请手工备份）")
        old_text = target.read_text(encoding="utf-8")
    elif args.create:
        base = load_base()
        old_text = ""
    else:
        die(2, f"{target} 不存在",
            "跑 builder init，或本脚本加 --create 从 builder/builder.template.json 新建")

    new_cfg, notes = merge(base, args, root)
    new_text = json.dumps(new_cfg, ensure_ascii=False, indent=2) + "\n"

    if not notes:
        print("无需变更：现有 builder.json 已与探测结果一致")
        return 0
    print("变更项：")
    for n in notes:
        print(f"  - {n}")
    patch = diff_text(old_text, new_text, "builder.json")
    print("\n" + (patch if patch else "(与现有内容一致)\n"))

    if args.write:
        if target.exists():
            shutil.copy2(target, target.with_suffix(".json.bak"))
            print(f"已备份 -> {target.with_suffix('.json.bak')}")
        try:
            target.write_text(new_text, encoding="utf-8", newline="\n")
        except OSError as exc:
            die(1, f"写入失败：{exc}", "检查目录权限，或先 --write 到别的目录再移动")
        print(f"已写入 {target}")
    else:
        print("预览模式：加 --write 才落盘（写前自动备份 builder.json.bak）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
