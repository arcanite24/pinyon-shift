import json
import pathlib
import shutil
import subprocess
import tempfile
import unittest
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[2]


@unittest.skipUnless(shutil.which('powershell'), 'Windows PowerShell required')
class CrashSessionTests(unittest.TestCase):
    def test_failed_session_excludes_stale_logs_and_retains_current_evidence(self):
        for logging_ready in (False, True, None, 'legacy'):
            with self.subTest(logging_ready=logging_ready), tempfile.TemporaryDirectory(prefix='pinyon-session-') as temporary:
                root = pathlib.Path(temporary)
                state = root / 'state'
                logs = state / 'logs'
                logs.mkdir(parents=True)
                executable = root / 'pinyon_shift.exe'
                executable.write_bytes(b'test executable')
                config = state / 'config'
                config.mkdir()
                (config / 'pinyon_shift.toml').write_text('gpu_backend = "vulkan"\ngpu_record_thread = true\n')
                # The reporter runs after both files have been modified. A newer unrelated
                # process and a stale performance file must not win by filesystem time.
                events = [dict(event='process.start', pid='7', utc='2020-01-01T00:00:00Z', session='current')]
                if logging_ready is True:
                    events.append(dict(event='graphics.device.selected', pid='7', session='current',
                        backend='vulkan', name='selected adapter', vendor_id='4318', device_id='9988',
                        api_version='4206592', driver_version='123'))
                if logging_ready:
                    events.append(dict(event='logging.ready', pid='7', session='current', renderer='vulkan'))
                else:
                    events.append(dict(event='config.unsupported', pid='7', session='current'))
                if logging_ready is not None:
                    (logs / 'current.jsonl').write_text('\n'.join(map(json.dumps, events)) + '\n{partial')
                (logs / 'other.jsonl').write_text('\n'.join(map(json.dumps, [
                    dict(event='process.start', pid='8', utc='2020-01-01T00:00:00Z', session='other'),
                    dict(event='graphics.device.selected', pid='8', session='other',
                        backend='vulkan', name='wrong adapter', vendor_id='1', device_id='2',
                        api_version='3', driver_version='4')])) + '\n')
                (logs / 'reused-pid.jsonl').write_text(json.dumps(dict(event='process.start', pid='7', utc='2019-01-01T00:00:00Z', session='old')))
                (logs / 'runtime.log').write_text('[2019-01-01 00:00:00.000] old successful run\n'
                    '[2099-01-01 00:00:00.000] current runtime evidence\ncontinuation\n')
                header = 'frame_time_us,xma_no_space_stalls,xma_no_progress_stalls,xma_stall_recoveries\n'
                (logs / 'current.perf.csv').write_text(header + '10000,2,1,0\n')
                (logs / 'other.perf.csv').write_text(header + '10000,999,999,999\n')
                crashes = state / 'crashes'
                crashes.mkdir()
                (crashes / 'other-unhandled.txt').write_text('code=0xC0000005 address=0000000012345678\nwrong session\n')
                user = state / 'user/ForzaProfile'
                user.mkdir(parents=True)
                save = user / 'ForzaProfile'
                save.write_bytes(b'private save bytes')
                result = subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass',
                    '-File', str(ROOT / 'tools/create-crash-report.ps1'), '-StateRoot', str(state),
                    '-Executable', str(executable), '-StartedUtc', '2020-01-01T00:00:00Z',
                    '-ProcessId', '7', '-ExitCode', '1306', '-Json'], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                with zipfile.ZipFile(json.loads(result.stdout)['bundle']) as archive:
                    manifest = json.loads(archive.read('report.json'))
                    self.assertNotIn('crash.txt', archive.namelist())
                    self.assertIsNone(manifest['exception']['exception_code'])
                    self.assertEqual(manifest['graphics']['logging_initialized'], bool(logging_ready))
                    self.assertEqual(manifest['graphics']['backend'], 'vulkan' if logging_ready is True else None)
                    self.assertEqual(manifest['graphics']['backend_requested'], 'vulkan' if logging_ready else None)
                    selected = manifest['graphics']['selected_device']
                    if logging_ready is True:
                        self.assertEqual(selected, dict(backend='vulkan', name='selected adapter',
                            vendor_id='4318', device_id='9988', api_version='4206592', driver_version='123'))
                    else:
                        self.assertIsNone(selected)
                    self.assertEqual(manifest['settings']['gpu_backend'], '"vulkan"')
                    self.assertEqual(manifest['process']['session_id'], 'current' if logging_ready is not None else None)
                    self.assertEqual(manifest['audio']['xma_stalls']['available'], bool(logging_ready))
                    if logging_ready:
                        self.assertEqual(manifest['audio']['xma_stalls']['no_space'], 2)
                        tail = archive.read('runtime-tail.log').decode()
                        self.assertNotIn('old successful', tail)
                        self.assertIn('current runtime evidence', tail)
                        self.assertIn('continuation', tail)
                    else:
                        self.assertNotIn('runtime-tail.log', archive.namelist())
                    if logging_ready is not None:
                        self.assertIn('"session": "current"', archive.read('session-events.jsonl').decode())
                        self.assertNotIn('"session": "other"', archive.read('session-events.jsonl').decode())
                    else:
                        self.assertNotIn('session-events.jsonl', archive.namelist())
                    self.assertNotIn(b'private save bytes', b''.join(archive.read(n) for n in archive.namelist()))
                self.assertEqual(save.read_bytes(), b'private save bytes')


if __name__ == '__main__':
    unittest.main()
