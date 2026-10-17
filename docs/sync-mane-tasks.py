"""Create/update E/S issues and C10 from generated bodies using authenticated gh."""
import json
import re
import subprocess
from pathlib import Path

root=Path(__file__).resolve().parents[1]
repo='Artyomkrtchyan/fairrent'
def gh(*args):
 return subprocess.check_output(['gh',*args],text=True).strip()
tasks=json.loads((root/'docs/board-tasks.json').read_text(encoding='utf-8'))
issues=json.loads(gh('issue','list','--repo',repo,'--state','all','--limit','200','--json','number,title,url'))
path=root/'docs/board-issues.json'
mapping=json.loads(path.read_text(encoding='utf-8'))
for t in tasks:
 if not t['id'].startswith(('E','S')) and t['id']!='C10':
  continue
 matches=[i for i in issues if re.match(r'^\[?'+t['id']+r'(?:\]|:)',i['title'])]
 if len(matches)>1:
  raise RuntimeError('Duplicate task issues: '+t['id'])
 body=root/'docs'/('sysadmin-issue-bodies' if t['id'].startswith('S') else 'security-issue-bodies')/f"{t['id']}.md"
 title=f"[{t['id']}] {t['title']}"
 if matches:
  item=matches[0]
  gh('issue','edit',str(item['number']),'--repo',repo,'--title',title,'--body-file',str(body),'--add-assignee',t['owner'])
 else:
  url=gh('issue','create','--repo',repo,'--title',title,'--body-file',str(body),'--assignee',t['owner'])
  item=dict(number=int(url.rsplit('/',1)[1]),url=url)
 mapping=[i for i in mapping if i['code']!=t['id']]
 mapping.append(dict(code=t['id'],number=item['number'],url=item['url'],owner=t['owner']))
 path.write_text(json.dumps(mapping,indent=2)+'\n',encoding='utf-8',newline='\n')
 print(t['id'],item['url'],flush=True)
