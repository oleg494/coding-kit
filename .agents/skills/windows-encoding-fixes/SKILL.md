---
name: windows-encoding-fixes
description: 'Use when a script or install fails on Windows text or child-process handling: UnicodeEncodeError or mojibake on ✓/Cyrillic, cp1251 output, CRLF or BOM breakage, md5 mismatch between mirrors, FileNotFoundError from npm, venv bin vs Scripts, winget binaries outside PATH, zip vs tar.gz assets, bash.exe acting as a WSL stub, subprocess decode errors. Not for locating which component failed (systematic-debugging) or Linux-only work.'
compatibility: Windows (win32), PowerShell 5.1, MINGW64/Git Bash, Python 3.12+
license: MIT
metadata:
  version: "6.0.0"
---

# Windows: encodings, console, child processes

Field notes from Windows 10 installers and CLIs that also have to run on
Linux. Each section is one symptom, its cause and a verified fix. The fixes
belong in a shared compatibility helper used by the entry points, not copied
into every module.

## 1. Console output dies on non-ASCII

**Symptom:** `UnicodeEncodeError: ... codec can't encode character '\u2713'`
when printing `✓`, `✗` or Cyrillic. Appears when output is redirected
(`script > log 2>&1`) and in a cp1251 console.

**Cause:** the console code page is cp1251, and Python 3.12 adopts the console
encoding for redirected output; Unicode does not fit.

**Where it applies:** any script that prints non-ASCII. Pure ASCII scripts
need nothing.

**Fix** — one call at each entry point, from the shared helper:
```python
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # reconfigure is optional; a missing stream must not crash
    pass
```
When editing coding-kit, call `fix_encoding()` in `memory/scripts/_compat.py`;
elsewhere, reuse the target project's helper if one exists rather than
assuming that module.

**For bash wrappers:**
```bash
export PYTHONIOENCODING="${PYTHONIOENCODING:-utf-8}"
```

**Machine-wide mitigation** (user scope, worth doing once per box):
```powershell
[Environment]::SetEnvironmentVariable("PYTHONUTF8", "1", "User")
```

## 2. Writing files: CRLF breaks md5 checks

**Symptom:** `Path.write_text()` on Windows produces `\r\n`; the canonical form
is `\n`. Any md5 check over mirrors or copies then fails as "files diverged".

**Fix when writing** — pin the newline and compare bytes:
```python
dst.write_text(content, encoding="utf-8", newline="\n")
if dst.read_bytes() == content.encode("utf-8"): ...   # freshness check
```

**Fix when comparing in bash** — normalize before hashing:
```bash
first=$(tr -d '\r' < "${MIRRORS[0]}" | md5sum | cut -d' ' -f1)
```

## 3. PowerShell 5.1 reads BOM-less UTF-8 as cp1251

**Symptom:** a bootstrap `.ps1` ignores `--check`, prints mojibake, or fails
to parse on an em dash inside a comment.

**Cause:** Windows PowerShell 5.1 decodes a `.ps1` without a BOM as cp1251, so
Cyrillic and punctuation break the parse — argument handling included.

**Fix:** save the script as UTF-8 **with BOM** (`EF BB BF`).
```python
if not data.startswith(b"\xef\xbb\xbf"):
    p.write_bytes(b"\xef\xbb\xbf" + data)
```
Verify: `head -c 3 file.ps1 | od -An -tx1` → `ef bb bf`.

## 4. npm is npm.cmd

**Symptom:** `subprocess.run(["npm", "install"])` →
`FileNotFoundError: [WinError 2]`.

**Cause:** `CreateProcess` without a shell does not execute `.cmd` files, and
npm installs as `npm.cmd` on Windows.

**Fix:** resolve the executable first.
```python
def _npm_cmd():
    if os.name == "nt":
        for name in ("npm.cmd", "npm"):
            p = shutil.which(name)
            if p:
                return p
    return "npm"
```

## 5. venv is Scripts/, not bin/, and binaries carry .exe

**Symptom:** the script looks for `venv/bin/python`; on Windows the venv lives
at `venv\Scripts\python.exe`.

**Fix** — one resolver for the whole project:
```python
VENV_BIN = VENV / ("Scripts" if os.name == "nt" else "bin")
# Windows executables end in .exe:
# d / "Scripts" / f"{name}.exe"  vs  d / "bin" / name
```
In bash, iterate candidates `Scripts/python.exe` and `bin/python`.

## 6. winget installs are not on PATH

**Symptom:** `shutil.which("clangd")` returns nothing although clangd is
installed.

**Cause:** winget puts shims in `%LOCALAPPDATA%\Microsoft\WinGet\Links\`, which
is not always in the process PATH.

**Fix:** add that directory as an extra lookup path.
```python
win_get = Path(os.environ.get("LOCALAPPDATA", HOME)) / "Microsoft" / "WinGet" / "Links"
extra = [str(win_get / "clangd.exe")] if os.name == "nt" else []
```

## 7. Release assets differ per platform

**Symptom:** the installer looks for `win32-x64.tar.gz` but the project ships
only `.zip` for Windows (or the reverse).

**Fix:** select the asset format by platform and unpack accordingly.
```python
ext = r"\.zip" if os.name == "nt" else r"\.tar\.gz"
m = re.search(rf'https://[^"]*{key}-{variant}{ext}', json)
# zipfile.ZipFile on Windows vs tarfile.open elsewhere
```

## 8. `bash` on PATH is a WSL stub

**Symptom:** `C:\Windows\System32\bash.exe` prints "use wsl.exe --list" and
fails.

**Cause:** the system bash is a WSL launcher, not Git Bash.

**Fix:** in documentation and wrappers, require Git for Windows
(`C:\Program Files\Git\bin\bash.exe`) or ship a PowerShell entry point. Do not
rely on `bash` from PATH.

## 9. subprocess decodes child output with the wrong code page

**Symptom:** `UnicodeDecodeError: 'charmap' codec can't decode byte 0x98` inside
subprocess reader threads, truncated output, a download step that reports
"asset not found" because stdout came back empty, or mojibake where a status
message belongs.

**Cause:** `subprocess.run(..., text=True)` without an explicit encoding picks
the ANSI code page (`locale.getencoding()`, cp1251) while console children
write to the OEM page (cp866, `GetConsoleOutputCP`). The two never match
(CPython issue #105312).

**Fix from both sides** — the parent decodes tolerantly, the child writes
UTF-8:
```python
# parent: the shared _compat run() helper decodes utf-8 with errors="replace"
# and exports PYTHONUTF8=1 to python children. Never raises on foreign bytes:
r = _compat.run(cmd, timeout=120)      # instead of subprocess.run(text=True)
```
```powershell
# child: PowerShell 5.1 writes to pipes in the OEM page — switch at startup:
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [Console]::OutputEncoding
```

**Rejected:** `encoding="oem"` (Python 3.13+ only, and 3.12 must keep
working); decoding via `GetOEMCP()` in the parent (does not fix python children
that write UTF-8 themselves, and loses output when the bytes are already
corrupt); `errors="strict"` (one foreign byte drops the whole capture).

## Adjacent Windows cases

Not yet hit in our own reports, but true of Windows and cheap to respect when
the code touches them:

| Case | What happens | Habit |
|---|---|---|
| Path separators | hardcoded `/` or `\` breaks the other side | build paths with `pathlib.Path` / `Path.home()` |
| HOME | `$HOME` is often unset outside Git Bash | `Path.home()` in Python, `${HOME:-$USERPROFILE}` in bash |
| Temp directory | `/tmp` does not exist | `tempfile.gettempdir()` |
| `curl` in PowerShell | resolves to `Invoke-WebRequest`, different flags | call `curl.exe` explicitly |
| Open files | deletion or rewrite of an open file raises `PermissionError` | close with `with`; never delete what you still hold open |
| Executable lookup | `.cmd`/`.bat` and WinGet shims need the lookups above | `shutil.which` plus the extra paths |

For forward compatibility, write `encoding="utf-8"` explicitly on every text
file read/write: PEP 686 makes UTF-8 the default in Python 3.15, and explicit
code keeps the same behavior before and after.

## Checklist — a script is Windows-ready when

- [ ] it prints non-ASCII and calls the shared encoding helper at its entry
      point (§1)
- [ ] it consumes child output through the shared `run()` helper rather than
      bare `subprocess.run(text=True)` (§9); `.ps1` children set
      `[Console]::OutputEncoding`
- [ ] it writes files with `newline="\n"` and compares bytes, not text (§2)
- [ ] it resolves the venv through one resolver: Scripts vs bin, plus `.exe`
      (§5)
- [ ] it resolves npm to `npm.cmd` and adds the WinGet Links directory to
      executable lookup (§4, §6)
- [ ] any `.ps1` it ships is UTF-8 with BOM (§3)
- [ ] mirror or copy checks strip `\r` before hashing (§2)
- [ ] release download picks the asset format by platform (§7)
- [ ] it never calls `bash` from PATH (§8)
- [ ] paths come from `pathlib`, temp files from `tempfile`
- [ ] text file I/O states `encoding="utf-8"` explicitly
- [ ] the project's own doctor/diagnostics script runs clean on a Windows box
      (if it has one)

## References

- `memory/scripts/_compat.py` — the shared compatibility module in this kit.
- PEP 686 (UTF-8 default, Python 3.15); CPython issue #105312 (child encoding
  mismatch); Microsoft `about_Character_Encoding` for PowerShell pipes.