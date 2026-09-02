"""Shared AST oracle helpers for the three coding-kit task verifiers.

The candidate test file (test_calc.py) is model-written and therefore
semi-trusted.  The regression/mutation checks only prove the tests *behave*
differently across implementation variants; a hostile candidate can satisfy
them by inspecting ``calc.py`` source, bytecode, or filesystem state and
branching on that instead of asserting observable behavior.

These helpers close that hole with a stdlib-only ``ast`` pass that runs before
any behavior check:

* reject implementation introspection (imports of ``inspect``/``ast``/
  ``dis``/``marshal`` and their aliases, ``inspect.getsource``/``getfile``/
  ``signature``, ``open``/``io.open``/``pathlib.Path.open``, chained
  ``read``/``readline``/``readlines``, ``read_text``/``read_bytes``,
  ``__file__``, ``__code__``, and ``co_*`` bytecode attributes), and
* require concrete behavioral assertions, credited only from top-level
  pytest-collectable ``test_*`` functions (never from nested/helper defs).

Nothing here inspects raw source text: acceptance is structural AST walking
plus the downstream mutation runs.
"""

from __future__ import annotations

import ast
from pathlib import Path

# Implementation-introspection modules a legitimate calc regression test has
# no reason to import.
_FORBIDDEN_MODULES = frozenset({"inspect", "ast", "dis", "marshal"})

# Filesystem/source-file reads a calc regression test has no reason to use:
# pathlib.Path.open()/io.open(), the builtin open(), and any chained stream
# read (read/readline/readlines) or Path read_text/read_bytes.
_FORBIDDEN_ATTRS = frozenset(
    {"read_text", "read_bytes", "read", "readline", "readlines", "open"}
)

# Interpreter internals that expose source/bytecode rather than behavior.
_METADATA_ATTRS = frozenset({"__file__", "__code__"})

# inspect.* callables the spec names explicitly (import-agnostic guard).
_INTROSPECT_CALLS = frozenset(
    {"getsource", "getsourcelines", "getfile", "signature"}
)


def _root_module(module_name: str | None) -> str:
    return (module_name or "").split(".")[0]


def introspection_violations(tree: ast.Module) -> list[str]:
    """Return human-readable violations for implementation introspection."""
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _root_module(alias.name) in _FORBIDDEN_MODULES:
                    out.append(f"imports forbidden introspection module {alias.name!r}")
        elif isinstance(node, ast.ImportFrom):
            if _root_module(node.module) in _FORBIDDEN_MODULES:
                out.append(f"imports from forbidden introspection module {node.module!r}")
        elif isinstance(node, ast.Attribute):
            if node.attr in _FORBIDDEN_ATTRS:
                out.append(f"uses forbidden file access .{node.attr}")
            if node.attr in _METADATA_ATTRS:
                out.append(f"uses forbidden metadata attribute .{node.attr}")
            if node.attr.startswith("co_"):
                out.append(f"uses forbidden bytecode attribute .{node.attr}")
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "open":
                out.append("uses forbidden builtin open()")
            elif (
                isinstance(func, ast.Name)
                and func.id == "__import__"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
                and _root_module(node.args[0].value) in _FORBIDDEN_MODULES
            ):
                out.append(f"forbidden dynamic import of {node.args[0].value!r}")
            elif isinstance(func, ast.Attribute) and func.attr in _INTROSPECT_CALLS:
                out.append(f"uses forbidden introspection call .{func.attr}")
            elif (
                isinstance(func, ast.Name)
                and func.id == "getattr"
                and len(node.args) >= 2
                and isinstance(node.args[1], ast.Constant)
                and isinstance(node.args[1].value, str)
            ):
                attr_name = node.args[1].value
                if (
                    attr_name in _FORBIDDEN_ATTRS
                    or attr_name in _METADATA_ATTRS
                    or attr_name.startswith("co_")
                ):
                    out.append(f"uses forbidden dynamic attribute .{attr_name}")
    return out


def _is_call_to(call: ast.Call, name: str) -> bool:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id == name
    return isinstance(func, ast.Attribute) and func.attr == name


def _is_raises_context(item: ast.withitem) -> bool:
    """True for ``with pytest.raises(ValueError)`` / ``with raises(ValueError)``."""
    ctx = item.context_expr
    if not isinstance(ctx, ast.Call):
        return False
    func = ctx.func
    if isinstance(func, ast.Name):
        if func.id != "raises":
            return False
    elif isinstance(func, ast.Attribute):
        if func.attr != "raises":
            return False
    else:
        return False
    if not ctx.args:
        return False
    first = ctx.args[0]
    return isinstance(first, ast.Name) and first.id == "ValueError"


def _is_raises_block(stmt: ast.stmt) -> bool:
    return isinstance(stmt, ast.With) and any(
        isinstance(item, ast.withitem) and _is_raises_context(item)
        for item in stmt.items
    )


def _contains_zero_arg(call: ast.Call) -> bool:
    for node in list(call.args) + [k.value for k in call.keywords]:
        if isinstance(node, ast.Constant) and node.value == 0:
            return True
    return False


def credited_test_functions(
    tree: ast.Module,
) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    """Top-level pytest-collectable test functions, in module.body order.

    Only ``def test_*`` / ``async def test_*`` directly in ``module.body``
    count: a function nested under ``if`` (including ``if False``)/``try``/
    ``class``/another function is not collectable by pytest and must not be
    credited for behavioral coverage. Helper functions (non-``test_`` names)
    are likewise ignored.
    """
    return [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    ]


# --- Task 001: divide-by-zero regression ---------------------------------

def has_divide_by_zero_test(tree: ast.Module) -> bool:
    """A top-level ``def test_divide_by_zero`` with ``divide(..., 0)`` in raises(ValueError)."""
    for fn in credited_test_functions(tree):
        if fn.name != "test_divide_by_zero":
            continue
        for sub in ast.walk(fn):
            if _is_raises_block(sub):  # type: ignore[arg-type]
                for call in ast.walk(sub):
                    if (
                        isinstance(call, ast.Call)
                        and _is_call_to(call, "divide")
                        and _contains_zero_arg(call)
                    ):
                        return True
    return False


# --- Task 002: parse_int whitespace + non-numeric ValueError --------------

def _parse_int_str_arg(call: ast.Call) -> str | None:
    if not _is_call_to(call, "parse_int"):
        return None
    if len(call.args) != 1:
        return None
    arg = call.args[0]
    if not isinstance(arg, ast.Constant) or not isinstance(arg.value, str):
        return None
    return arg.value


def has_whitespace_success(tree: ast.Module) -> bool:
    """A top-level ``test_*`` with ``parse_int(<whitespace-bearing literal>) == <int>``."""
    for fn in credited_test_functions(tree):
        for node in ast.walk(fn):
            if not isinstance(node, ast.Compare):
                continue
            if not any(isinstance(op, ast.Eq) for op in node.ops):
                continue

            def _ws_call(nd: ast.AST) -> bool:
                s = (
                    _parse_int_str_arg(nd)
                    if isinstance(nd, ast.Call)
                    else None
                )
                if s is None or s == s.strip():
                    return False
                try:
                    int(s)
                except (ValueError, TypeError):
                    return False
                return True

            if _ws_call(node.left) and any(
                isinstance(c, ast.Constant)
                and isinstance(c.value, int)
                and not isinstance(c.value, bool)
                for c in node.comparators
            ):
                return True
            if any(
                isinstance(node.left, ast.Constant)
                and isinstance(node.left.value, int)
                and not isinstance(node.left.value, bool)
                and _ws_call(c)
                for c in node.comparators
            ):
                return True
    return False


def has_non_numeric_cover(tree: ast.Module) -> bool:
    """A top-level ``test_*`` with ``parse_int(<non-numeric literal>)`` in raises(ValueError)."""
    for fn in credited_test_functions(tree):
        for node in ast.walk(fn):
            if not _is_raises_block(node):  # type: ignore[arg-type]
                continue
            for call in ast.walk(node):
                if not isinstance(call, ast.Call):
                    continue
                s = _parse_int_str_arg(call)
                if s is None:
                    continue
                try:
                    int(s)
                except (ValueError, TypeError):
                    return True
    return False


# --- Task 003: clamp boundary assertions ----------------------------------

def _number(node: ast.AST) -> int | float | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        if isinstance(node.value, bool):  # bool is an int subclass; exclude
            return None
        return node.value
    # Negative literals parse as UnaryOp(USub, Constant(N)); unwrap them so
    # `clamp(-5, 0, 10) == 0` is recognised as a v<lo boundary assertion.
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        inner = _number(node.operand)
        if inner is None:
            return None
        return -inner if isinstance(node.op, ast.USub) else inner
    return None


def clamp_boundary_assertions(tree: ast.Module) -> tuple[bool, bool]:
    """Return (v<lo -> lo asserted, v>hi -> hi asserted)."""
    boundary_lo = False
    boundary_hi = False
    for fn in credited_test_functions(tree):
        for node in ast.walk(fn):
            if not isinstance(node, ast.Compare):
                continue
            if not any(isinstance(op, ast.Eq) for op in node.ops):
                continue
            if not isinstance(node.left, ast.Call) or not _is_call_to(node.left, "clamp"):
                continue
            if len(node.left.args) != 3 or node.left.keywords:
                continue
            va, vb, vc = (_number(a) for a in node.left.args)
            if va is None or vb is None or vc is None:
                continue
            for c in node.comparators:
                vx = _number(c)
                if vx is None:
                    continue
                if va < vb and vx == vb:
                    boundary_lo = True
                if va > vc and vx == vc:
                    boundary_hi = True
    return boundary_lo, boundary_hi


# --- Task 004: median even-count regression --------------------------------

def _median_call(call: ast.Call) -> bool:
    return _is_call_to(call, "median") and len(call.args) == 1


def _median_even_list_arg(call: ast.Call) -> bool:
    """``median([<literals>])`` with an even number of elements."""
    if not _median_call(call):
        return False
    arg = call.args[0]
    if not isinstance(arg, ast.List):
        return False
    return len(arg.elts) % 2 == 0


def has_median_even_success(tree: ast.Module) -> bool:
    """A top-level ``test_*`` with ``median([<even literal list>]) == <number>``."""
    for fn in credited_test_functions(tree):
        for node in ast.walk(fn):
            if not isinstance(node, ast.Compare):
                continue
            if not any(isinstance(op, ast.Eq) for op in node.ops):
                continue

            def _even_call(nd: ast.AST) -> bool:
                return isinstance(nd, ast.Call) and _median_even_list_arg(nd)

            left_is_even = _even_call(node.left)
            comparator_is_number = any(
                isinstance(c, ast.Constant)
                and isinstance(c.value, (int, float))
                and not isinstance(c.value, bool)
                for c in node.comparators
            )
            if left_is_even and comparator_is_number:
                return True
            if any(
                isinstance(node.left, ast.Constant)
                and isinstance(node.left.value, (int, float))
                and not isinstance(node.left.value, bool)
                and _even_call(c)
                for c in node.comparators
            ):
                return True
    return False


# --- Public entry point ----------------------------------------------------

def audit_test_calc(tree: ast.Module, task: str) -> list[str]:
    """Failure reasons for the candidate test file; empty list == accept."""
    failures = introspection_violations(tree)
    if task in {
        "001-fix-div-zero", "005-canary-oneoff", "006-canary-conflicting",
    }:
        if not has_divide_by_zero_test(tree):
            failures.append(
                "no regression test: missing def test_divide_by_zero with "
                "divide(..., 0) inside pytest.raises(ValueError)"
            )
    elif task == "002-add-validation":
        if not has_whitespace_success(tree):
            failures.append(
                "no behavioral coverage: missing parse_int(<whitespace string>) == <int> assertion"
            )
        if not has_non_numeric_cover(tree):
            failures.append(
                "no behavioral coverage: missing parse_int(<non-numeric>) inside pytest.raises(ValueError)"
            )
    elif task == "003-regression-guard":
        boundary_lo, boundary_hi = clamp_boundary_assertions(tree)
        if not boundary_lo:
            failures.append("no boundary assertion: missing clamp(v < lo) == lo")
        if not boundary_hi:
            failures.append("no boundary assertion: missing clamp(v > hi) == hi")
    elif task == "004-regression-test-first":
        if not has_median_even_success(tree):
            failures.append(
                "no behavioral coverage: missing median([<even literal "
                "list>]) == <number> assertion"
            )
    return failures


def audit_test_calc_file(sandbox: Path, task: str) -> tuple[bool, list[str]]:
    """Read + parse the sandbox test_calc.py and audit it. (ok, failures)."""
    path = sandbox / "test_calc.py"
    if not path.is_file():
        return False, ["missing test_calc.py"]
    try:
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src, filename="test_calc.py")
    except SyntaxError as exc:
        return False, [f"test_calc.py does not parse: {exc}"]
    failures = audit_test_calc(tree, task)
    return not failures, failures