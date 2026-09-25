import io,json,os,subprocess,tempfile,unittest,zipfile,hashlib
from pathlib import Path
from unittest.mock import patch
import python_bootstrap as bootstrap
import repro_runtime as runtime

class BootstrapTests(unittest.TestCase):
    def test_other_python_versions_delegate_without_installing_to_host(self):
        for version in [(3,8),(3,9),(3,10),(3,11),(3,14)]:
            with self.subTest(version=version), tempfile.TemporaryDirectory() as temp:
                root=Path(temp).resolve();entry=root/'run_all.py'
                python=root/'.repro-env/bin/python'
                with patch.object(runtime.sys,'version_info',version),patch.object(bootstrap,'prepare_python',return_value=python) as prepare,patch.object(runtime.subprocess,'call',return_value=0) as call,patch.object(runtime,'dependency_errors') as deps:
                    with self.assertRaises(SystemExit):runtime.ensure_environment(entry,['--prepare-only'])
                    prepare.assert_called_once_with(root);deps.assert_not_called()
                    self.assertEqual(call.call_args.args[0],[str(python),'-X','utf8',str(entry),'--prepare-only'])

    def test_compatible_environment_requires_no_network(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(bootstrap,'compatible_python',return_value=True),patch.object(bootstrap,'download_uv') as download:
            bootstrap.prepare_python(Path(temp));download.assert_not_called()

    def test_download_checks_hash_before_executing(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            (root/'bootstrap_uv.json').write_text(json.dumps({'version':'test','platforms':{'test':{'url':'https://files.pythonhosted.org/test.whl','sha256':'bad'}}}),encoding='utf-8')
            with patch.object(bootstrap,'platform_key',return_value='test'),patch.object(bootstrap.urllib.request,'urlopen',return_value=io.BytesIO(b'corrupt')):
                with self.assertRaisesRegex(RuntimeError,'校验失败'):bootstrap.download_uv(root)
            self.assertFalse((root/'.repro-tools/uv').exists())

    def test_managed_environment_is_local_and_preserves_previous(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);old=root/'.repro-env';old.mkdir();(old/'keep').write_text('old')
            with patch.object(bootstrap,'compatible_python',side_effect=[False,True]),patch.object(bootstrap,'download_uv',return_value=root/'.repro-tools/uv'),patch.object(bootstrap.subprocess,'run') as run:
                bootstrap.prepare_python(root)
            call=run.call_args
            self.assertEqual(call.kwargs['env']['UV_PYTHON_INSTALL_DIR'],str(root/'.repro-python'))
            self.assertEqual(call.kwargs['env']['UV_PYTHON_PREFERENCE'],'only-managed')
            self.assertEqual(len(list(root.glob('.repro-env.previous-*/keep'))),1)

if __name__=='__main__':unittest.main()
