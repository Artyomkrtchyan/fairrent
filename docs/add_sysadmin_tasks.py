"""Maintain the additional system administration track and issue body files."""
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
tasks = [
    dict(id='S01', title='Set up an isolated Linux lab and document secure access', phase='Foundation', priority='P1', deps=['C02'],
         goal='Deploy the existing Compose application manually on a clean Ubuntu VM and document Linux administration fundamentals.', criteria=[
             'Document VM OS/resources, a non-root administrator, SSH key access, file permissions and firewall rules; verify access before restricting SSH.',
             'Start the API and PostGIS from the repository instructions, verify health/readiness, and document container networking and persistent storage.',
             'Keep secrets and real listing data out of Git; provide a reproducible setup and teardown guide with sanitized command output.']),
    dict(id='S02', title='Document service monitoring and Linux troubleshooting', phase='MVP', priority='P1', deps=['S01'],
         goal='Make application and host failures diagnosable on the isolated Linux lab.', criteria=[
             'Document checks for API health/readiness, Compose status/logs, listening ports, disk space, memory and host services.',
             'Provide a small shell check script with meaningful exit codes and no credentials in output; demonstrate healthy and unavailable database states.',
             'Document log locations, bounded log retention and a symptom-to-diagnosis checklist with sanitized evidence.']),
    dict(id='S03', title='Implement and verify lab database backup and restore', phase='MVP', priority='P1', deps=['S01'],
         goal='Demonstrate recoverability of PostgreSQL/PostGIS using a small synthetic dataset.', criteria=[
             'Provide documented pg_dump/pg_restore commands or shell scripts, backup naming, restricted permissions and a retention policy; exclude backups from Git.',
             'Restore into a separate disposable database or Compose project and verify synthetic rows and PostGIS functionality without overwriting the working database.',
             'Record backup/restore duration, database and PostGIS versions, failure handling and rerun steps; distinguish this lab procedure from production RDS backups.']),
    dict(id='S04', title='Run failure recovery exercises and deliver the administration runbook', phase='Release', priority='P1', deps=['S02','S03'],
         goal='Demonstrate independent operation and recovery of the lab application.', criteria=[
             'Reproduce database unavailability, an occupied API port and invalid configuration safely on the lab; record symptoms, diagnosis and recovery.',
             'Demonstrate recovery after VM reboot and a database restore drill; verify health/readiness and retained synthetic data.',
             'Publish a runbook covering access, startup/shutdown, logs, backup/restore, recovery and lab teardown; have another teammate reproduce one procedure.']),
]
path = root/'docs/board-tasks.json'
existing = json.loads(path.read_text(encoding='utf-8'))
ids = {t['id'] for t in tasks}
existing = [t for t in existing if t['id'] not in ids]
for task in tasks:
    task.update(owner='manemazmand', area='Infra')
existing.extend(tasks)
path.write_text(json.dumps(existing, indent=2, ensure_ascii=False)+'\n', encoding='utf-8', newline='\n')
sections=[]
out=root/'docs/sysadmin-issue-bodies'
out.mkdir(exist_ok=True)
for task in tasks:
    deps=', '.join(f'[{d}](implementation-plan.md#{d.lower()})' for d in task['deps'])
    body=f"## Goal\n\n{task['goal']}\n\nOwner: @manemazmand | Area: Infra / System Administration | Phase: {task['phase']} | Priority: {task['priority']}\n\nDependencies: {', '.join(task['deps'])}.\n\n## Acceptance criteria\n\n"+'\n'.join('- [ ] '+c for c in task['criteria'])+'\n\n## Scope\n\nIsolated Linux learning lab with synthetic data. No Ansible. AWS production architecture and existing frontend ownership remain unchanged. Work sequentially after frontend MVP priorities; do not provision paid resources as part of planning.\n'
    (out/f"{task['id']}.md").write_text(body,encoding='utf-8',newline='\n')
    sections.append(f"<a id=\"{task['id'].lower()}\"></a>\n\n## {task['id']}: {task['title']}\n\nOwner: @manemazmand | Area: Infra / System Administration | Phase: {task['phase']} | Priority: {task['priority']}\n\n{task['goal']}\n\nDependencies: {deps}.\n\nAcceptance criteria:\n\n"+'\n'.join('- [ ] '+c for c in task['criteria']))
plan=root/'docs/implementation-plan.md'
text=plan.read_text(encoding='utf-8')
marker='\n## Additional system administration track\n'
text=text.split(marker)[0]
text+=marker+'\nMane owns S01–S04 in addition to frontend. This isolated learning lab is not a release dependency. Schedule it sequentially around frontend MVP priorities. No Ansible is required. See [scope and ownership](system-administration.md).\n\n'+'\n\n'.join(sections)+'\n'
plan.write_text(text,encoding='utf-8',newline='\n')
print(f'{len(existing)} tasks; added S01–S04.')
