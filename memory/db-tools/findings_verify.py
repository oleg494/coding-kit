"""findings verify: re-run a finding's verify-cmd and stamp/clear freshness."""
import datetime
import subprocess
import sys

from findings_db import connect  # also puts scripts/ (_compat) on sys.path
import _compat  # noqa: E402


def cmd_verify(args):
    """Re-run a finding's verify-cmd: memory that proves itself fresh.
    VERIFIED (exit 0, verified_at stamped) or FAILED (exit 1)."""
    con = connect()
    cur = con.cursor()
    r = cur.execute("SELECT topic, verify_cmd, verified_at FROM findings "
                    "WHERE id = ?", (args.id,)).fetchone()
    if not r:
        print(f"no finding with id={args.id}")
        con.close()
        sys.exit(1)
    if not r["verify_cmd"]:
        print(f"finding [{args.id}] has no verify-cmd "
              "(add one: findings.py edit ... / add --verify-cmd)")
        con.close()
        sys.exit(1)
    cmd = r["verify_cmd"]
    print(f"[~] running: {cmd}")
    # P15 (D-F): verify_cmd is a SHELL line by design ('cd … && pytest');
    # shlex.split broke every stored multi-command value. Writers of this
    # store already hold the shell — an exec-allowlist is disproportionate.
    # Freshness: a TIMEOUT is a failed check too — the evidence hung
    # instead of erroring. Catch it here so the clearing branch below is
    # reached instead of crashing with the stale stamp retained.
    timeout = getattr(args, "timeout", None) or 300
    try:
        out = _compat.run(cmd, shell=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        print(f"[✗] FAILED (timeout after {timeout}s): "
              f"\"{r['topic']}\" — last verified: {r['verified_at'] or 'never'}",
              file=sys.stderr)
        cur.execute("UPDATE findings SET verified_at = '' WHERE id = ?",
                    (args.id,))
        con.commit()
        con.close()
        sys.exit(1)
    tail = "\n".join(((out.stdout or "") + (out.stderr or "")).splitlines()[-5:])
    if out.returncode == 0:
        now = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")
        cur.execute("UPDATE findings SET verified_at = ? WHERE id = ?",
                    (now, args.id))
        con.commit()
        print(f"[✓] VERIFIED: \"{r['topic']}\" at {now}")
        con.close()
        return
    # Freshness: a FAILED check proves the current evidence no longer
    # passes — the prior stamp describes a state that just failed, so
    # clear it (empty string = schema's unverified sentinel, matching
    # cmd_edit). search_all.py reads bool(verified_at).
    cur.execute("UPDATE findings SET verified_at = '' WHERE id = ?",
                (args.id,))
    con.commit()
    print(f"[✗] FAILED (rc={out.returncode}): \"{r['topic']}\" — "
          f"last verified: {r['verified_at'] or 'never'}")
    if tail:
        print(tail)
    con.close()
    sys.exit(1)
