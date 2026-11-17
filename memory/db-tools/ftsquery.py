#!/usr/bin/env python3

"""FTS5 query sanitizing — the single implementation.

Consumers: db-tools/search.py, db-tools/findings.py,
memory-scripts/memory-warmup.py (via the ~/.memory/db-tools junction).
Before v2.9 there were three drifting copies with three different
behaviors (audit 2026-08-22 M2); the quoted phrase-prefix semantics were
verified live against FTS5 (raw 'firmware*' and quoted '"firmware*"'
match the same rows — a trailing '*' INSIDE quotes keeps prefix meaning).
"""

OPS = {"AND", "OR", "NOT", "NEAR"}


def _is_balanced_quoted(tok):
    """True when tok is a single FTS5 double-quoted string with >= 1 inner char."""
    if len(tok) < 3 or not (tok.startswith('"') and tok.endswith('"')):
        return False
    i = 1
    end = len(tok) - 1
    while i < end:
        if tok[i] == '"':
            if i + 1 < end and tok[i + 1] == '"':
                i += 2
                continue
            return False
        i += 1
    return True


def _split_tokens(query):
    """Split on whitespace while keeping balanced double-quoted phrases intact."""
    tokens = []
    i, n = 0, len(query)
    while i < n:
        if query[i].isspace():
            i += 1
            continue
        if query[i] == '"':
            j = i + 1
            closed = -1
            while j < n:
                if query[j] == '"':
                    if j + 1 < n and query[j + 1] == '"':
                        j += 2
                        continue
                    closed = j
                    break
                j += 1
            if closed != -1 and (
                closed + 1 == n
                or query[closed + 1].isspace()
                or query[closed + 1] == "*"
            ):
                end = (
                    closed + 2
                    if closed + 1 < n and query[closed + 1] == "*"
                    else closed + 1
                )
                tokens.append(query[i:end])
                i = end
                continue
        start = i
        while i < n and not query[i].isspace():
            i += 1
        tokens.append(query[start:i])
    return tokens


def _needs_quote(body):
    return any(ord(c) < 128 and not (c.isalnum() or c == "_") for c in body)


def _is_brace_filter(tok):
    """Preserve balanced FTS5 brace column filters like {component}."""
    return (
        len(tok) >= 3
        and tok.startswith("{")
        and tok.endswith("}")
        and not any(c.isspace() for c in tok)
    )


def sanitize_query(query):
    """Escapes an FTS5 query: tokens with ASCII special characters (quotes,
    parens, hyphen — the known «agent-lsp» gotcha, asterisks, dots, slashes,
    plus, at, etc.) are wrapped in double quotes. Operators, valid NEAR(...),
    FTS5 brace column filters and balanced quoted phrases (including
    multi-word '"memory root"') pass through untouched so boolean logic,
    column filters and phrase matching keep working.

    A trailing '*' ALWAYS lands OUTSIDE the quotes (D-A): '"body*"' is
    an EXACT match of token body (the tokenizer drops the star inside
    quotes), '"body"*' is the prefix — measured 2026-08-22: prox*→2,
    "prox*"→0, "prox"*→2. Dots are special because a bare '5.3' is an
    FTS5 SYNTAX error (dot is not a bareword char); quoted it becomes
    the phrase [5, 3]."""
    out = []
    for tok in _split_tokens(query):
        if tok == '""':
            continue
        upper = tok.upper()
        if (
            upper in OPS
            or (upper.startswith("NEAR(") and tok.endswith(")"))
            or _is_brace_filter(tok)
            or _is_balanced_quoted(tok)
        ):
            out.append(tok)
            continue
        star = tok.endswith("*") and len(tok) > 1
        body = tok[:-1] if star else tok
        if star and _is_balanced_quoted(body):
            out.append(body + "*")
        elif star or _needs_quote(body):
            quoted = '"' + body.replace('"', '""') + '"'
            out.append(quoted + "*" if star else quoted)
        else:
            out.append(tok)
    return " ".join(out)


def fallback_query(query):
    """Last-resort sanitizer for FTS syntax errors: split every token on
    dots and quote each piece (implicit AND). '5.3' -> '"5" "3"'. Only
    used by cmd_search's single retry after sanitize_query raised."""
    out = []
    for tok in query.split():
        body = tok[1:-1] if (tok.startswith('"') and tok.endswith('"')
                             and len(tok) > 1) else tok
        body = body.rstrip("*")
        for part in body.split("."):
            if part:
                out.append('"' + part.replace('"', '""') + '"')
    return " ".join(out) or '""'
