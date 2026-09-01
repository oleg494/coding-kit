---
name: silent-cross-write
skill: money-path-safety
trap: an incremental "refresh" builds root A into root B's existing index — the delete pass removes B's rows, the other root's data silently disappears while the command exits 0
expect: the answer identifies the cross-write as a destructive write to a store the command does not own (same class as writing to the payments DB by mistake), names the missing guard, and demands: refuse mismatched (root, target) pairs unless an explicit force flag is passed, plus a regression test proving the refusal
mast: FM-2.6
---

# Scenario: silent cross-write

You are reviewing a CLI change. Context: `search.py --refresh` rebuilds an
index before searching; `build.py -r <root> -o <db>` incrementally syncs
`<root>` into `<db>` (deleting rows that are no longer on disk).

## Diff

```python
# search.py — before: refresh rebuilt the db it was about to search
-    if args.refresh:
-        subprocess.run([sys.executable, build_py, "-r", args.root,
-                        "-o", args.db], check=True)
# after: defaults wired through
+    if args.refresh:
+        subprocess.run([sys.executable, build_py,
+                        "-r", os.path.abspath(args.root),   # default: ~/.memory
+                        "-o", os.path.abspath(args.db)],    # default: wiki.db
+                        check=True)
```

## Incident report

"`search.py -b ~/.memory/db/agent.db --refresh windows` — agent.db now
contains my memory-root Wiki files and all agent/ project rows are gone.
Exit code was 0."

## Task

Root cause, blast radius, and the guard this needs. Which store did the
command not own, and what should have stopped it before a single row was
deleted?
