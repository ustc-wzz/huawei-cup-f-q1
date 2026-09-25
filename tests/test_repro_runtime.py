"""启动流程回归：无需网络或真实训练附件。执行 python -X utf8 -m unittest discover -s tests。"""
import hashlib,json,os,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import repro_runtime as runtime

class RuntimeTests(unittest.TestCase):
    def test_inputs_can_be_found_and_checked_repeatedly(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'package';root.mkdir()
            data=root/'附件/real_attachments'
            (data/'A_data_value').mkdir(parents=True);(data/'B_scaling_laws').mkdir()
            raw=data/'A_data_value/raw.jsonl';raw.write_bytes(b'{"id":1}\n')
            manifest={'files':[{'path':'real_attachments/A_data_value/raw.jsonl','sha256':hashlib.sha256(raw.read_bytes()).hexdigest()}]}
            (root/'repro_inputs.json').write_text(json.dumps(manifest),encoding='utf-8')
            runtime.prepare_inputs(root);runtime.prepare_inputs(root)
            self.assertTrue((root/'real_attachments/A_data_value/signals_cache').is_dir())
            (root/'real_attachments/A_data_value/raw.jsonl').write_bytes(b'broken')
            with self.assertRaisesRegex(FileNotFoundError,'损坏'):runtime.prepare_inputs(root)

    def test_missing_dependencies_install_only_inside_package(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);entry=root/'run_all.py';entry.touch()
            (root/'requirements.txt').write_text('numpy==2.3.5\n',encoding='utf-8')
            with patch.object(runtime,'dependency_errors',return_value=['missing']),patch.object(runtime.venv,'EnvBuilder') as builder,patch.object(runtime.subprocess,'run') as run,patch.object(runtime.subprocess,'call',return_value=0),patch.dict(os.environ):
                with self.assertRaises(SystemExit):runtime.ensure_environment(entry,['--prepare-only'])
                builder.return_value.create.assert_called_once_with(root.resolve()/'.repro-env')
                command=next(call.args[0] for call in run.call_args_list if 'install' in call.args[0])
                self.assertIn('.repro-env',command[0]);self.assertIn('install',command)
                self.assertNotEqual(command[0],sys.executable)
                self.assertEqual(os.environ['PYTHONUTF8'],'1')

    def test_existing_environment_reused_without_pip(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);entry=root/'run_all.py';entry.touch()
            (root/'requirements.txt').write_text('numpy==2.3.5\n',encoding='utf-8')
            python=root/'.repro-env'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
            python.parent.mkdir(parents=True);python.touch()
            with patch.object(runtime,'dependency_errors',return_value=['missing']),patch.object(runtime.venv,'EnvBuilder') as builder,patch.object(runtime.subprocess,'run',return_value=subprocess.CompletedProcess([],0)) as run,patch.object(runtime.subprocess,'call',return_value=0) as call:
                with self.assertRaises(SystemExit):runtime.ensure_environment(entry,['--prepare-only'])
                builder.assert_not_called();self.assertEqual(run.call_count,1)
                self.assertNotIn('pip',run.call_args.args[0])
                self.assertEqual(call.call_args.args[0][0],str(python.resolve()))

    def test_bundled_font_has_chinese_glyphs_without_system_install(self):
        from matplotlib import font_manager,ft2font
        family=runtime.configure_fonts()
        font=font_manager.findfont(family,fallback_to_default=False)
        self.assertIn('assets',font)
        self.assertTrue(all(ord(c) in ft2font.FT2Font(font).get_charmap() for c in '中文质量参数'))

    def test_existing_release_is_not_overwritten(self):
        import build_package
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);archive=root/'F题_四问完整复现包_v0.9.0.zip';archive.write_bytes(b'previous')
            with patch.object(build_package,'ROOT',root):
                with self.assertRaises(FileExistsError):build_package.build()
            self.assertEqual(archive.read_bytes(),b'previous')

if __name__=='__main__':unittest.main()
