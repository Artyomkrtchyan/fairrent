"""Offline release contract: update golden-AMI scripts without embedding credentials."""
import base64
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SCRIPT=Path(__file__).resolve().parents[1]/'scripts'/'deploy_asg.py'
spec=importlib.util.spec_from_file_location('deploy',SCRIPT)
deploy=importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy)
IMAGES={name:'566663271715.dkr.ecr.eu-central-1.amazonaws.com/fairrent-'+name+'@sha256:'+'a'*64 for name in ('backend','frontend')}


class ReleaseTests(unittest.TestCase):
    def test_release_preserves_database_config_installs_scripts_and_enables_logs(self):
        payload=base64.b64decode(deploy.build_user_data(IMAGES))
        self.assertLessEqual(len(payload),16384)
        config=json.loads(payload.decode().split('\n',1)[1])
        files={entry['path']:entry for entry in config['write_files']}
        for name in ('backend','frontend'):
            script=files[f'/usr/local/sbin/fairrent-{name}-start.py']
            self.assertEqual(script['permissions'],'0750')
            self.assertIn('awslogs-create-group=false',script['content'])
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary)
            original={'db_host':'private-db.invalid','db_secret_name':'secret-reference','other':'preserve'}
            for name in IMAGES:
                (directory/(name+'.json')).write_text(json.dumps(original))
            release=files['/opt/fairrent/release.py']['content'].replace("Path('/etc/fairrent')",'Path('+repr(temporary)+')')
            with patch('subprocess.run') as systemctl:
                exec(compile(release,'release.py','exec'),{})
            self.assertEqual(systemctl.call_count,2)
            for name,image in IMAGES.items():
                updated=json.loads((directory/(name+'.json')).read_text())
                self.assertEqual({key:updated[key] for key in original},original)
                self.assertEqual(updated[name+'_image'],image)
                self.assertEqual(updated['log_group'],'/fairrent/dev/'+name)

    def test_oversized_bootstrap_is_rejected_before_a_launch_template_can_be_created(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary)
            for name in IMAGES:
                (directory/f'fairrent-{name}-start.py').write_text('x'*17000)
            with self.assertRaisesRegex(ValueError,'16 KiB'):
                deploy.build_user_data(IMAGES,bootstrap_directory=directory)


if __name__=='__main__':
    unittest.main()
