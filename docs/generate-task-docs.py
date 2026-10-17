"""Generate the implementation plan and selected issue bodies from board-tasks.json."""
import json
from pathlib import Path

root=Path(__file__).resolve().parents[1]
tasks=json.loads((root/'docs/board-tasks.json').read_text(encoding='utf-8'))
ids={t['id'] for t in tasks}
assert len(ids)==len(tasks)
assert all(d in ids for t in tasks for d in t['deps'])
intro='''# Implementation plan

Each task has one owner, a goal, deliverables, dependencies and acceptance criteria. Dates are set by the team.

## Delivery sequence

Foundation → working baseline and coordinate-valuation MVP → model/ontology and analytics integration → deployment, security verification and demonstration.

Start A01, B01, C01, D01 and E01 independently. C01 establishes the shared contract. B09, C11 and D09 cover coordinate valuation and observed price dispersion; C09 covers weekly ingestion.

Mane owns D01–D09 and E01–E05 as regular project tasks. Security work follows component availability and E05 feeds release verification C10. Artyom owns AWS and IAM. S01–S04 are Release/P2, performed only after the core release and security work if time remains. They do not block C10.
'''
sections=[]
mapping_path=root/'docs/board-issues.json'
mapping={i['code']:i for i in json.loads(mapping_path.read_text(encoding='utf-8'))}
for t in tasks:
 deps=', '.join(f"[{d}](#{d.lower()})" for d in t['deps']) or 'None.'
 planning=f"Owner: @{t['owner']} | Area: {t['area']} | Phase: {t['phase']} | Priority: {t['priority']}"
 criteria='\n'.join('- [ ] '+c for c in t['criteria'])
 sections.append(f'<a id="{t["id"].lower()}"></a>\n\n## {t["id"]}: {t["title"]}\n\n{planning}\n\n{t["goal"]}\n\nDependencies: {deps}\n\nAcceptance criteria:\n\n{criteria}')
 if t['id'].startswith(('E','S')) or t['id']=='C10':
  out=root/'docs'/('sysadmin-issue-bodies' if t['id'].startswith('S') else 'security-issue-bodies')
  out.mkdir(exist_ok=True)
  links=', '.join(f"[{d}]({mapping[d]['url']})" if d in mapping else d for d in t['deps']) or 'None - ready to start.'
  body=f"## Goal\n\n{t['goal']}\n\n## Acceptance criteria\n\n{criteria}\n\n## Dependencies\n\n{links}\n\n## Planning\n\n{planning}\n\n[Implementation plan](https://github.com/Artyomkrtchyan/fairrent/blob/main/docs/implementation-plan.md#{t['id'].lower()})\n"
  (out/f"{t['id']}.md").write_text(body,encoding='utf-8',newline='\n')
(root/'docs/implementation-plan.md').write_text(intro+'\n'+'\n\n'.join(sections)+'\n',encoding='utf-8',newline='\n')
print(f'Generated plan: {len(tasks)} tasks.')
