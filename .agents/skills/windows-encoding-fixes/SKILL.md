---
name: windows-encoding-fixes
description: 'Use when working with Windows (cmd/PowerShell console, MINGW64, script installation): stdout encoding (cp1251 vs UTF-8, UnicodeEncodeError on ✓/Cyrillic), CRLF/LF when writing files (md5 checks of mirrors), UTF-8 BOM for PowerShell 5.1, npm.cmd instead of npm, venv Scripts vs bin, PYTHONIOENCODING/PYTHONUTF8. Verified against 2 Windows 10 bug reports.'
compatibility: Windows (win32), PowerShell 5.1, MINGW64, Python 3.12
license: Proprietary
---


# Windows: encodings, console, cross-platform

Experience from two coding-kit installation bug reports on Windows 10 (research.db
id=141, 146). Each pitfall — with symptom, cause, fix. Apply
to ANY script/file that must also work on Windows.

## 1. stdout encoding: cp1251 kills Russian output

**Symptom:** `UnicodeEncodeError: '\u2713' ... codec can't encode` — fails
when printing `✓`/`✗`/Cyrillic. Shows up when redirecting output
(`script > log 2>&1`) and in a cp1251 console.

**Cause:** the Windows console defaults to cp1251; Python 3.12
takes the console encoding when redirecting, and Unicode does not fit into it.

**Fix (required in every CLI script):**
```python
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: S110,BLE001 — reconfigure is optional
    pass
```
In coding-kit — the single `memory/scripts/_compat.py: fix_encoding()` instead of copying.

**Fix for bash wrappers:**
```bash
export PYTHONIOENCODING="${PYTHONIOENCODING:-utf-8}"
```

**System-level fix (recommended for every Windows box):**
```powershell
[Environment]::SetEnvironmentVariable("PYTHONUTF8", "1", "User")
```

## 2. Writing files: CRLF breaks md5 checks

**Symptom:** `Path.write_text()` on Windows writes `\r\n`; the canonical form is `\n`.
Any md5 check of mirrors/copies falsely fails with «files diverged».

**Fix when writing:** `newline="\n"` + byte comparison:
```python
dst.write_text(content, encoding="utf-8", newline="\n")
# freshness check:
if dst.read_bytes() == content.encode("utf-8"): ...
```

**Fix when checking (bash, md5 with normalization):**
```bash
first=$(tr -d '\r' < "${MIRRORS[0]}" | md5sum | cut -d' ' -f1)
```

## 3. PowerShell 5.1: UTF-8 without BOM is read as cp1251

**Symptom:** a bootstrap .ps1 ignores `--check`, outputs mojibake,
fails on the dash «—» in comments.

**Cause:** Windows PowerShell 5.1 decodes a .ps1 without BOM as cp1251;
Cyrillic and dashes break parsing (down to the argument logic).

**Fix:** save the .ps1 as UTF-8 **with BOM** (EF BB BF at the start of the file).
```python
if not data.startswith(b"\xef\xbb\xbf"):
    p.write_bytes(b"\xef\xbb\xbf" + data)
```
Check: `head -c 3 file.ps1 | od -An -tx1` → `ef bb bf`.

## 4. npm on Windows is npm.cmd

**Symptom:** `subprocess.run(["npm", "install", ...])` →
`FileNotFoundError: [WinError 2]`.

**Cause:** CreateProcess (without shell) does not run .cmd files; on Windows
npm is npm.cmd.

**Fix:** look for `npm.cmd` first on Windows:
```python
def _npm_cmd():
    if os.name == "nt":
        for name in ("npm.cmd", "npm"):
            p = shutil.which(name)
            if p:
                return p
    return "npm"
```

## 5. venv: bin vs Scripts, .exe

**Symptom:** the script looks for `venv/bin/python` — on Windows it does not exist, venv is at
`venv\Scripts\python.exe`.

**Fix (single resolver, `_compat.py`):**
```python
VENV_BIN = VENV / ("Scripts" if os.name == "nt" else "bin")
# the binary on Windows has .exe:
# d / "Scripts" / f"{name}.exe"  vs  d / "bin" / name
```
In bash: iterate candidates `Scripts/python.exe` and `bin/python`.

## 6. winget puts binaries not in PATH

**Symptom:** `shutil.which("clangd")` does not find it — but clangd is installed.

**Cause:** winget puts binaries in `%LOCALAPPDATA%\Microsoft\WinGet\Links\`
(this directory is not always in the process PATH).

**Fix:** also look there:
```python
win_get = Path(os.environ.get("LOCALAPPDATA", HOME)) / "Microsoft" / "WinGet" / "Links"
extra = [str(win_get / "clangd.exe")] if os.name == "nt" else []
```

## 7. GitHub releases: projects use different asset formats per platform

**Symptom:** the script looks for `win32-x64.tar.gz`, but the project only ships
`.zip` for Windows (LuaLS), or the reverse.

**Fix:** pick the asset format by platform:
```python
ext = r"\.zip" if IS_NT else r"\.tar\.gz"
m = re.search(rf'https://[^"]*{key}-{variant}{ext}', json)
# unpacking: zipfile.ZipFile (NT) vs tarfile.open (posix)
```

## 8. bash in Windows PATH is a WSL stub, not Git Bash

**Symptom:** `C:\Windows\System32\bash.exe` prints «use wsl.exe --list to
list distributions» and fails.

**Cause:** the system bash.exe is a WSL stub, not Git Bash.

**Fix:** in docs require Git for Windows (`C:\Program Files\Git\bin\
bash.exe`) or PowerShell wrappers. Do not rely on `bash` from PATH.

## 9. subprocess: child output encoding (BUG-1/4, bug report v2.4)

**Symptom:** `UnicodeDecodeError: 'charmap' codec can't decode byte 0x98`
in subprocess reader threads (part of the output is lost; for the LuaLS download
`stdout` became None → «asset not found») or mojibake
instead of «Checking mirrors» (doctor.py).

**Cause:** `subprocess.run(..., text=True)` without an explicit encoding takes
the ANSI code page (`locale.getencoding()` — cp1251), while console
children write to the OEM page (cp866, `GetConsoleOutputCP`). The two
encodings will never match (CPython issue #105312).

**Fix from both sides (shared helper + children write UTF-8):**

```python
# parent: memory/scripts/_compat.py run() — decodes utf-8 + errors=replace,
# passes PYTHONUTF8=1 to python children (they write UTF-8). NEVER fails
# on foreign encoding:
r = _compat.run(cmd, timeout=120)          # instead of subprocess.run(text=True)
```

```powershell
# child: PowerShell 5.1 writes to pipes with the OEM page — switch at the
# start of .ps1 (about_Character_Encoding):
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [Console]::OutputEncoding
```

**Rejected:** `encoding='oem'` — only available in Python 3.13+ (we need
to support 3.12); decoding via `GetOEMCP()` only in the parent —
does not fix python-child output, which itself writes UTF-8 (after
`fix_encoding()`), and still does not save the output when the encoding
is corrupted; `errors="strict"` — one foreign byte drops the entire capture.

## Universal cross-platform pitfalls

Our 8 pitfalls are NOT unique: they are known problem classes described
in the industry (blog.shellnetsecurity.com «Cross-Platform Scripting Tips»,
PEP 686, pythonfriday.dev #130). Verified by web research 08.2026.

**Which of our pitfalls are universal (confirmed by sources):**
- stdout encoding (cp1251 vs UTF-8) — PEP 686, pythonfriday.dev #130;
- CRLF/LF when writing and in md5 checks — a classic (git core.autocrlf,
  .gitattributes);
- npm.cmd / .cmd files through CreateProcess — the known WinError 2 class;
- venv Scripts vs bin — a standard difference across all venv tools;
- GitHub release assets by platform — a common automation problem.

**What we do NOT have, but the industry knows (add to code when relevant):**

| Pitfall | Symptom | Fix |
|---|---|---|
| Path separators | hardcoding `/` in paths | `Path.home() / "x"` or `os.path.join()` (pathlib) |
| File case | `Config.json` == `config.json` on NTFS/macOS, ≠ on Linux | uniform case for names, don't rely on sensitivity |
| HOME vs USERPROFILE | on Windows `$HOME` is often unset (without Git Bash) | `Path.home()` in Python; in bash `${HOME:-$USERPROFILE}` |
| TEMP vs /tmp | TMPDIR/TEMP differ | `tempfile.gettempdir()` |
| find/which/grep/sed | tools absent or different (find = search text!) | `shutil.which`, python instead of unix pipelines |
| curl — alias | in PowerShell `curl` = Invoke-WebRequest | `curl.exe` explicitly |
| File locking | Windows holds open files, PermissionError | close files (with), don't delete open ones |
| Default shell | bash is not native, PowerShell/CMD have their own syntaxes | one shell + require it (Git Bash) or Python |
| subprocess + PATH on Windows | shell=True solves lookup but is messy | explicit paths, shutil.which, .cmd wrappers |
| PEP 686: UTF-8 by default | Python 3.15 enables UTF-8 everywhere | write `encoding="utf-8"` explicitly now — won't break later |

**Takeaway:** our pitfalls are a special case of general classes; this skill holds
concrete fixes, the table above is insurance against the «next» pitfall.

## Checklist «script is Windows-ready»

- [ ] `fix_encoding()` (or reconfigure) at the start — stdout utf-8
- [ ] child output — via `_compat.run()` (not `subprocess.run(text=True)`
      without encoding) — section 9; .ps1 children — `[Console]::OutputEncoding`
- [ ] writing files with `newline="\n"`, byte comparison
- [ ] venv via the resolver (Scripts vs bin, .exe)
- [ ] npm → npm.cmd (or shell=True), winget links as an extra path
- [ ] .ps1 — UTF-8 with BOM
- [ ] md5 checks with `tr -d '\r'`
- [ ] GitHub release assets by platform (zip vs tar.gz)
- [ ] paths — only pathlib/Path.home(), no hardcoded `/` and `\`
- [ ] read/write files with explicit `encoding="utf-8"` (PEP 686-ready)
- [ ] temp files — `tempfile.gettempdir()`, not `/tmp`
- [ ] run `python scripts/doctor.py` on Windows (0 errors)

## References

- `memory/scripts/_compat.py` — the shared cross-platform module (coding-kit).
- First Windows bug report, second, doctor diagnostics.
- Sources: blog.shellnetsecurity.com «Cross-Platform Scripting Tips
  and Tricks» (01.2026); PEP 686 (UTF-8 default, Python 3.15);
  pythonfriday.dev #130 «Different File Encodings Between Windows and
  Linux».