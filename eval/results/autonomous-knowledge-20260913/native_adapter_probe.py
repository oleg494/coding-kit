"""Exercise the current adapter with native Hermes APIs in a disposable profile."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

kit, runtime, home = map(Path, sys.argv[1:4])
assert Path(os.environ['HERMES_HOME']).resolve() == home.resolve()
sys.path.insert(0, str(runtime))
checks = {}
def invoke(command):
    p = subprocess.run([sys.executable, str(kit / 'scripts/tools/hermes_adapter.py'),
                        '--kit', str(kit), '--hermes-home', str(home), command],
                       capture_output=True, text=True, encoding='utf-8', timeout=60)
    assert p.returncode == 0, p.stdout + p.stderr
    return p.stdout

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

home.mkdir(exist_ok=True, parents=True)
(home / 'skills').mkdir(exist_ok=True)
(home / 'config.yaml').write_bytes(b'model: native-probe\r\n')
(home / 'SOUL.md').write_bytes(b'Foreign soul\r\n')
original = {n: (home / n).read_bytes() for n in ['config.yaml', 'SOUL.md']}
preview = invoke('preview')
checks['preview_no_owned_mutation'] = not (home / 'kit-skills').exists() and all((home/n).read_bytes() == b for n,b in original.items())
apply = invoke('apply')
from tools import skills_tool, skill_usage
from agent.prompt_builder import build_skills_system_prompt
from hermes_constants import get_hermes_home
checks['native_home_is_disposable'] = Path(get_hermes_home()).resolve() == home.resolve()
names = sorted(p.name for p in (kit / 'skills').iterdir() if (p / 'SKILL.md').is_file())
listing = json.loads(skills_tool.skills_list())
visible = {s['name'] for s in listing.get('skills', []) if s.get('category') == 'coding-kit'}
checks['catalogue_all_skills'] = visible == set(names)
prompt = build_skills_system_prompt(available_tools=None, available_toolsets=None)
checks['rendered_prompt_all_skills'] = all(n in prompt for n in names)
loaded = json.loads(skills_tool.skill_view('coding-kit/ponytail'))
checks['categorized_load_full_body'] = loaded.get('success') is True and 'The ladder' in loaded.get('content', '')
projected = home / 'kit-skills/coding-kit/ponytail/SKILL.md'
sha_before = digest(projected)
archived, message = skill_usage.archive_skill('ponytail')
checks['curator_cannot_archive_projection'] = archived is False and projected.exists() and digest(projected) == sha_before
owned = {p.relative_to(home).as_posix(): digest(p) for p in (home/'kit-skills').rglob('*') if p.is_file()}
owned.update({n: digest(home/n) for n in original})
repeat = invoke('apply')
checks['repeat_apply_preserves_owned_bytes'] = all((home/n).is_file() and digest(home/n) == sha for n,sha in owned.items())
restore = invoke('restore')
checks['restore_foreign_bytes_exactly'] = all((home/n).read_bytes() == b for n,b in original.items())
checks['restore_removes_projection'] = not (home/'kit-skills/coding-kit').exists()
print(json.dumps({'ok': all(checks.values()), 'checks': checks, 'visible_count':len(visible), 'expected_count':len(names), 'archive_message':message, 'preview':preview, 'apply':apply, 'repeat':repeat, 'restore':restore}, ensure_ascii=False, indent=2))
sys.exit(0 if all(checks.values()) else 1)
