from pathlib import PurePosixPath
import posixpath
import re

from sqlalchemy import select

from app.core.errors import ApiError
from app.models.code_project import ProjectFile

EVIDENCE_LIMIT = 10
CONTEXT_LIMIT = 12500
TOKEN = re.compile(r"[a-zA-Z_][a-zA-Z_0-9.-]*|[\u4e00-\u9fff]{2,}")
DEPENDENCIES = {
    "react": "前端框架", "vue": "前端框架", "svelte": "前端框架", "vite": "前端构建",
    "fastapi": "后端框架", "flask": "后端框架", "django": "后端框架", "express": "后端框架",
    "sqlalchemy": "ORM", "prisma": "ORM", "pymysql": "数据库驱动", "mysql2": "数据库驱动",
    "psycopg": "数据库驱动", "openai": "AI SDK", "anthropic": "AI SDK", "langchain": "AI SDK",
    "pytest": "测试", "vitest": "测试", "jest": "测试", "typescript": "语言工具", "zod": "参数校验",
    "redis": "外部服务", "alembic": "数据库迁移", "celery": "后台任务",
}
CONFIG_EVIDENCE = {
    "dockerfile": ("Docker", "部署"), "docker-compose.yml": ("Docker Compose", "部署"),
    "docker-compose.yaml": ("Docker Compose", "部署"), "compose.yml": ("Docker Compose", "部署"),
    "compose.yaml": ("Docker Compose", "部署"), "tsconfig.json": ("TypeScript", "语言配置"),
}


def files_for(db, snapshot_id, loaded=False):
    stmt = select(ProjectFile).where(ProjectFile.snapshot_id == snapshot_id).order_by(ProjectFile.id)
    if loaded:
        stmt = stmt.where(ProjectFile.content.is_not(None))
    return list(db.scalars(stmt))


def tokens(query):
    words = set()
    for word in TOKEN.findall(query.lower()[:350]):
        if re.search(r"[\u4e00-\u9fff]", word):
            words.update(word[i:i + 2] for i in range(len(word) - 1))
        else:
            words.add(word)
    return sorted(words)[:35]


def citations(files, query="", file_id=None, symbol=None, limit=EVIDENCE_LIMIT):
    if file_id is not None and not any(file.id == file_id for file in files):
        raise ApiError(422, "CODE_FILE_NOT_LOADED", "请先读取目标文件")
    words = tokens(query)
    candidates = []
    for file in files:
        if file_id is not None and file_id != file.id:
            continue
        lines = file.content.split("\n")
        symbols = file.index_data.get("symbols", [])
        if symbol:
            symbols = [item for item in symbols if item["name"] == symbol]
            if not symbols:
                continue
        spans = [(item["start"], item["end"], item["name"]) for item in symbols]
        if not symbol:
            spans.extend((offset, min(offset + 34, len(lines)), None) for offset in range(1, len(lines) + 1, 35))
        for start, end, name in spans:
            # Long symbols contribute multiple windows when the query matches a later line.
            for first in range(start, end + 1, 35):
                last = min(first + 34, end)
                code = "\n".join(lines[first - 1:last])
                if len(code) > 2200:
                    code_lines = []
                    chars = 0
                    for line in lines[first - 1:last]:
                        if chars + len(line) + 1 > 2200:
                            break
                        chars += len(line) + 1
                        code_lines.append(line)
                    if not code_lines:
                        continue
                    last = first + len(code_lines) - 1
                    code = "\n".join(code_lines)
                if not code.strip():
                    continue
                name_path = f"{file.path} {name or ''}".lower()
                score = sum(12 * (word in name_path) + 2 * (word in code.lower()) for word in words)
                if words and not score and file_id is None:
                    continue
                score += (4 if name else 0) + max(0, 5 - file.metadata_json["priority"])
                candidates.append((score, file.id, first, last, file.path, name, code))
    if symbol and not candidates:
        raise ApiError(422, "CODE_SYMBOL_UNAVAILABLE", "当前索引中没有可用的该符号片段")
    output, seen, used = [], set(), 0
    for _, file_id, first, last, path, name, code in sorted(candidates, key=lambda row: (-row[0], row[1], row[2])):
        key = (file_id, first, last)
        if key in seen or used + len(code) > CONTEXT_LIMIT:
            continue
        seen.add(key)
        used += len(code)
        output.append({"id": len(output) + 1, "file_id": file_id, "path": path, "start": first,
                       "end": last, "symbol": name, "code": code})
        if len(output) == limit:
            break
    return output


def dependency_signals(file):
    name = PurePosixPath(file.path).name.lower()
    lines = file.content.split("\n")
    if name in CONFIG_EVIDENCE:
        technology, group = CONFIG_EVIDENCE[name]
        yield {"name": technology, "category": group, "path": file.path, "line": 1, "status": "declared"}
    names = set()
    if name == "package.json":
        import json
        try:
            data = json.loads(file.content)
        except ValueError:
            return
        if not isinstance(data, dict):
            return
        for key in ("dependencies", "devDependencies", "peerDependencies"):
            section = data.get(key, {})
            if isinstance(section, dict):
                names.update(section)
    elif name == "pyproject.toml":
        import tomllib
        try:
            data = tomllib.loads(file.content)
        except ValueError:
            return
        project = data.get("project", {})
        declared = project.get("dependencies", []) if isinstance(project, dict) else []
        names.update(re.split(r"[<>=~!;\[ ]", word.lower(), maxsplit=1)[0] for word in declared if isinstance(word, str))
        poetry = data.get("tool", {}).get("poetry", {}).get("dependencies", {})
        if isinstance(poetry, dict):
            names.update(poetry)
        if data.get("tool", {}).get("pytest"):
            names.add("pytest")
    elif name == "requirements.txt":
        names.update(re.split(r"[<>=~!;\[ #]", row.strip().lower(), maxsplit=1)[0] for row in lines)
    for word in sorted(names & DEPENDENCIES.keys()):
        mark = re.compile(rf"(?<![\w-]){re.escape(word)}(?![\w-])", re.I)
        line = next((i for i, row in enumerate(lines, 1) if mark.search(row)), 1)
        yield {"name": word, "category": DEPENDENCIES[word], "path": file.path, "line": line, "status": "declared"}


def targets(path, name, known):
    if path.endswith(".py"):
        level = len(name) - len(name.lstrip("."))
        parts = path.split("/")[:-1]
        if level > len(parts) + 1:
            return []
        base = "/".join(parts[:len(parts) + 1 - level] + [name[level:].replace(".", "/")]) if level else name.replace(".", "/")
        suffixes = [f"{base}.py", f"{base.rstrip('/')}/__init__.py"]
        return [target for target in known if any(target == suffix or
                (not level and target.endswith("/" + suffix)) for suffix in suffixes)]
    if name.startswith(("./", "../")):
        base = posixpath.normpath(posixpath.join(posixpath.dirname(path), name))
        variants = [base, base.removesuffix(".js"), base.removesuffix(".mjs")]
        return [target for target in known if target in variants or any(
            target in {f"{value}.{ext}", f"{value}/index.{ext}"} for value in variants
            for ext in ("js", "mjs", "jsx", "ts", "tsx", "cjs"))]
    return []


def architecture(files, paths):
    signals, modules, links, routes, entries, models, calls = [], [], [], [], [], [], []
    seen_languages = set()
    for file in files:
        signals.extend(dependency_signals(file))
        symbols = file.index_data["symbols"]
        lines = file.content.splitlines()
        parent = file.path.split("/")[0] if "/" in file.path else "根目录"
        modules.append({"path": file.path, "module": parent, "kind": file.metadata_json["kind"],
                        "symbols": len(symbols)})
        lang = file.metadata_json["language"]
        if lang in {"Python", "JavaScript", "TypeScript", "SQL"} and lang not in seen_languages:
            signals.append({"name": lang, "category": "语言", "path": file.path, "line": 1, "status": "observed"})
            seen_languages.add(lang)
        routes.extend({**item, "file": file.path} for item in file.index_data["routes"])
        known_symbols = {item["name"] for item in symbols}
        calls.extend({**call, "file": file.path, "status": "inferred", "target": call["name"]}
                     for call in file.index_data["calls"] if call["name"] in known_symbols)
        for imported in file.index_data["imports"]:
            matches = targets(file.path, imported["name"], paths)
            if len(matches) == 1 and matches[0] != file.path:
                links.append({"from": file.path, "to": matches[0], "line": imported["line"], "status": "static_import"})
        if file.metadata_json["priority"] == 2:
            entries.append({"path": file.path, "line": 1, "status": "inferred", "reason": "常见入口文件名"})
        for row in symbols:
            if row["kind"] != "class":
                continue
            heading = lines[row["start"] - 1] if row["start"] <= len(lines) else ""
            if re.search(r"\b(Base|BaseModel|Model|DeclarativeBase)\b", heading):
                models.append({"path": file.path, "name": row["name"], "line": row["start"], "status": "inferred"})
    unique_signals = {item["name"].lower():item for item in signals}
    return {"tech_stack": list(unique_signals.values()), "modules": modules, "entries": entries,
            "imports": links[:200], "calls": calls[:120], "routes": routes[:100], "models": models[:100],
            "files_read": len(files), "files_indexed": len(paths)}
