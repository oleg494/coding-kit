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


def sanitize_query(query):
    """Escapes an FTS5 query: tokens with special characters (quotes,
    parens, hyphen — the known «agent-lsp» gotcha, asterisks, dots) are
    wrapped in double quotes. Operators, NEAR(...) and ready-made quoted
    TOKENS (single-token, no inner spaces — tokenization is
    whitespace-based) are left untouched so boolean logic keeps working.

    A trailing '*' ALWAYS lands OUTSIDE the quotes (D-A): '"body*"' is
    an EXACT match of token body (the tokenizer drops the star inside
    quotes), '"body"*' is the prefix — measured 2026-08-22: prox*→2,
    "prox*"→0, "prox"*→2. Dots are special because a bare '5.3' is an
    FTS5 SYNTAX error (dot is not a bareword char); quoted it becomes
    the phrase [5, 3]."""
    out = []
    for tok in query.split():
        upper = tok.upper()
        if upper in OPS or upper.startswith("NEAR(") or \
                (len(tok) >= 2 and tok.startswith('"') and tok.endswith('"')):
            out.append(tok)
            continue
        star = tok.endswith("*")
        body = tok[:-1] if star else tok
        if star or any(c in body for c in '"-().:^'):
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
