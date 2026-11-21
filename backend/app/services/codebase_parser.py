import ast
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import re
import subprocess

from app.services.github_service import MAX_FILE, SHA

LANGUAGES = {
    ".py": "Python", ".js": "JavaScript", ".mjs": "JavaScript", ".cjs": "JavaScript",
    ".jsx": "JavaScript", ".ts": "TypeScript", ".tsx": "TypeScript",
    ".sql": "SQL", ".json": "JSON", ".toml": "TOML", ".yaml": "YAML",
    ".yml": "YAML", ".md": "Markdown", ".txt": "Text", ".html": "HTML", ".css": "CSS",
}
MANIFESTS = {"requirements.txt", "pyproject.toml", "package.json", "package-lock.json",
             "tsconfig.json", "dockerfile", "docker-compose.yml", "docker-compose.yaml",
             "compose.yaml", "compose.yml", ".env.example"}
IGNORED = {".git", "node_modules", "dist", "build", "coverage", "__pycache__", ".venv", "venv",
           ".tox", ".next", ".pytest_cache", "vendor", ".aws", ".ssh", ".gnupg", "secrets",
           ".secrets", ".idea", "site-packages", ".npm", ".vscode"}
SECRET_NAMES = re.compile(r"(^|[._-])(secret|secrets|credentials|credential|token|tokens|private[._-]?key)([._-]|$)", re.I)
SECRET_SUFFIXES = {".key", ".pem", ".pfx", ".p12", ".kdbx", ".keystore", ".crt", ".ssh"}
ENTRY_NAMES = {"main.py", "app.py", "index.js", "index.ts", "main.tsx", "main.jsx",
               "server.js", "server.ts", "wsgi.py", "asgi.py", "__main__.py"}
SOURCE_LANGS = {"Python", "JavaScript", "TypeScript"}
JS_INDEX = Path(__file__).resolve().parents[2] / "tools" / "index_js.cjs"
SECRET_LINE = re.compile(
    r'''sk-[A-Za-z0-9_-]{18,}|github_pat_[A-Za-z0-9_]{18,}|gh[pousr]_[A-Za-z0-9]{20,}|AKIA[A-Z0-9]{16}|'''
    r'''(?:password|passwd|api[_-]?key|client[_-]?secret|access[_-]?token)\s*['"]?\s*[:=]\s*['"][^'"\s]{8,}''',
    re.I,
)
PRIVATE_KEY_START = re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----", re.I)
PRIVATE_KEY_END = re.compile(r"-----END [A-Z0-9 ]*PRIVATE KEY-----", re.I)


def select_entries(entries):
    records = []
    for item in entries:
        if item.get("type") != "blob" or item.get("mode") not in {"100644", "100755"}:
            continue
        path = item.get("path", "")
        if len(path) > 600 or path.startswith("/") or any(char in path for char in "\\\x00\r\n"):
            continue
        pieces = path.lower().split("/")
        if any(part in IGNORED or part in {"", ".", ".."} for part in pieces):
            continue
        filename = pieces[-1]
        suffix = PurePosixPath(path).suffix.lower()
        if any((part.startswith(".env") and part != ".env.example") or SECRET_NAMES.search(part) for part in pieces):
            continue
        if suffix in SECRET_SUFFIXES or filename in {".npmrc", ".netrc", ".pypirc", "id_rsa", "id_ed25519"}:
            continue
        if filename.startswith("readme"):
            kind, priority = "documentation", 0
        elif filename in MANIFESTS:
            kind, priority = "configuration", 1 if filename != "package-lock.json" else 8
        elif suffix == ".sql":
            kind, priority = "database", 3
        elif LANGUAGES.get(suffix) in SOURCE_LANGS:
            kind, priority = ("test", 7) if ("tests" in pieces or filename.startswith("test_") or ".test." in filename) else ("source", 2 if filename in ENTRY_NAMES else 4)
        elif suffix in LANGUAGES:
            kind, priority = "supporting", 9
        else:
            continue
        if not isinstance(item.get("size"), int) or item["size"] < 0 or not SHA.fullmatch(item.get("sha", "")):
            continue
        records.append({"path": path, "size": item["size"], "blob_sha": item["sha"],
                        "metadata_json": {"kind": kind, "priority": priority, "language": LANGUAGES.get(suffix, "Text"),
                                          "core": priority <= 4, "readable": item["size"] <= MAX_FILE}})
    return sorted(records, key=lambda row: (row["metadata_json"]["priority"], row["path"].count("/"), row["path"]))


def mask_source(text):
    lines, private_key = [], False
    for line in text.split("\n"):
        private_key = private_key or bool(PRIVATE_KEY_START.search(line))
        lines.append("[已遮盖可能的凭据]" if private_key or SECRET_LINE.search(line) else line)
        if PRIVATE_KEY_END.search(line):
            private_key = False
    return "\n".join(lines)


def python_index(text):
    tree = ast.parse(text)
    symbols, imports, routes, calls = [], [], [], []
    active = []

    class Visitor(ast.NodeVisitor):
        def definition(self, node, kind):
            name = ".".join([*active, node.name])
            symbols.append({"name": name, "kind": kind, "start": node.lineno, "end": node.end_lineno})
            if kind == "function":
                for decorator in node.decorator_list:
                    if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute):
                        method = decorator.func.attr.upper()
                        if (method in {"GET", "POST", "PUT", "PATCH", "DELETE"} and decorator.args
                                and isinstance(decorator.args[0], ast.Constant) and isinstance(decorator.args[0].value, str)):
                            routes.append({"method": method, "path": decorator.args[0].value[:200], "name": name, "line": decorator.lineno})
            active.append(node.name)
            self.generic_visit(node)
            active.pop()

        def visit_ClassDef(self, node):
            self.definition(node, "class")

        def visit_FunctionDef(self, node):
            self.definition(node, "function")

        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_Import(self, node):
            imports.extend({"name": item.name, "line": node.lineno} for item in node.names)

        def visit_ImportFrom(self, node):
            prefix = "." * node.level + (node.module or "")
            if prefix:
                imports.append({"name": prefix, "line": node.lineno})
            imports.extend({"name": prefix + ("" if prefix.endswith(".") else ".") + item.name, "line": node.lineno}
                           for item in node.names if prefix)

        def visit_Call(self, node):
            target = node.func
            if active and isinstance(target, ast.Name):
                calls.append({"caller": ".".join(active), "name": target.id, "line": node.lineno})
            self.generic_visit(node)

    Visitor().visit(tree)
    return {"symbols": symbols[:180], "imports": imports[:180], "routes": routes[:100], "calls": calls[:220]}


def parse_file(path, language, text):
    empty = {"symbols": [], "imports": [], "routes": [], "calls": []}
    parsed = empty
    status = "text"
    # Static parsers receive source via stdin and do not load the imported project's configuration.
    try:
        if language == "Python":
            parsed, status = python_index(text), "parsed"
        elif language in {"JavaScript", "TypeScript"}:
            result = subprocess.run(["node", str(JS_INDEX), PurePosixPath(path).name],
                                    input=text, encoding="utf-8", capture_output=True, timeout=5, check=True)
            parsed, status = json.loads(result.stdout), "parsed"
    except (SyntaxError, ValueError, RecursionError, OSError, subprocess.SubprocessError):
        status = "syntax_or_parser_unavailable"
    cleaned = mask_source(text)
    return cleaned, {**parsed, "status": status, "content_hash": sha256(cleaned.encode()).hexdigest()}
