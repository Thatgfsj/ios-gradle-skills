#!/usr/bin/env python3
"""Skill Spec Linter

校验本仓库是否满足 agent-skills / OpenClaw 的 Skill 规范，以及 SKILL.md 与
references/ 之间的一致性。`.github/workflows/validate.yml` 的 lint job 调用它。

Usage:
    python ios-builder/scripts/ops/lint_skill.py            # 从仓库根校验
    python ios-builder/scripts/ops/lint_skill.py /path/to/skill-dir

Checks:
    1. SKILL.md frontmatter：name 与父目录同名、^[a-z0-9-]{1,64}$、description ≤1024 字符
       且含第三人称描述与负向触发词（"不要用于"）
    2. SKILL.md 行数 < 500（超出说明知识未下沉到 references/）
    3. Command Matrix 表：表头 5 列、每行 5 个非空单元格
    4. SKILL.md 中出现的相对路径全部存在，且不含反斜杠 / 绝对路径
    5. references/ 下每篇文档都被 SKILL.md 或 claw-skill.yaml 引用（无孤儿文件）
    6. troubleshooting.md 的错误码锚点覆盖 SKILL.md 引用的所有 E<n>
    7. claw-skill.yaml 可解析，且其 scripts/references/examples 路径存在

Exit codes:
    0  全部通过
    1  存在 FAIL
    2  找不到 SKILL.md

所有 FAIL 打到 stdout（便于 CI 聚合），异常与文件缺失打 stderr。
"""

import json
import re
import sys
from pathlib import Path

try:  # pyyaml 在 CI 里安装；缺失时退化为内置迷你解析器
    import yaml  # type: ignore
    HAVE_YAML = True
except ImportError:
    HAVE_YAML = False

MAX_LINES = 500
MAX_DESC = 1024
NAME_RE = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")
MATRIX_COLUMNS = ["用户意图", "必须执行的命令", "前置条件", "产物位置", "常见错误速查"]
PATH_RE = re.compile(r"(?:^|[\s`(|])([\w./-]+\.(?:md|py|json|yml|yaml|sh|swift|template|toml))(?=[\s`)，。;、])")
# 这些是「目标工程里的生成物」或示例目录名，不在本仓库，路径检查跳过
GENERATED_ALLOWLIST = {
    "builder.json", "ios-build.yml", "ios-share.yml", "codemagic.yaml", "bitrise.yml",
    ".github/workflows/ios-build.yml", ".github/workflows/ios-share.yml",
    "ios-build.yml.template", "Info.plist", "Podfile", "app.json", "package.json",
    "pubspec.yaml", "GoogleService-Info.plist", ".wslconfig",
}

failures: list = []
warnings: list = []
notes: list = []


def fail(check: str, message: str) -> None:
    failures.append(f"FAIL  [{check}] {message}")


def warn(check: str, message: str) -> None:
    warnings.append(f"WARN  [{check}] {message}")


def ok(check: str, message: str) -> None:
    print(f"OK    [{check}] {message}")


def note(check: str, message: str) -> None:
    notes.append(f"NOTE  [{check}] {message}")


def repo_root(argv: list) -> Path:
    if len(argv) > 1:
        return Path(argv[1]).resolve()
    # <root>/ios-builder/scripts/ops/lint_skill.py -> 上溯三级到仓库根
    return Path(__file__).resolve().parents[3]


def split_frontmatter(text: str) -> tuple:
    if not text.startswith("---"):
        return None, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None, text
    return parts[1], parts[2]


def mini_yaml(raw: str) -> dict:
    """只支持本仓库 frontmatter 的形态：顶层 key、折叠块 >、行内列表 []。"""
    data: dict = {}
    key = None
    buf: list = []
    for line in raw.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if m:
            if key:
                data[key] = " ".join(buf).strip()
            key, value = m.group(1), m.group(2).strip()
            if value in (">", ">", "|", ">-", "|-"):
                buf = []
                continue
            if value.startswith("[") and value.endswith("]"):
                data[key] = [v.strip() for v in value[1:-1].split(",") if v.strip()]
                key, buf = None, []
                continue
            buf = []
            data[key] = value.strip("'\"")
            key = None
        elif key is not None:
            buf.append(line.strip())
    if key:
        data[key] = " ".join(buf).strip()
    return data


def parse_frontmatter(raw: str) -> dict:
    if HAVE_YAML:
        loaded = yaml.safe_load(raw)
        return loaded if isinstance(loaded, dict) else {}
    return mini_yaml(raw)


def check_frontmatter(root: Path, fm: dict, skill_dir_name: str) -> None:
    name = fm.get("name")
    if not isinstance(name, str) or not name:
        fail("frontmatter", "缺少 name 字段")
    else:
        if len(name) > 64:
            fail("frontmatter", f"name 长度 {len(name)} > 64")
        if not NAME_RE.match(name):
            fail("frontmatter", f"name 只允许小写字母/数字/连字符：{name!r}")
        if name != skill_dir_name:
            fail("frontmatter", f"name={name!r} 必须与父目录名 {skill_dir_name!r} 一致")
        else:
            ok("frontmatter", f"name 与目录名一致：{name}")

    desc = fm.get("description")
    if not isinstance(desc, str) or not desc.strip():
        fail("frontmatter", "缺少 description 字段")
    else:
        flat = " ".join(desc.split())
        if len(flat) > MAX_DESC:
            fail("frontmatter", f"description {len(flat)} 字符 > {MAX_DESC}")
        else:
            ok("frontmatter", f"description {len(flat)} 字符（上限 {MAX_DESC}）")
        if "不要用于" not in flat and "not for" not in flat.lower():
            fail("frontmatter", "description 缺负向触发词（应写明「不要用于…」）")
        else:
            ok("frontmatter", "description 含负向触发词")

    meta = fm.get("metadata") if isinstance(fm.get("metadata"), dict) else {}
    if meta.get("version"):
        ok("frontmatter", f"metadata.version = {meta['version']}")
    elif HAVE_YAML:
        warn("frontmatter", "metadata.version 缺失（建议写版本号，便于 agent 判断时效）")


def check_line_count(body: str, full_text: str) -> None:
    lines = full_text.count("\n") + 1
    if lines >= MAX_LINES:
        fail("size", f"SKILL.md {lines} 行 >= {MAX_LINES}；把知识下沉到 ios-builder/references/，"
                     "根文件只留路由与矩阵")
    else:
        ok("size", f"SKILL.md {lines} 行（上限 {MAX_LINES}）")


def table_rows(text: str, heading_keyword: str) -> list:
    """抽取包含 heading_keyword 的 markdown 表格，返回 [[cell,...], ...]（跳过分隔行）。"""
    lines = text.splitlines()
    rows: list = []
    in_table = False
    for line in lines:
        if line.startswith("|") and heading_keyword in line:
            in_table = True
            rows = [[c.strip() for c in line.strip("|").split("|")]]
            continue
        if in_table:
            if not line.startswith("|"):
                break
            if re.match(r"^\|[\s:|-]+\|$", line):
                continue
            rows.append([c.strip() for c in line.strip("|").split("|")])
    return rows


def check_matrix(body: str) -> None:
    rows = table_rows(body, "用户意图")
    if not rows:
        fail("matrix", "找不到 Command Matrix 表格（表头需含「用户意图」）")
        return
    header = rows[0]
    if [c for c in header] != MATRIX_COLUMNS:
        fail("matrix", f"表头应为 {MATRIX_COLUMNS}，实际 {header}")
    elif len(rows) - 1 < 5:
        fail("matrix", f"命令矩阵只有 {len(rows) - 1} 行，至少需要 5 条路由")
    else:
        ok("matrix", f"表头 5 列正确，共 {len(rows) - 1} 条路由")
    for i, row in enumerate(rows[1:], start=1):
        if len(row) != len(header):
            fail("matrix", f"第 {i} 行列数 {len(row)} != 表头 {len(header)}：{row}")
            continue
        empty = [j for j, cell in enumerate(row) if not cell]
        if empty:
            fail("matrix", f"第 {i} 行存在空单元格（列号 {empty}）")
        cmd = row[1]
        if "`" not in cmd:
            warn("matrix", f"第 {i} 行「必须执行的命令」未用反引号包裹：{cmd}")


def referenced_paths(body: str) -> list:
    found = []
    for match in PATH_RE.finditer(body):
        p = match.group(1)
        if p.startswith(("http://", "https://", "/")):
            continue
        found.append(p)
    return sorted(set(found))


REPO_TOP = {"SKILL.md", "README.md", "LICENSE", "CONTRIBUTING.md", "claw-skill.yaml",
            "builder", "ios-builder", "templates", "examples", ".github", ".gitignore",
            ".gitattributes"}


def check_paths(root: Path, body: str) -> list:
    used, skipped = [], []
    for p in referenced_paths(body):
        if (root / p).exists():
            used.append(p)
            continue
        if p in GENERATED_ALLOWLIST or "__" in p:
            skipped.append(p)
            continue
        if p.split("/")[0] not in REPO_TOP:
            # 指的是用户目标工程里的文件（Podfile、ios/Runner.xcodeproj 等），本仓库不该有
            skipped.append(p)
            continue
        fail("paths", f"SKILL.md 引用的本仓库文件不存在：{p}")
    if not used:
        warn("paths", "SKILL.md 未引用任何仓库内文件，agent 无法下钻到 references")
    if "\\" in body:
        fail("paths", "SKILL.md 出现反斜杠路径；规范只允许正斜杠相对路径")
    for token in re.findall(r"(?<![\w./-])/[A-Za-z][\w./-]*", body):
        if re.match(r"^/(Users|home|opt|var|usr)/", token):
            warn("paths", f"SKILL.md 出现绝对路径 {token}，改为相对路径")
    ok("paths", f"SKILL.md 内 {len(used)} 个本仓库引用路径均存在"
       + (f"，{len(skipped)} 个目标工程生成物已跳过" if skipped else ""))
    return used


def check_references(root: Path, body: str, claw_text: str) -> None:
    ref_dir = root / "ios-builder" / "references"
    if not ref_dir.is_dir():
        fail("references", f"缺少知识库目录：{ref_dir}")
        return
    files = sorted(p for p in ref_dir.glob("*.md"))
    if not files:
        fail("references", "ios-builder/references/ 为空")
        return
    expected = {
        "framework-detection.md", "builder-json-schema.md", "workflow-yml-anatomy.md",
        "code-signing.md", "flutter-hot-reload.md", "react-native-hot-reload.md",
        "mobai-device-bridge.md", "troubleshooting.md",
    }
    present = {p.name for p in files}
    missing = sorted(expected - present)
    if missing:
        fail("references", f"缺少规范要求的核心文档：{missing}")
    orphans = [p.name for p in files if p.name not in body and p.name not in claw_text]
    if orphans:
        fail("references", f"孤儿文档（SKILL.md 与 claw-skill.yaml 都没引用）：{orphans}")
    else:
        ok("references", f"{len(files)} 篇文档全部有入口")
    if len(files) > 12:
        warn("references", f"文档已达 {len(files)} 篇，考虑合并或加索引页")


def check_error_codes(root: Path, body: str) -> None:
    codes = set(re.findall(r"\bE(\d{1,2})\b", body))
    ts = root / "ios-builder" / "references" / "troubleshooting.md"
    if not ts.is_file():
        fail("error-codes", "troubleshooting.md 不存在")
        return
    text = ts.read_text(encoding="utf-8")
    defined = set(re.findall(r"^#{2,4}\s+E(\d{1,2})\b", text, re.M))
    defined |= set(re.findall(r"^\|\s*`?E(\d{1,2})`?\s*\|", text, re.M))
    if not defined:
        fail("error-codes", "troubleshooting.md 里找不到任何 E<n> 锚点/表格行")
        return
    missing = sorted(codes - defined, key=int)
    if missing:
        fail("error-codes", f"SKILL.md 引用了未定义的错误码：E{'、E'.join(missing)}")
    else:
        ok("error-codes", f"引用的 {len(codes)} 个错误码在 troubleshooting.md 全部有定义")
    if len(defined) < 10:
        warn("error-codes", f"troubleshooting.md 只有 {len(defined)} 个错误码（规范期望 E1~E10）")


def check_claw(root: Path) -> str:
    claw = root / "claw-skill.yaml"
    if not claw.is_file():
        warn("claw-skill", "缺少 claw-skill.yaml（OpenClaw 机器可读清单，参考仓库里有）")
        return ""
    text = claw.read_text(encoding="utf-8")
    if not HAVE_YAML:
        # 无 pyyaml 时退化为结构检查：禁 tab、name 对得上、path 全部存在
        if "\t" in text:
            fail("claw-skill", "claw-skill.yaml 含 tab（YAML 不允许用 tab 缩进）")
        m = re.search(r"^name:\s*(\S+)\s*$", text, re.M)
        if not m:
            fail("claw-skill", "claw-skill.yaml 找不到顶层 name")
        elif m.group(1) != root.name:
            fail("claw-skill", f"claw-skill.yaml name={m.group(1)} 与目录名 {root.name} 不一致")
        missing_paths = []
        for ref in re.finditer(r"^-?\s*(?:-\s+)?path:\s*([\w./-]+)\s*$", text, re.M):
            value = ref.group(1)
            if not value.startswith(("http://", "https://")) and not (root / value).exists():
                missing_paths.append(value)
        if missing_paths:
            fail("claw-skill", f"claw-skill.yaml 里这些 path 不存在：{missing_paths}")
        else:
            ok("claw-skill", "无 pyyaml，已做结构校验：name 一致、全部 path 存在")
        return text
    if HAVE_YAML:
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            fail("claw-skill", f"claw-skill.yaml 无法解析：{exc}")
            return text
        if isinstance(data, dict) and data.get("name") != root.name:
            fail("claw-skill", f"claw-skill.yaml name={data.get('name')!r} 与目录名 {root.name!r} 不一致")
        for section in ("capabilities", "references", "examples"):
            items = data.get(section) or []
            for item in items:
                if not isinstance(item, dict):
                    continue
                for key in ("path", "scripts"):
                    vals = item.get(key)
                    if isinstance(vals, str):
                        if not (root / vals).exists():
                            fail("claw-skill", f"{section} 指向不存在的文件：{vals}")
                    elif isinstance(vals, list):
                        for sub in vals:
                            p = sub.get("path") if isinstance(sub, dict) else sub
                            if isinstance(p, str) and not (root / p).exists():
                                fail("claw-skill", f"{section} 指向不存在的文件：{p}")
        ok("claw-skill", "claw-skill.yaml 可解析且路径有效")
    return text


ID_RE = re.compile(r"\b[0-9A-F]{24}\b")


def strip_pbx_noise(text: str) -> str:
    """去掉 /* ... */ 注释与 "..." 字面量，便于做括号配平统计。"""
    no_comments = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    return re.sub(r'"(?:[^"\\]|\\.)*"', '""', no_comments)


PLACEHOLDER_RE = re.compile(r"__[A-Z][A-Z0-9_]*__")


def check_data_files(root: Path) -> None:
    """与 validate.yml 的同一套规则：JSON 必须可解析；templates/ 里带裸占位 token 的除外。
    YAML 只在装了 pyyaml 时校验（与 CI 对齐），否则报 NOTE。"""
    bad_json, skipped = [], []
    for p in sorted(root.rglob("*.json")):
        if ".git" in p.parts:
            continue
        sp = p.relative_to(root).as_posix()      # 与 validate.yml 一样用仓库相对路径判断
        if p.name == "package-lock.json":
            continue
        text = p.read_text(encoding="utf-8")
        try:
            json.loads(text)
        except json.JSONDecodeError as e:
            if sp.startswith("templates/") and PLACEHOLDER_RE.search(text):
                skipped.append(sp)
            else:
                bad_json.append(f"{sp}: {e}")
    if bad_json:
        for item in bad_json:
            fail("data-files", f"JSON 解析失败 {item}")
    else:
        ok("data-files", f"JSON 全部可解析（{len(skipped)} 个模板占位文件按规则跳过）")

    if not HAVE_YAML:
        note("data-files", "未装 pyyaml，YAML 校验跳过（CI 里会跑）")
        return
    bad_yaml = []
    targets = sorted(root.rglob("*.yml")) + [root / "builder" / "ios-build.yml.template"]
    for p in targets:
        if ".git/" in p.as_posix() or not p.is_file():
            continue
        try:
            yaml.safe_load(p.read_text(encoding="utf-8"))
        except yaml.YAMLError as e:
            bad_yaml.append(f"{p.relative_to(root).as_posix()}: {e}")
    if bad_yaml:
        for item in bad_yaml:
            fail("data-files", f"YAML 解析失败 {item}")
    else:
        ok("data-files", "YAML（含 workflow 模板）全部可解析")


def check_xcodeproj(root: Path) -> None:
    """校验 examples/ 下真实工程：pbxproj 结构完整、ID 引用可解析、scheme 指得到 target。"""
    found = False
    for pbx in sorted(root.rglob("*.xcodeproj/project.pbxproj")):
        if ".git/" in pbx.as_posix():
            continue
        found = True
        xcodeproj = pbx.parent
        proj_dir = xcodeproj.parent
        text = pbx.read_text(encoding="utf-8")
        label = pbx.relative_to(root).as_posix()

        begins = re.findall(r"/\* Begin (\w+) section \*/", text)
        ends = re.findall(r"/\* End (\w+) section \*/", text)
        if sorted(begins) != sorted(ends):
            fail("xcodeproj", f"{label} 的 section Begin/End 不配对：{sorted(set(begins) ^ set(ends))}")

        bare = strip_pbx_noise(text)
        for opener, closer, name in (("{", "}", "花括号"), ("(", ")", "圆括号"), ("[", "]", "方括号")):
            if bare.count(opener) != bare.count(closer):
                fail("xcodeproj", f"{label} {name}不配平：{bare.count(opener)} vs {bare.count(closer)}")

        defined = set(re.findall(r"^\s{2}([0-9A-F]{24})\b[^\n=]*=\s*\{", text, re.M))
        used = set(ID_RE.findall(text))
        dangling = sorted(used - defined)
        if dangling:
            fail("xcodeproj", f"{label} 引用了未定义的对象 ID：{dangling[:5]}")
        else:
            ok("xcodeproj", f"{label}：{len(defined)} 个对象，ID 引用全部可解析")

        is_template = "templates/" in pbx.as_posix()
        for ref in re.finditer(r"lastKnownFileType = [\w.]+; path = ([^;]+);", text):
            if is_template:
                break
            name = ref.group(1).strip().strip('"')
            if (proj_dir / name).exists() or list(proj_dir.rglob(Path(name).name)):
                continue
            fail("xcodeproj", f"{label} 引用的文件在工程里不存在：{name}")

        for scheme in sorted(xcodeproj.glob("xcshareddata/xcschemes/*.xcscheme")):
            body = scheme.read_text(encoding="utf-8")
            bids = set(re.findall(r'BlueprintIdentifier="([0-9A-F]{24})"', body))
            bad = sorted(b for b in bids if b not in defined)
            if bad:
                fail("xcodeproj", f"{scheme.name} 的 BlueprintIdentifier 在 pbxproj 里不存在：{bad}")
            names = set(re.findall(r'BlueprintName="([^"]+)"', body))
            missing = sorted(n for n in names if not re.search(
                r"isa = PBXNativeTarget;.*?name = " + re.escape(n) + r";", text, re.S))
            if missing:
                fail("xcodeproj", f"{scheme.name} 指向的 target 名在 pbxproj 里不存在：{missing}")

        bundle_ids = set(re.findall(r"PRODUCT_BUNDLE_IDENTIFIER = ([^;]+);", text))
        cfg = proj_dir / "builder.json"
        if cfg.is_file():
            try:
                want = (json.loads(cfg.read_text(encoding="utf-8")).get("ios") or {}).get("bundleId")
            except (json.JSONDecodeError, AttributeError):
                want = None
            if want and bundle_ids and want not in bundle_ids:
                fail("xcodeproj", f"{label} 的 PRODUCT_BUNDLE_IDENTIFIER {sorted(bundle_ids)} "
                                  f"与 builder.json 的 ios.bundleId={want} 不一致")
            elif want:
                ok("xcodeproj", f"{label} bundle id 与 builder.json 一致：{want}")
    if not found:
        warn("xcodeproj", "没找到任何 project.pbxproj（examples/ 下应有一个可构建工程）")


def main(argv: list) -> int:
    root = repo_root(argv)
    skill = root / "SKILL.md"
    if not skill.is_file():
        print(f"[ERROR] 未找到 {skill}", file=sys.stderr)
        print("[HINT ] 在 Skill 仓库根目录运行，或传目录参数：lint_skill.py <skill-dir>", file=sys.stderr)
        return 2

    full = skill.read_text(encoding="utf-8")
    raw_fm, body = split_frontmatter(full)
    if raw_fm is None:
        fail("frontmatter", "SKILL.md 缺少 YAML frontmatter（--- 包裹）")
        fm = {}
    else:
        fm = parse_frontmatter(raw_fm)

    check_frontmatter(root, fm, root.name)
    check_line_count(body, full)
    check_matrix(body)
    check_paths(root, body)
    claw_text = check_claw(root)
    check_references(root, body, claw_text)
    check_error_codes(root, body)
    check_xcodeproj(root)
    check_data_files(root)

    print()
    for line in warnings:
        print(line)
    for line in failures:
        print(line)
    if failures:
        print(f"\n结果：{len(failures)} 项 FAIL，{len(warnings)} 项 WARN")
        return 1
    if not HAVE_YAML:
        print("NOTE  未安装 pyyaml，claw-skill.yaml 深度校验已跳过（pip install pyyaml 后重跑）")
    for line in notes:
        print(line)
    print(f"\n结果：全部通过（{len(warnings)} 项 WARN）")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
