

"""parsers — language parsers (tree-sitter JS/TS/bash) + extract-API
(symbols/imports/calls/inheritance/errors).

Mechanically extracted from build.py (verbatim) — the god-file gate
(FILE-SIZE.md). build.py re-exports extract_* (the contract of the tests)."""
import ast
import glob
import os
import sys

_JS_EXTS = {".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx"}
_TS_LANGS = {".js": "javascript", ".mjs": "javascript",
             ".cjs": "javascript", ".jsx": "javascript",
             ".ts": "typescript", ".tsx": "tsx",
             ".sh": "bash"}
_SH_EXTS = {".sh"}

def _ts_parser(content, ext):
    """tree-sitter parser for JS/TS. Lazy import: if the library is missing —
    None (old behavior: the file has no symbols). tree_sitter_language_pack
    lives in the project venv (~/.venvs/memory, ships with code-review-graph);
    build.py also runs under a system python3 — so we inject the venv
    site-packages on the first import."""
    try:
        from tree_sitter_language_pack import get_parser
    except ImportError:
        sp = _venv_site_packages()
        if sp and sp not in sys.path:
            sys.path.insert(0, sp)
        try:
            from tree_sitter_language_pack import get_parser
        except ImportError:
            return None
    try:
        return get_parser(_TS_LANGS[ext]).parse(bytes(content, "utf-8"))
    except Exception:
        return None


def _venv_site_packages():
    """The project venv site-packages (~/.venvs/memory), or None."""
    if os.name == "nt":
        p = os.path.join(os.path.expanduser("~"), ".venvs", "memory",
                         "Lib", "site-packages")
        return p if os.path.isdir(p) else None
    hits = glob.glob(os.path.join(os.path.expanduser("~"), ".venvs",
                                  "memory", "lib*", "python*",
                                  "site-packages"))
    return hits[0] if hits else None


def _ts_text(node):
    return node.text.decode("utf-8", errors="replace") if node else ""


def _ts_symbols(rel_path, content):
    """JS/TS symbols: function_declaration, class_declaration (with base),
    method_definition, const f = () => {} / function () {}."""
    ext = os.path.splitext(rel_path)[1].lower()
    tree = _ts_parser(content, ext)
    if tree is None:
        return []
    syms = []
    name_types = ("identifier", "type_identifier")

    def params(node):
        for c in node.children:
            if c.type == "formal_parameters":
                return _ts_text(c)
        return "()"

    def ids(node):
        """All identifiers under the node (recursively): a class name in TS is
        type_identifier, the base may be wrapped in an extends_clause."""
        out = []
        for c in node.children:
            if c.type in name_types:
                out.append(c)
            out.extend(ids(c))
        return out

    def walk(node, in_class=False):
        t = node.type
        if t in ("function_declaration", "generator_function_declaration"):
            name = next((c for c in node.children
                         if c.type == "identifier"), None)
            if name:
                nm = _ts_text(name)
                sig = f"function {nm}{params(node)}"
                syms.append((nm, "method" if in_class else "function",
                             node.start_point[0] + 1, sig))
            for c in node.children:
                walk(c, False)
        elif t == "class_declaration":
            found = ids(node)
            name = found[0] if found else None
            if name:
                nm = _ts_text(name)
                base = ""
                h = next((c for c in node.children
                          if c.type == "class_heritage"), None)
                if h:
                    b = ids(h)
                    if b:
                        base = f"({_ts_text(b[-1])})"
                syms.append((nm, "class", node.start_point[0] + 1,
                             f"class {nm}{base}"))
            for c in node.children:
                walk(c, True)
        elif t == "method_definition":
            name = next((c for c in node.children
                         if c.type == "property_identifier"), None)
            if name:
                nm = _ts_text(name)
                syms.append((nm, "method", node.start_point[0] + 1,
                             f"method {nm}{params(node)}"))
        elif t == "variable_declarator":
            name = next((c for c in node.children
                         if c.type == "identifier"), None)
            fn = next((c for c in node.children
                       if c.type in ("arrow_function", "function_expression",
                                     "generator_function")), None)
            if name and fn:
                nm = _ts_text(name)
                syms.append((nm, "function", node.start_point[0] + 1,
                             f"function {nm}{params(fn)}"))
            for c in node.children:
                walk(c, in_class)
        else:
            for c in node.children:
                walk(c, in_class)

    walk(tree.root_node)
    return sorted(syms, key=lambda s: s[2])


def _ts_imports(rel_path, content):
    """JS/TS import edges: (module, line). The module is the file name
    from the import string (./mod.js -> mod.js), like .py takes the root package."""
    ext = os.path.splitext(rel_path)[1].lower()
    tree = _ts_parser(content, ext)
    if tree is None:
        return []
    edges = []

    def walk(node):
        if node.type == "import_statement":
            for c in node.children:
                if c.type == "string":
                    mod = _ts_text(c).strip("'\"")
                    edges.append((mod.split("/")[-1],
                                  node.start_point[0] + 1))
                    break
        for c in node.children:
            walk(c)

    walk(tree.root_node)
    return edges


def _ts_calls(rel_path, content):
    """JS/TS call edges: (callee_name, line). The name is the last attribute
    of the chain (chrome.tabs.query -> query), like in .py."""
    ext = os.path.splitext(rel_path)[1].lower()
    tree = _ts_parser(content, ext)
    if tree is None:
        return []
    edges = []

    def walk(node):
        if node.type == "call_expression" and node.children:
            fn = node.children[0]
            if fn.type == "identifier":
                edges.append((_ts_text(fn), node.start_point[0] + 1))
            elif fn.type == "member_expression":
                prop = next((c for c in fn.children
                             if c.type == "property_identifier"), None)
                if prop:
                    edges.append((_ts_text(prop), node.start_point[0] + 1))
        for c in node.children:
            walk(c)

    walk(tree.root_node)
    return edges


def _ts_inherits(rel_path, content):
    """Inheritance for JS/TS: (class, base, line) from class_heritage."""
    ext = os.path.splitext(rel_path)[1].lower()
    tree = _ts_parser(content, ext)
    if tree is None:
        return []
    edges = []

    def ids(node):
        out = []
        for c in node.children:
            if c.type in ("identifier", "type_identifier"):
                out.append(c)
            out.extend(ids(c))
        return out

    def walk(node):
        if node.type == "class_declaration":
            found = ids(node)
            h = next((c for c in node.children
                      if c.type == "class_heritage"), None)
            if found and h:
                base = ids(h)
                if base:
                    edges.append((_ts_text(found[0]), _ts_text(base[-1]),
                                  node.start_point[0] + 1))
        for c in node.children:
            walk(c)

    walk(tree.root_node)
    return edges


def _ts_errors(rel_path, content):
    """Syntax errors for JS/TS: (line, message) — the first ERROR node or
    a missing node (an unclosed bracket, etc.)."""
    ext = os.path.splitext(rel_path)[1].lower()
    tree = _ts_parser(content, ext)
    if tree is None:
        return []
    if not tree.root_node.has_error:
        return []
    stack = [tree.root_node]
    while stack:
        n = stack.pop()
        if n.type == "ERROR" or n.is_missing:
            return [(n.start_point[0] + 1, "syntax error (tree-sitter)")]
        stack.extend(n.children)
    return []


def _walk_ts(node):
    """Walk the tree-sitter tree fully (all nodes, including nested)."""
    yield node
    for c in node.children:
        yield from _walk_ts(c)


def _ts_bash_symbols(content):
    """bash symbols: function_definition via tree-sitter-bash (name, line).
    Catches all forms: `name() {}`, `function name {}`, `function name() {}`,
    multi-line bodies — what the regex 'name() {' missed (the function
    keyword, a space before the parens, '{' on the next line)."""
    tree = _ts_parser(content, ".sh")
    if tree is None:
        return []
    syms = []
    for node in _walk_ts(tree.root_node):
        if node.type == "function_definition":
            name = next((c for c in node.children if c.type == "word"), None)
            if name:
                syms.append((_ts_text(name), "function",
                             node.start_point[0] + 1, ""))
    return sorted(syms, key=lambda s: s[2])


def _ts_bash_calls(content):
    """bash calls: command nodes — command name and line (for the --calls graph)."""
    tree = _ts_parser(content, ".sh")
    if tree is None:
        return []
    edges = []
    for node in _walk_ts(tree.root_node):
        if node.type == "command":
            cn = node.child_by_field_name("name")
            if cn is not None and cn.type == "command_name":
                w = next((c for c in cn.children if c.type == "word"), None)
                if w:
                    edges.append((_ts_text(w), node.start_point[0] + 1))
    return edges


def _ts_bash_errors(rel_path, content):
    """bash syntax errors: tree-sitter has_error (like _ts_errors for JS)."""
    tree = _ts_parser(content, ".sh")
    if tree is None:
        return []
    if tree.root_node.has_error:
        return [(tree.root_node.start_point[0] + 1,
                 "syntax error (tree-sitter)")]
    return []


_PY_AST_CACHE = None


def _parse_py(rel_path, content):
    """Parse Python source with a 1-entry cache across extract_* passes."""
    global _PY_AST_CACHE
    import hashlib
    n = len(content)
    digest = hashlib.sha256(content.encode("utf-8", errors="replace")).hexdigest()
    cached = _PY_AST_CACHE
    if cached is not None and cached[0] == rel_path and cached[1] == n and cached[2] == digest:
        res = cached[3]
    else:
        try:
            res = ast.parse(content)
        except SyntaxError as exc:
            res = exc
        _PY_AST_CACHE = (rel_path, n, digest, res)
    if isinstance(res, SyntaxError):
        raise res
    return res


def extract_symbols(rel_path, content):
    """File symbols: (name, type, line, signature). For .py —
    functions/classes/methods via ast (functions get a signature); for .md —
    headings (# / ## / ###) as sections; for .sh — functions via
    tree-sitter-bash (fallback: regex 'name() {'); for .js/.ts —
    tree-sitter (functions, classes, methods, arrow functions in variables)."""
    ext = os.path.splitext(rel_path)[1].lower()
    syms = []
    if ext in _JS_EXTS:
        return _ts_symbols(rel_path, content)
    if ext == ".py":
        try:
            tree = _parse_py(rel_path, content)
        except SyntaxError:
            return syms

        def sig(node):
            try:
                args = node.args
                parts = [a.arg for a in args.posonlyargs + args.args]
                if args.vararg:
                    parts.append("*" + args.vararg.arg)
                for a in args.kwonlyargs:
                    parts.append(a.arg)
                if args.kwarg:
                    parts.append("**" + args.kwarg.arg)
                return f"def {node.name}({', '.join(parts)})"
            except (AttributeError, TypeError, ValueError):
                return f"def {node.name}(...)"

        def walk(node, in_class=False):
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    kind = "method" if in_class else "function"
                    syms.append((child.name, kind, child.lineno,
                                 sig(child)))
                    walk(child, in_class=False)
                elif isinstance(child, ast.ClassDef):
                    bases = [b.id for b in child.bases if isinstance(b, ast.Name)]
                    syms.append((child.name, "class", child.lineno,
                                 f"class {child.name}({', '.join(bases)})"
                                 if bases else f"class {child.name}"))
                    walk(child, in_class=True)
                else:
                    walk(child, in_class)

        walk(tree)
        return sorted(syms, key=lambda s: s[2])
    if ext == ".md":
        import re
        for i, line in enumerate(content.split("\n"), 1):
            m = re.match(r"^(#{1,3})\s+(.*)$", line)
            if m:
                depth = len(m.group(1))
                syms.append((m.group(2).strip(), f"h{depth}", i, ""))
        return syms
    if ext == ".sh":
        syms = _ts_bash_symbols(content)
        if syms:
            return syms
        # fallback without tree-sitter (system python3 without the venv package)
        import re
        for i, line in enumerate(content.split("\n"), 1):
            m = re.match(r"^\s*([a-zA-Z_][a-zA-Z0-9_]*)\(\)\s*(\{)?\s*(#.*)?$",
                         line)
            if m:
                syms.append((m.group(1), "function", i, ""))
        return syms
    return syms


def extract_imports(rel_path, content):
    """Import edges: .py — ast; .js/.ts — tree-sitter."""
    ext = os.path.splitext(rel_path)[1].lower()
    if ext in _JS_EXTS:
        return _ts_imports(rel_path, content)
    if ext != ".py":
        return []
    try:
        tree = _parse_py(rel_path, content)
    except SyntaxError:
        return []
    edges = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                edges.append((a.name.split(".")[0], node.lineno))
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            edges.append((mod.split(".")[0], node.lineno))
    return edges


def extract_calls(rel_path, content):
    """Call edges: .py — ast; .js/.ts — tree-sitter; .sh — tree-sitter-bash.
    The name is the last attribute of the chain (os.path.join -> join, tg_send_text)."""
    ext = os.path.splitext(rel_path)[1].lower()
    if ext in _JS_EXTS:
        return _ts_calls(rel_path, content)
    if ext in _SH_EXTS:
        return _ts_bash_calls(content)
    if ext != ".py":
        return []
    try:
        tree = _parse_py(rel_path, content)
    except SyntaxError:
        return []
    edges = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Name):
                edges.append((f.id, node.lineno))
            elif isinstance(f, ast.Attribute):
                edges.append((f.attr, node.lineno))
    return edges


def extract_inherits(rel_path, content):
    """Inheritance: .py — ast; .js/.ts — tree-sitter (class X extends Y).
    Simple names (class X(Base)) and the last attribute of the chain
    (unittest.TestCase -> TestCase, like in extract_calls): the full name is
    ambiguous, but the "who inherits from TestCase" graph works."""
    ext = os.path.splitext(rel_path)[1].lower()
    if ext in _JS_EXTS:
        return _ts_inherits(rel_path, content)
    if ext != ".py":
        return []
    try:
        tree = _parse_py(rel_path, content)
    except SyntaxError:
        return []
    edges = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for b in node.bases:
                if isinstance(b, ast.Name):
                    edges.append((node.name, b.id, node.lineno))
                elif isinstance(b, ast.Attribute):
                    edges.append((node.name, b.attr, node.lineno))
    return edges


def extract_errors(rel_path, content):
    """Syntax errors: .py — ast; .js/.ts — tree-sitter; .sh —
    tree-sitter-bash. A file that fails to parse is diagnostics for the search
    rather than a silent skip (previously SyntaxError just yielded an empty
    list)."""
    ext = os.path.splitext(rel_path)[1].lower()
    if ext in _JS_EXTS:
        return _ts_errors(rel_path, content)
    if ext in _SH_EXTS:
        return _ts_bash_errors(rel_path, content)
    if ext != ".py":
        return []
    try:
        _parse_py(rel_path, content)
    except SyntaxError as e:
        return [(e.lineno or 0, e.msg)]
    return []
