#!/usr/bin/env python3
"""Remote Build Trigger / Poller（运维）

在没有 builder CLI 的机器上（或需要把构建嵌进别的流水线时）复现 `builder ios build`
的核心动作：dispatch 仓库里的 ios-build.yml、轮询 run、把名为 ipa 的 artifact 落到 ./dist/。

与 builder CLI 的**关键差异**：本脚本不推工作区快照（hidden ref refs/ios-builder/jobs/<id>），
它构建的是远端默认分支上**已提交的代码**。想验证未提交的改动，必须回到 builder ios build。

Usage:
    python ios-builder/scripts/ops/trigger_build.py --project /path/to/MyApp --unsigned
    python ios-builder/scripts/ops/trigger_build.py --project . --profile store --build-number 12
    python ios-builder/scripts/ops/trigger_build.py --project . --dry-run
    python ios-builder/scripts/ops/trigger_build.py --project . --tag-fallback   # GitHub API 不可达时
    python ios-builder/scripts/ops/trigger_build.py --download-only <run-id>

Options:
    --project DIR         目标工程根（读它的 builder.json），默认当前目录
    --workflow NAME       workflow 文件名，默认 ios-build.yml
    --ref GIT_REF         触发用的分支/SHA，默认 builder.json 里的 branch 或 main
    --profile NAME        选 profiles.NAME（解析成 profile JSON input，与 --unsigned 互斥时以 unsigned 为准）
    --unsigned            use_signing=false（等价 builder ios build --unsigned）
    --configuration NAME  覆盖 configuration（Debug / Release）
    --build-number N      CFBundleVersion，或 X.Y.Z+N 同时设 marketing version
    --timeout MINUTES     轮询上限，默认 90（与 workflow 的 timeout-minutes 对齐）
    --poll-interval SEC   轮询间隔，默认 20
    --dist-dir DIR        artifact 落地目录，默认 ./dist
    --no-wait             触发后立即返回，打印 run id
    --tag-fallback        改用 git tag ios-build/<id> 触发（无 API 权限时的上游应急通道）
    --download-only ID    不触发，只下载指定 run 的 ipa artifact
    --dry-run             只打印将要发送的 inputs JSON
    --json                结构化输出

鉴权：优先用已登录的 gh（builder auth github 也会写它）；无 gh 时读 GITHUB_TOKEN。

退出码：
    0  构建成功且已下载 IPA
    1  构建失败 / 被取消 / 超时
    2  builder.json 缺失或非法、owner/repo 未填
    3  环境缺 gh 且无 GITHUB_TOKEN
"""

import argparse
import json
import shutil
import os
import subprocess
import sys
import time
import urllib.request
import uuid
import zipfile
from pathlib import Path

API = "https://api.github.com"


def die(code: int, msg: str, hint: str = "") -> None:
    print(f"[ERROR] {msg}", file=sys.stderr)
    if hint:
        print(f"[HINT ] {hint}", file=sys.stderr)
    sys.exit(code)


def have(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def run(cmd, cwd=None, capture=True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=str(cwd) if cwd else None,
                          capture_output=capture, text=True, timeout=600)


def read_cfg(project: Path) -> dict:
    cfg = project / "builder.json"
    if not cfg.is_file():
        die(2, f"缺少 {cfg}", "先执行 builder init，或 python ios-builder/scripts/ai/patch_builder_config.py --project <目录> --create --write")
    try:
        data = json.loads(cfg.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        die(2, f"{cfg} 不是合法 JSON：{exc}", "修 JSON 后重试")
    owner = (data.get("github") or {}).get("owner")
    repo = (data.get("github") or {}).get("repo")
    if not owner or not repo or "YOUR_" in str(owner) + str(repo):
        die(2, f"{cfg} 的 github.owner/repo 未填", "填成真实仓库，或跑 builder init 自动探测")
    return data


def auth_or_die() -> str:
    if have("gh"):
        return "gh"
    if os.environ.get("GITHUB_TOKEN"):
        return "rest"
    die(3, "既没有 gh CLI，也没有 GITHUB_TOKEN",
        "安装 gh（https://cli.github.com），或 export GITHUB_TOKEN=<有 repo 写权限的 token>")
    return ""


def api_get(path: str, mode: str) -> dict:
    if mode == "gh":
        p = run(["gh", "api", path])
        if p.returncode != 0:
            die(1, f"gh api 失败：{p.stderr.strip()[:300]}", "确认 builder auth github 已完成，或 token 有 Actions 读权限")
        return json.loads(p.stdout or "{}")
    req = urllib.request.Request(f"{API}{path}", headers={
        "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "ios-gradle-skills",
    })
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def api_post(path: str, payload: dict, mode: str) -> int:
    if mode == "gh":
        p = run(["gh", "api", "-X", "POST", path, "--input", "-"],
                capture=True)
        if p.returncode != 0:
            die(1, f"触发失败：{p.stderr.strip()[:300]}",
                "多半是 workflow 里不存在某个 input（旧版 workflow），跑 builder init 刷新后重试")
        return 204
    req = urllib.request.Request(f"{API}{path}", data=json.dumps(payload).encode(),
                                headers={"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
                                         "Accept": "application/vnd.github+json",
                                         "Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.status


def build_inputs(cfg: dict, args: argparse.Namespace) -> dict:
    ios = cfg.get("ios") or {}
    profile_blob = {}
    if args.profile:
        profiles = cfg.get("profiles") or {}
        if args.profile not in profiles:
            die(2, f"builder.json 里没有 profile {args.profile}",
                f"可用：{sorted(profiles) or '（一个都没有）'}；上游对未知 profile 名会列出候选")
        profile_blob = {"name": args.profile}
        profile_blob.update({k: v for k, v in profiles[args.profile].items() if isinstance(v, (str, dict))})
    use_signing = "false" if (args.unsigned or not profile_blob) else "true"
    configuration = args.configuration or (ios.get("configuration") or "Debug")
    if profile_blob:
        dist = profile_blob.get("distribution", "")
        if not args.configuration:
            configuration = "Debug" if dist == "development" else ("Release" if dist else configuration)
    return {
        "build_id": f"sk-{int(time.time())}-{uuid.uuid4().hex[:6]}",
        "snapshot_ref": "",                     # 本脚本不推快照，见文件头差异说明
        "ios_path": args.ios_path or ios.get("path") or ".",
        "scheme": args.scheme or ios.get("scheme") or "",
        "use_signing": use_signing,
        "configuration": configuration,
        "flutter_version": (cfg.get("flutter") or {}).get("version") or "",
        "jdk_version": str((cfg.get("kmp") or {}).get("jdkVersion") or "17"),
        "profile": json.dumps(profile_blob, ensure_ascii=False),
        "build_number": args.build_number or "",
    }


def poll_run(owner: str, repo: str, workflow: str, since_iso: str, mode: str,
             timeout_min: int, interval: int) -> dict:
    deadline = time.time() + timeout_min * 60
    run_id = None
    while time.time() < deadline:
        data = api_get(f"/repos/{owner}/{repo}/actions/workflows/{workflow}/runs?per_page=5&created=<{since_iso}", mode)
        runs = data.get("workflow_runs") or []
        if runs and run_id is None:
            run_id = runs[0]["id"]
            print(f"run {run_id}  queueing: {runs[0].get('status')}  url: {runs[0].get('html_url')}")
        if run_id is not None:
            one = api_get(f"/repos/{owner}/{repo}/actions/runs/{run_id}", mode)
            status, conclusion = one.get("status"), one.get("conclusion")
            if status in ("completed",):
                print(f"run {run_id} completed: {conclusion}")
                return one
            print(f"  [{time.strftime('%H:%M:%S')}] {status} ...")
        time.sleep(interval)
    die(1, f"等待超过 {timeout_min} 分钟", "在 GitHub Actions 页面看该 run 是否卡在排队（免费档 macOS 排队可能很久）")
    return {}


def download_artifact(owner: str, repo: str, run_id: int, dest: Path, mode: str) -> Path:
    data = api_get(f"/repos/{owner}/{repo}/actions/runs/{run_id}/artifacts", mode)
    items = data.get("artifacts") or []
    target = next((a for a in items if a.get("name") == "ipa"), None)
    if target is None:
        die(1, f"run {run_id} 没有名为 ipa 的 artifact（有：{[a.get('name') for a in items]}）",
            "构建可能没产出 build/*.ipa——用 python ios-builder/scripts/ai/analyze_build_log.py 看日志")
    dest.mkdir(parents=True, exist_ok=True)
    zip_path = dest / f"run-{run_id}-ipa.zip"
    if mode == "gh":
        p = run(["gh", "api", f"/repos/{owner}/{repo}/actions/artifacts/{target['id']}/zip", "-o", str(zip_path)])
        if p.returncode != 0:
            die(1, f"下载 artifact 失败：{p.stderr.strip()[:200]}")
    else:
        req = urllib.request.Request(target["archive_download_url"], headers={
            "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}"})
        with urllib.request.urlopen(req, timeout=300) as resp, open(zip_path, "wb") as fh:
            shutil.copyfileobj(resp, fh)
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        zf.extractall(dest)
    zip_path.unlink(missing_ok=True)
    print(f"已解出 {len(names)} 个文件到 {dest}")
    ipas = sorted(dest.rglob("*.ipa"))
    if not ipas:
        die(1, f"{dest} 里没有 .ipa", "检查 workflow 的 artifact path（上游是 build/*.ipa）")
    return ipas[0]


def tag_fallback(owner: str, repo: str, args: argparse.Namespace, inputs: dict) -> str:
    tag = f"ios-build/{inputs['build_id']}"
    p = run(["git", "tag", tag])
    if p.returncode != 0:
        die(1, f"打 tag 失败：{p.stderr.strip()[:200]}")
    p = run(["git", "push", "origin", tag])
    if p.returncode != 0:
        die(1, f"push tag 失败：{p.stderr.strip()[:200]}",
            "tag 触发用的就是上游的 git-only 通道；先确认本地有 origin 且已提交")
    print(f"已推送 {tag}；tag 通道不传 flags，profile 取 builder.json 的 defaultProfile")
    return tag


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="trigger_build.py", description="触发并轮询远程 iOS 构建")
    ap.add_argument("--project", default=".")
    ap.add_argument("--workflow", default="ios-build.yml")
    ap.add_argument("--ref", default="")
    ap.add_argument("--profile", default="")
    ap.add_argument("--unsigned", action="store_true")
    ap.add_argument("--configuration", default="")
    ap.add_argument("--build-number", dest="build_number", default="")
    ap.add_argument("--scheme", default="")
    ap.add_argument("--ios-path", dest="ios_path", default="")
    ap.add_argument("--timeout", type=int, default=90)
    ap.add_argument("--poll-interval", dest="poll_interval", type=int, default=20)
    ap.add_argument("--dist-dir", dest="dist_dir", default="")
    ap.add_argument("--no-wait", action="store_true")
    ap.add_argument("--tag-fallback", action="store_true")
    ap.add_argument("--download-only", dest="download_only", default="")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv if argv is not None else sys.argv[1:])

    project = Path(args.project).expanduser().resolve()
    cfg = read_cfg(project)
    owner = cfg["github"]["owner"]
    repo = cfg["github"]["repo"]
    inputs = build_inputs(cfg, args)
    dest = Path(args.dist_dir) if args.dist_dir else project / "dist"

    if args.dry_run:
        print(json.dumps({"workflow": args.workflow, "ref": args.ref or "main",
                          "inputs": inputs}, ensure_ascii=False, indent=2))
        print("\n注意：snapshot_ref 为空表示构建远端已提交代码；未提交改动请用 builder ios build")
        return 0

    mode = auth_or_die()

    if args.download_only:
        path = download_artifact(owner, repo, int(args.download_only), dest, mode)
        print(f"IPA: {path}")
        return 0

    if args.tag_fallback:
        tag_fallback(owner, repo, args, inputs)
        if args.no_wait:
            return 0
        run_info = poll_run(owner, repo, args.workflow, time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                            mode, args.timeout, args.poll_interval)
    else:
        ref = args.ref or "main"
        start = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        api_post(f"/repos/{owner}/{repo}/actions/workflows/{args.workflow}/dispatches",
                 {"ref": ref, "inputs": inputs}, mode)
        print(f"已 dispatch {args.workflow} @ {ref}（build_id={inputs['build_id']}）")
        if args.no_wait:
            return 0
        run_info = poll_run(owner, repo, args.workflow, start, mode, args.timeout, args.poll_interval)

    conclusion = run_info.get("conclusion")
    if conclusion != "success":
        print(f"[FAIL] run {run_info.get('id')} 结论={conclusion}，日志取法：", file=sys.stderr)
        print("  gh run view %d --log > build.log" % int(run_info.get("id") or 0), file=sys.stderr)
        print("  python ios-builder/scripts/ai/analyze_build_log.py build.log", file=sys.stderr)
        return 1

    ipa = download_artifact(owner, repo, int(run_info["id"]), dest, mode)
    result = {"run_id": run_info["id"], "ipa": str(ipa), "dist": str(dest)}
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"IPA 已落地：{ipa}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
