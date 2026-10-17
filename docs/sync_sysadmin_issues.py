"""Create/update only S01–S04 issues using an authenticated GitHub CLI.

Run with Python in the same WSL environment as gh. Does not modify Projects
without a project-scoped token. Reruns identify existing issues by task prefix.
"""
import json
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[1]
repo = 'Artyomkrtchyan/fairrent'
def gh(*args):
    return subprocess.check_output(['gh', *args], text=True).strip()
tasks = json.loads((root/'docs/board-tasks.json').read_text())
issues = json.loads(gh('issue','list','--repo',repo,'--state','all','--limit','200','--json','number,title,url'))
mapping_path = root/'docs/board-issues.json'
mapping = json.loads(mapping_path.read_text())
for task in tasks:
    if task['id'] not in {'S01','S02','S03','S04'}:
        continue
    prefix = f"{task['id']}:"
    matches = [i for i in issues if i['title'].startswith(prefix)]
    if len(matches)>1:
        raise RuntimeError(f'Duplicate issues for {prefix}; resolve manually.')
    body = root/'docs/sysadmin-issue-bodies'/f"{task['id']}.md"
    title = f"{prefix} {task['title']}"
    if matches:
        item=matches[0]
        gh('issue','edit',str(item['number']),'--repo',repo,'--title',title,'--body-file',str(body),'--add-assignee','manemazmand')
    else:
        url=gh('issue','create','--repo',repo,'--title',title,'--body-file',str(body),'--assignee','manemazmand')
        item={'number':int(url.rsplit('/',1)[1]),'url':url}
    mapping=[i for i in mapping if i['code']!=task['id']]
    mapping.append(dict(code=task['id'],number=item['number'],url=item['url'],owner='manemazmand'))
    mapping_path.write_text(json.dumps(mapping,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(f"{task['id']}: {item['url']}")
