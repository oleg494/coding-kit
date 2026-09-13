"""Escape battery executed INSIDE the confinement container.

The host writes `job.json` next to this file (mounted read-only at /probe) with
the host paths it will try to reach; this script attempts every escape class
and prints one JSON object on stdout. It never decides pass/fail — the host
compares the result against its own filesystem (the sentinel must not exist,
the secret must not have been read).
"""
import hashlib
import json
import os
import socket
import subprocess
import sys

PROBE_DIR = os.path.dirname(os.path.abspath(__file__))
WORK = "/work"


def try_read(path):
    try:
        with open(path, "rb") as fh:
            return {"result": "read", "bytes": len(fh.read())}
    except Exception as exc:  # noqa: BLE001 - every failure mode is a result
        return {"result": "blocked", "error": type(exc).__name__}


def try_write(path, data="probe\n"):
    try:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(data)
        return {"result": "wrote"}
    except Exception as exc:  # noqa: BLE001
        return {"result": "blocked", "error": type(exc).__name__}


def main():
    with open(os.path.join(PROBE_DIR, "job.json"), encoding="utf-8") as fh:
        job = json.load(fh)

    out = {"workdir_writable": try_write(os.path.join(WORK, "probe-wrote.txt")),
           "reads": {}, "writes": {}, "symlink": None, "symlink_ro": None,
           "subprocess": None, "network": None, "docker_socket": None,
           "host_env_matches": None}

    for label, path in job["read_targets"].items():
        out["reads"][label] = try_read(path)
    for label, path in job["write_targets"].items():
        out["writes"][label] = try_write(path)

    # symlink escape: create a link inside the writable mount pointing outside,
    # then write through it
    link = os.path.join(WORK, "escape-link")
    try:
        if os.path.islink(link) or os.path.exists(link):
            os.remove(link)
        os.symlink(job["symlink_target"], link)
        out["symlink"] = try_write(os.path.join(link, "sentinel-symlink.txt"))
    except Exception as exc:  # noqa: BLE001
        out["symlink"] = {"result": "blocked", "error": type(exc).__name__}

    # the same trick aimed at a READ-ONLY mount (the trusted verifier or the
    # policy bundle): a candidate-controlled link must not make it writable
    ro_link = os.path.join(WORK, "escape-link-ro")
    try:
        if os.path.islink(ro_link) or os.path.exists(ro_link):
            os.remove(ro_link)
        os.symlink(job["read_only_mount"], ro_link)
        out["symlink_ro"] = try_write(
            os.path.join(ro_link, "attack-symlink.txt"))
    except Exception as exc:  # noqa: BLE001
        out["symlink_ro"] = {"result": "blocked", "error": type(exc).__name__}

    # subprocess escape: a child process must face the same boundary
    target = job["write_targets"].get("absolute") or "/sentinel-subprocess.txt"
    try:
        proc = subprocess.run(
            [sys.executable, "-c",
             "import sys\n"
             "open(sys.argv[1], 'w').write('probe\\n')\n", target],
            capture_output=True, text=True, timeout=60)
        out["subprocess"] = {"result": "wrote" if proc.returncode == 0
                             else "blocked",
                             "returncode": proc.returncode,
                             "error": (proc.stderr or "").strip()[:120]}
    except Exception as exc:  # noqa: BLE001
        out["subprocess"] = {"result": "blocked", "error": type(exc).__name__}

    # network: --network=none must leave no route out
    try:
        sock = socket.create_connection(("1.1.1.1", 80), timeout=5)
        sock.close()
        out["network"] = {"result": "connected"}
    except Exception as exc:  # noqa: BLE001
        out["network"] = {"result": "blocked", "error": type(exc).__name__}

    out["docker_socket"] = {"present": os.path.exists("/var/run/docker.sock")}
    matches = {}
    for name, digest in job.get("host_env_digests", {}).items():
        seen = os.environ.get(name)
        matches[name] = bool(seen) and hashlib.sha256(
            seen.encode("utf-8", "replace")).hexdigest() == digest
    out["host_env_matches"] = matches
    print(json.dumps(out))


if __name__ == "__main__":
    main()
