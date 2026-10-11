#!/usr/bin/env python3
"""Signing Secrets Checker（运维）

签名构建失败前，先把三件事查清楚：仓库里 Secret 名字齐不齐、本地 .p12/.mobileprovision
能不能用、描述文件类型与所选 distribution 是否匹配。本脚本不需要 Mac，也不打印 Secret 值。

Usage:
    python ios-builder/scripts/ops/check_signing_secrets.py --project /path/to/MyApp
    python ios-builder/scripts/ops/check_signing_secrets.py --project . --distribution store
    python ios-builder/scripts/ops/check_signing_secrets.py --project . --profile store
    python ios-builder/scripts/ops/check_signing_secrets.py --local-only \
        --p12 ios-signing-development.p12 --profile Builder-development-com.example.app.mobileprovision
    python ios-builder/scripts/ops/check_signing_secrets.py --project . --json

Options:
    --project DIR         目标工程根（读 builder.json 的 github.owner/repo、ios.extensions、profiles）
    --distribution NAME   development | ad-hoc | internal | store | enterprise | legacy（默认按 builder.json 推断）
    --profile NAME        builder.json 里 profiles.<NAME>，用它的 distribution 决定 Secrets 集合
    --owner / --repo      覆盖 builder.json 里的仓库坐标
    --p12 PATH            本地证书文件
    --password ENVVAR     存放 p12 口令的**环境变量名**（不要把口令写在命令行上）
    --profile-file PATH   本地 .mobileprovision（与 --profile 语义不同：这是文件路径）
    --local-only          跳过远端 Secrets 查询，只查本地文件
    --json                结构化输出

Secrets 命名规则（ios-builder v0.11.0，大小写敏感）：
    legacy（无 profile）      IOS_CERTIFICATE / IOS_CERTIFICATE_PASSWORD / IOS_PROVISIONING_PROFILE
    development              *_DEVELOPMENT
    ad-hoc / internal        *_AD_HOC
    store                    *_STORE
    enterprise               *_ENTERPRISE
    有 extension target 时   IOS_EXTENSION_PROFILES_<SET>（JSON：bundle id -> base64 profile）

退出码：
    0  全部就位
    1  有缺失 / 描述文件已过期 / 类型与 distribution 不匹配
    2  builder.json 缺失或非法
    3  既没有 gh CLI 也没有 GITHUB_TOKEN，且未加 --local-only
"""

import argparse
import base64
import json
import os
import plistlib
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE_NAMES = ["IOS_CERTIFICATE", "IOS_CERTIFICATE_PASSWORD", "IOS_PROVISIONING_PROFILE"]
SUFFIX = {
    "": "",
    "legacy": "",
    "development": "DEVELOPMENT",
    "ad-hoc": "AD_HOC",
    "internal": "AD_HOC",
    "store": "STORE",
    "enterprise": "ENTERPRISE",
}


def die(code: int, msg: str, hint: str = "") -> None:
    print(f"[ERROR] {msg}", file=sys.stderr)
    if hint:
        print(f"[HINT ] {hint}", file=sys.stderr)
    sys.exit(code)


def read_cfg(project: Path) -> dict:
    cfg = project / "builder.json"
    if not cfg.is_file():
        return {}
    try:
        return json.loads(cfg.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        die(2, f"{cfg} 不是合法 JSON：{exc}", "先修 JSON")
    return {}


def expected_names(distribution: str, extensions: list) -> list:
    suffix = SUFFIX.get(distribution.lower() if distribution else "", None)
    if suffix is None:
        die(2, f"未知 distribution：{distribution}",
            "可选 development / ad-hoc / internal / store / enterprise / legacy")
    names = [f"{n}{('_' + suffix) if suffix else ''}" for n in BASE_NAMES]
    if extensions:
        names.append("IOS_EXTENSION_PROFILES_" + (suffix or "LEGACY"))
    return names


def list_remote_secrets(owner: str, repo: str) -> list:
    if shutil.which("gh"):
        p = subprocess.run(["gh", "api", f"repos/{owner}/{repo}/actions/secrets",
                            "--jq", ".secrets[].name"], capture_output=True, text=True, timeout=60)
        if p.returncode != 0:
            die(1, f"gh api 失败：{p.stderr.strip()[:200]}",
                "确认已 builder auth github 或 gh auth login，且 token 能读 Actions Secrets")
        return [ln.strip() for ln in p.stdout.splitlines() if ln.strip()]
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        die(3, "没有 gh CLI 也没有 GITHUB_TOKEN", "装 gh，或 export GITHUB_TOKEN，或加 --local-only")
    import urllib.request
    req = urllib.request.Request(f"https://api.github.com/repos/{owner}/{repo}/actions/secrets",
                                 headers={"Authorization": f"Bearer {token}",
                                          "Accept": "application/vnd.github+json",
                                          "User-Agent": "ios-gradle-skills"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return [s["name"] for s in data.get("secrets", [])]


def extract_plist(path: Path) -> dict:
    """解 .mobileprovision：先试 openssl smime，失败再在原始字节里捞 XML plist。"""
    if shutil.which("openssl"):
        with subprocess.Popen(
            ["openssl", "smime", "-verify", "-noverify", "-inform", "DER", "-in", str(path)],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL) as proc:
            out, _ = proc.communicate()
            if out:
                try:
                    return plistlib.loads(out)
                except Exception:
                    pass
    raw = path.read_bytes()
    start, end = raw.find(b"<?xml"), raw.rfind(b"</plist>")
    if start == -1 or end == -1:
        raise ValueError("文件里找不到 plist（不是有效的 .mobileprovision？）")
    return plistlib.loads(raw[start:end + len(b"</plist>")])


def inspect_profile(path: Path) -> dict:
    info = extract_plist(path)
    ents = info.get("Entitlements") or {}
    devices = info.get("ProvisionedDevices") or []
    get_task_allow = bool(ents.get("get-task-allow"))
    if info.get("ProvisionsAllDevices"):
        kind = "enterprise"
    elif devices and get_task_allow:
        kind = "development"
    elif devices and not get_task_allow:
        kind = "ad-hoc"
    else:
        kind = "store"
    exp = info.get("ExpirationDate")
    days = None
    if isinstance(exp, datetime):
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        days = (exp - datetime.now(timezone.utc)).days
    return {
        "Name": info.get("Name"),
        "TeamName": info.get("TeamName"),
        "TeamIdentifier": (info.get("TeamIdentifier") or [None])[0],
        "application-identifier": ents.get("application-identifier"),
        "kind": kind,
        "devices": len(devices),
        "get-task-allow": get_task_allow,
        "expires": exp.isoformat() if isinstance(exp, datetime) else None,
        "days_left": days,
    }


def inspect_p12(path: Path, password_env: str) -> dict:
    blob = path.read_bytes()
    out = {"bytes": len(blob), "base64_len": len(base64.b64encode(blob))}
    if shutil.which("openssl") and password_env:
        pw = os.environ.get(password_env, "")
        p = subprocess.run(["openssl", "pkcs12", "-info", "-nokeys", "-nomaciter",
                            "-passin", f"pass:{pw}"], input=blob,
                           capture_output=True, timeout=60)
        out["openssl_ok"] = p.returncode == 0
        if p.returncode != 0:
            out["openssl_error"] = (p.stderr.decode("utf-8", "replace").strip()[:200])
    else:
        out["openssl_ok"] = None
        out["note"] = "未提供口令环境变量，无法验证 p12 是否能解开"
    return out


def resolve_distribution(cfg: dict, args: argparse.Namespace) -> tuple:
    if args.distribution:
        return args.distribution, None
    profile = args.profile or cfg.get("defaultProfile") or ""
    if profile:
        prof = (cfg.get("profiles") or {}).get(profile)
        if prof is None:
            die(2, f"builder.json 里没有 profile {profile}",
                f"可用：{sorted((cfg.get('profiles') or {}).keys()) or '（无）'}")
        return (prof.get("distribution") or "legacy"), profile
    if (cfg.get("ios") or {}).get("signing"):
        return "legacy", None
    return "legacy", None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="check_signing_secrets.py", description="检查签名材料与 GitHub Secrets")
    ap.add_argument("--project", default=".")
    ap.add_argument("--distribution", default="")
    ap.add_argument("--profile", default="")
    ap.add_argument("--owner", default="")
    ap.add_argument("--repo", default="")
    ap.add_argument("--p12", default="")
    ap.add_argument("--password", default="", help="存放 p12 口令的环境变量名")
    ap.add_argument("--profile-file", dest="profile_file", default="")
    ap.add_argument("--local-only", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv if argv is not None else sys.argv[1:])

    project = Path(args.project).expanduser().resolve()
    cfg = read_cfg(project)
    distribution, profile = resolve_distribution(cfg, args)
    ios = cfg.get("ios") or {}
    extensions = ios.get("extensions") or []

    report = {"project": str(project), "distribution": distribution, "profile": profile,
              "expected_secrets": expected_names(distribution, extensions), "present": [],
              "missing": [], "local": {}, "problems": []}

    if args.p12:
        p = Path(args.p12)
        if not p.is_file():
            report["problems"].append(f"p12 文件不存在：{p}")
        else:
            report["local"]["p12"] = inspect_p12(p, args.password)
            if report["local"]["p12"].get("openssl_ok") is False:
                report["problems"].append("p12 解不开（口令错或文件坏）："
                                          + report["local"]["p12"].get("openssl_error", ""))
    if args.profile_file:
        p = Path(args.profile_file)
        if not p.is_file():
            report["problems"].append(f"描述文件不存在：{p}")
        else:
            try:
                info = inspect_profile(p)
            except (ValueError, plistlib.InvalidFileException) as exc:
                info = {}
                report["problems"].append(f"描述文件解析失败：{exc}")
            if info:
                report["local"]["mobileprovision"] = info
                if info.get("days_left") is not None and info["days_left"] < 0:
                    report["problems"].append(f"描述文件已过期 {-info['days_left']} 天")
                elif info.get("days_left") is not None and info["days_left"] < 30:
                    report["problems"].append(f"描述文件 {info['days_left']} 天后过期，尽快重签")
                want = "ad-hoc" if distribution in ("ad-hoc", "internal") else distribution
                if want in SUFFIX and want != "legacy" and info.get("kind") != want:
                    report["problems"].append(
                        f"描述文件类型是 {info.get('kind')}，所选 distribution 是 {distribution}；"
                        "runner 会在编译前按名字拒绝它")
                if info.get("kind") in ("development", "ad-hoc") and not info.get("devices"):
                    report["problems"].append("开发/Ad Hoc 描述文件里没有设备，装机必失败")
    if not args.profile_file and not args.local_only and distribution in ("development", "ad-hoc", "internal"):
        report["problems"].append("提示：development/ad-hoc 需要已登记设备；"
                                  "用 builder signing setup --devices-from-mobai 自动注册")

    if not args.local_only:
        owner = args.owner or (cfg.get("github") or {}).get("owner")
        repo = args.repo or (cfg.get("github") or {}).get("repo")
        if not owner or not repo or "YOUR_" in str(owner) + str(repo):
            die(2, f"{project / 'builder.json'} 的 github.owner/repo 未填",
                "填真实仓库，或加 --local-only 只查本地文件")
        present = set(list_remote_secrets(owner, repo))
        report["present"] = [n for n in report["expected_secrets"] if n in present]
        report["missing"] = [n for n in report["expected_secrets"] if n not in present]

    ok = not report["missing"] and not report["problems"]
    if args.json:
        report["ok"] = ok
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        return 0 if ok else 1

    print(f"工程     : {project}")
    print(f"通道     : distribution={distribution}" + (f" profile={profile}" if profile else ""))
    print(f"期望密钥 : {', '.join(report['expected_secrets'])}")
    if not args.local_only:
        print(f"已存在   : {', '.join(report['present']) or '(无)'}")
        print(f"缺失     : {', '.join(report['missing']) or '(无)'}")
    for key, value in report["local"].items():
        print(f"本地 {key}: {json.dumps(value, ensure_ascii=False, default=str)}")
    for problem in report["problems"]:
        print(f"[问题] {problem}")
    if report["missing"]:
        print("\n补齐命令（值来源见 .github/secrets.example.md）：")
        for name in report["missing"]:
            if name.endswith("_PASSWORD"):
                print(f"  gh secret set {name} --body \"$P12_PASSWORD\"")
            elif name.startswith("IOS_EXTENSION_PROFILES"):
                print("  gh secret set " + name + " --body '{\"<extensionBundleId>\": \"<base64 profile>\"}'")
                print("  （没有扩展目标时写空对象）")
            else:
                src = "ios-signing.p12" if "CERTIFICATE" in name else "App.mobileprovision"
                enc = "base64 -i {f} | tr -d '\\n'".format(f=src) if sys.platform == "darwin" \
                    else "base64 -w0 {f}".format(f=src)
                print(f"  gh secret set {name} < <({enc})")
        print("\n不想现在签名就先出未签名包：builder ios build --unsigned"
              "（装机时用 MobAI 免费 Apple ID 重签，bundle id 会带 TEAMID 后缀）")
    print("\n结果：" + ("全部就位" if ok else "需要处理"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
