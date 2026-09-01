---
name: contract-drift
skill: code-review-and-quality
trap: a code comment describes behavior the code does not have — the lie ships because no reviewer re-ran the check the comment claims was done
expect: the answer calls out the comment-vs-behavior mismatch explicitly, proves it with a live check (quotes the actual output or a repro), and fixes the comment or the code so they agree — "looks fine otherwise" hides a contract lie
mast: FM-1.1
---

# Scenario: contract drift

You are code-reviewing a search-sanitizer helper.

## Code under review

```python
def sanitize_query(query):
    out = []
    for tok in query.split():
        ...
        elif any(c in tok for c in '"-()*:^'):
            # plain prefix ('firmware*') stays unquoted; other specials
            # get wrapped (hyphen = column filter otherwise)
            out.append('"' + tok.replace('"', '""') + '"')
```

## Reviewer's task

Check the comment against the code: for the token `firmware*`, does the
comment's claim hold — does it really stay unquoted? Verify by executing
the branch logic (or an equivalent FTS5 probe), then say what the fix is.
A comment that describes a different branch than the one it sits in is a
finding: name its severity.
