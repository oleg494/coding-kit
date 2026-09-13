import contextlib, importlib.util, io, json, shutil, sys, tempfile
from pathlib import Path
adapter_path=Path(sys.argv[1]).resolve()
sys.path.insert(0,str(adapter_path.parent))
spec=importlib.util.spec_from_file_location("probe_adapter",adapter_path)
mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
def snap(root):
    return {p.relative_to(root).as_posix():p.read_bytes().hex() if p.is_file() else None for p in root.rglob("*")}
results=[]
for case in ("foreign", "crlf", "binary", "anchor_failure", "legacy", "preview"):
    with tempfile.TemporaryDirectory(prefix="independent-recovery-") as tmp:
        root=Path(tmp); kit=root/"kit"; home=root/"profile"
        skill=kit/"skills"/"alpha"; skill.mkdir(parents=True); home.mkdir()
        (home/"skills").mkdir(); (kit/"VERSION").write_text("1.0")
        (skill/"SKILL.md").write_text("---\nname: alpha\ndescription: sample\n---\nbody\n")
        (home/"config.yaml").write_bytes(b"model: default\r\nskills:\r\n  external_dirs: []\r\n")
        (home/"SOUL.md").write_bytes(b"personal\r\n")
        ext=home/"kit-skills"; category=ext/"coding-kit"
        if case in ("foreign","preview"):
            (category/"foreign").mkdir(parents=True)
            (category/"foreign"/"data.bin").write_bytes(b"user\xff")
        if case=="binary": (skill/"asset.bin").write_bytes(b"\x00\xff\r\n")
        if case=="legacy": shutil.copytree(kit/"skills",home/"skills"/"coding-kit")
        before=snap(home); original=mod.safe_write_text; failed=False
        def injected(path,*args,**kwargs):
            global failed
            if Path(path).name==mod.RESTORE_NAME and not failed:
                failed=True; raise OSError("injected anchor failure")
            return original(path,*args,**kwargs)
        if case=="anchor_failure": mod.safe_write_text=injected
        args=["--kit",str(kit),"--hermes-home",str(home)]
        log=io.StringIO()
        try:
            with contextlib.redirect_stdout(log),contextlib.redirect_stderr(log):
                plan=mod.plan(kit,home,ext,case=="legacy")
                rc=mod.main(args+["apply"]+(["--retire-legacy"] if case=="legacy" else []))
                if case=="anchor_failure": ok=rc!=0 and snap(home)==before
                elif case=="preview": ok=rc==0 and plan["retired"]==0 and (category/"foreign"/"data.bin").read_bytes()==b"user\xff"
                elif case=="legacy": ok=rc==0 and not list((home/"skills").rglob("SKILL.md")) and mod.main(args+["restore"])==0 and snap(home)==before
                elif case=="binary": ok=rc==0 and (category/"alpha"/"asset.bin").read_bytes()==b"\x00\xff\r\n" and mod.main(args+["restore"])==0 and snap(home)==before
                else: ok=rc==0 and mod.main(args+["restore"])==0 and snap(home)==before
            results.append({"case":case,"pass":ok,"log":log.getvalue()})
        except Exception as exc: results.append({"case":case,"pass":False,"error":str(exc),"log":log.getvalue()})
        finally: mod.safe_write_text=original
print(json.dumps(results,indent=2))
sys.exit(0 if all(r["pass"] for r in results) else 1)
