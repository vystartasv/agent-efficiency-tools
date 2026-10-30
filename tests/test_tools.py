import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import shutil
import subprocess
import struct
import sys
import tempfile
import threading
import time
import unittest
from urllib.parse import quote
import zlib

ROOT = Path(__file__).resolve().parents[1]
CAPTURE = ROOT / 'bin/output-capture'
IMAGE = ROOT / 'bin/image-prepare'
BROWSER = ROOT / 'bin/browser-read'
DOCTOR = ROOT / 'bin/agent-doctor'
CLI = ROOT / 'bin/agent-tools'

class ToolsTest(unittest.TestCase):
    def test_doctor_reports_capabilities(self):
        result = subprocess.run([str(DOCTOR)], capture_output=True, text=True, check=True)
        report = json.loads(result.stdout)
        self.assertIn('python3', report['commands'])
        self.assertIn(report['playwright_available'], (True, False, None))
        self.assertIn(report['chromium_executable_present'], (True, False, None))
        self.assertIn(report['image_diff_dependencies_available'], (True, False, None))

    def test_dispatcher(self):
        result = subprocess.run([str(CLI), 'doctor'], capture_output=True, text=True, check=True)
        self.assertIn('commands', json.loads(result.stdout))
        self.assertEqual(subprocess.run([str(CLI), 'unknown'], capture_output=True).returncode, 2)

    def test_dispatcher_through_symlink_and_path(self):
        with tempfile.TemporaryDirectory() as d:
            link = Path(d)/'agent-tools'
            link.symlink_to(CLI)
            env = os.environ.copy()
            env['PATH'] = d + os.pathsep + env['PATH']
            result = subprocess.run(['agent-tools', 'doctor'], cwd=d, env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('commands', json.loads(result.stdout))

    def test_dispatcher_reports_missing_python(self):
        with tempfile.TemporaryDirectory() as d:
            env = os.environ.copy()
            env['PATH'] = d
            result = subprocess.run([str(CLI), '--help'], env=env, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('python3', result.stderr)

    def test_subcommand_help_without_optional_backends(self):
        commands = ['doctor', 'image-prepare', 'image-batch', 'image-crop', 'image-diff', 'image-text',
                    'media-info', 'video-frame', 'audio-transcribe', 'pdf-text', 'pdf-find',
                    'pdf-ocr', 'output-capture', 'log-scan', 'test-report', 'browser-read']
        with tempfile.TemporaryDirectory() as d:
            (Path(d)/'python3').symlink_to(shutil.which('python3'))
            env = os.environ.copy()
            env['PATH'] = d
            for command in commands:
                with self.subTest(command=command):
                    result = subprocess.run([str(CLI), command, '--help'], env=env, capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn(f'Usage: agent-tools {command}', result.stdout)
            self.assertEqual(subprocess.run([str(CLI), 'unknown', '--help'], env=env, capture_output=True).returncode, 2)

    def test_log_scan_bounded_context_and_recoverable_source(self):
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / 'build.log'
            log.write_text('start\ncompile module\nERROR first issue\n  at first.js:1\nretry\nFAIL second issue\nAssertionError: expected 2\n' + 'x' * 80 + '\n')
            run = subprocess.run([str(CLI), 'log-scan', str(log), '--context', '1', '--max-matches', '1', '--max-line-chars', '12'], capture_output=True, text=True)
            self.assertEqual(run.returncode, 1, run.stderr)
            result = json.loads(run.stdout)
            self.assertEqual(result['lines_scanned'], 8)
            self.assertEqual(result['match_count'], 3)
            self.assertEqual(result['matches_returned'], 1)
            self.assertTrue(result['matches_truncated'])
            self.assertEqual([(line['line'], line['kind']) for line in result['lines']],
                             [(2, 'context'), (3, 'match'), (4, 'context')])
            self.assertTrue(result['line_text_truncated'])
            self.assertEqual(log.read_text().count('FAIL second issue'), 1)
            absent = subprocess.run([str(CLI), 'log-scan', str(log), '--pattern', 'NEVER'], capture_output=True, text=True)
            self.assertEqual(absent.returncode, 0)
            self.assertEqual(json.loads(absent.stdout)['match_count'], 0)
            self.assertEqual(subprocess.run([str(CLI), 'log-scan', str(log), '--pattern', '['], capture_output=True).returncode, 2)

    def test_junit_report_details_and_inconsistency(self):
        with tempfile.TemporaryDirectory() as d:
            report = Path(d) / 'junit.xml'
            report.write_text('''<testsuites xmlns="urn:junit"><testsuite name="s" failures="1" errors="1">
              <testcase name="pass"/><testcase name="skip"><skipped/></testcase>
              <testcase name="broken" classname="example"><failure message="expected 3">trace &amp; detail</failure></testcase>
              <error message="setup failed">setup stack</error></testsuite></testsuites>''')
            cmd = [str(CLI), 'test-report', str(report)]
            run = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(run.returncode, 1, run.stderr)
            data = json.loads(run.stdout)
            self.assertEqual((data['testcases'], data['skipped']), (3, 1))
            self.assertEqual(data['report'], str(report))
            self.assertEqual(data['failures'][0]['test'], 'broken')
            self.assertEqual(data['failures'][0]['message'], 'expected 3')
            self.assertEqual(data['failures'][0]['detail'], 'trace & detail')
            self.assertEqual(data['failures'][1]['detail'], 'setup stack')
            report.write_text('<testsuite failures="1"><testcase name="pass"/></testsuite>')
            run = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(run.returncode, 2)
            self.assertTrue(json.loads(run.stdout)['warnings'])
            report.write_text('<testsuite><testcase name="pass"/></testsuite>')
            self.assertEqual(subprocess.run(cmd, capture_output=True).returncode, 0)
            report.write_text('<testsuites/>')
            run = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(run.returncode, 2)
            self.assertIn('no testcases', json.loads(run.stdout)['warnings'][0])
            report.write_text('<testsuite tests="2"><testcase name="one"/></testsuite>')
            self.assertEqual(subprocess.run(cmd, capture_output=True).returncode, 2)
            report.write_text('<testsuite>')
            self.assertEqual(subprocess.run(cmd, capture_output=True).returncode, 2)
            report.write_text('<html/>')
            self.assertEqual(subprocess.run(cmd, capture_output=True).returncode, 2)

    @unittest.skipUnless(shutil.which('node'), 'requires Node.js')
    def test_junit_report_from_node_test_runner(self):
        with tempfile.TemporaryDirectory() as d:
            source, report = Path(d)/'failure.test.js', Path(d)/'report.xml'
            source.write_text("const {test}=require('node:test'); const assert=require('node:assert/strict'); test('broken example',()=>assert.equal('actual','expected'));\n")
            run = subprocess.run(['node', '--test', '--test-reporter=junit', str(source)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 1, run.stderr)
            report.write_text(run.stdout)
            result = subprocess.run([str(CLI), 'test-report', str(report)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 1, result.stderr)
            failure = json.loads(result.stdout)['failures'][0]
            self.assertEqual(failure['test'], 'broken example')
            self.assertIn('actual', failure['detail'])
            self.assertIn('expected', failure['detail'])

    @unittest.skipUnless(os.path.exists('/System/Library/Frameworks/PDFKit.framework'), 'requires macOS PDFKit')
    def test_pdf_page_text_and_incomplete_pages(self):
        # Minimal two-page PDF: selectable text on page one, blank page two.
        content = b'BT /F1 6 Tf 20 180 Td 8 TL (HELLO PAGE ONE) Tj T* ' + b'(TARGET) Tj T* ' * 21 + b'ET'
        objects = [b'<< /Type /Catalog /Pages 2 0 R >>',
                   b'<< /Type /Pages /Kids [3 0 R 4 0 R] /Count 2 >>',
                   b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] /Resources << /Font << /F1 5 0 R >> >> /Contents 6 0 R >>',
                   b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] /Resources << >> >>',
                   b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
                   b'<< /Length %d >>\nstream\n' % len(content) + content + b'\nendstream']
        pdf = bytearray(b'%PDF-1.4\n')
        offsets = []
        for number, obj in enumerate(objects, 1):
            offsets.append(len(pdf))
            pdf.extend(f'{number} 0 obj\n'.encode() + obj + b'\nendobj\n')
        xref = len(pdf)
        pdf.extend(f'xref\n0 {len(objects)+1}\n0000000000 65535 f \n'.encode())
        for offset in offsets:
            pdf.extend(f'{offset:010} 00000 n \n'.encode())
        pdf.extend(f'trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode())
        with tempfile.TemporaryDirectory() as d:
            file = Path(d) / 'example.pdf'
            file.write_bytes(pdf)
            cmd = [str(CLI), 'pdf-text', str(file)]
            run = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            result = json.loads(run.stdout)
            self.assertEqual(result['page_count'], 2)
            self.assertIn('HELLO PAGE ONE', result['pages'][0]['text'])
            blank = subprocess.run(cmd + ['2'], capture_output=True, text=True)
            self.assertEqual(blank.returncode, 1, blank.stderr)
            self.assertTrue(json.loads(blank.stdout)['pages'][0]['no_extractable_text'])
            both = subprocess.run(cmd + ['1', '2'], capture_output=True, text=True)
            self.assertEqual(both.returncode, 1, both.stderr)
            self.assertEqual([page['page'] for page in json.loads(both.stdout)['pages']], [1, 2])
            self.assertEqual(subprocess.run(cmd + ['3'], capture_output=True).returncode, 2)
            self.assertEqual(subprocess.run([str(CLI), 'pdf-text', str(Path(d)/'missing.pdf')], capture_output=True).returncode, 2)
            search = [str(CLI), 'pdf-find', str(file)]
            found = subprocess.run(search + ['hello'], capture_output=True, text=True)
            self.assertEqual(found.returncode, 1, found.stderr)
            result = json.loads(found.stdout)
            self.assertEqual(result['match_count'], 1)
            self.assertEqual(result['matches'][0]['page'], 1)
            self.assertIn('HELLO', result['matches'][0]['excerpt'])
            self.assertEqual(result['no_text_pages'], [2])
            many = subprocess.run(search + ['target'], capture_output=True, text=True)
            self.assertEqual(many.returncode, 1, many.stderr)
            result = json.loads(many.stdout)
            self.assertEqual(result['match_count'], 21)
            self.assertEqual(len(result['matches']), 20)
            self.assertTrue(result['matches_truncated'])
            absent = subprocess.run(search + ['not present'], capture_output=True, text=True)
            self.assertEqual(absent.returncode, 1)
            self.assertEqual(json.loads(absent.stdout)['match_count'], 0)
            self.assertEqual(subprocess.run(search + [''], capture_output=True).returncode, 2)
            one_page = Path(d)/'one-page.pdf'
            script = 'import PDFKit; import Foundation; let doc = PDFDocument(url: URL(fileURLWithPath: CommandLine.arguments[1]))!; doc.removePage(at: 1); if !doc.write(to: URL(fileURLWithPath: CommandLine.arguments[2])) { exit(1) }'
            make = subprocess.run(['swift', '-e', script, str(file), str(one_page)], capture_output=True, text=True)
            self.assertEqual(make.returncode, 0, make.stderr)
            complete = subprocess.run([str(CLI), 'pdf-find', str(one_page), 'not present'], capture_output=True, text=True)
            self.assertEqual(complete.returncode, 0, complete.stderr)
            self.assertEqual(json.loads(complete.stdout)['match_count'], 0)

    @unittest.skipUnless(os.path.exists('/System/Library/Frameworks/PDFKit.framework'), 'requires macOS PDFKit')
    def test_pdf_ocr_on_image_and_blank_pages(self):
        generator = '''import AppKit
import PDFKit
let doc = PDFDocument()
for hasText in [true, false] {
    let image = NSImage(size: NSSize(width: 1000, height: 500))
    image.lockFocus()
    NSColor.white.setFill(); NSRect(x: 0, y: 0, width: 1000, height: 500).fill()
    if hasText { ("ORDER 7264 READY" as NSString).draw(at: NSPoint(x: 80, y: 250), withAttributes: [.font: NSFont.systemFont(ofSize: 64), .foregroundColor: NSColor.black]) }
    image.unlockFocus()
    doc.insert(PDFPage(image: image)!, at: doc.pageCount)
}
guard doc.write(to: URL(fileURLWithPath: CommandLine.arguments[1])) else { exit(1) }
'''
        with tempfile.TemporaryDirectory() as d:
            source, script = Path(d)/'scan.pdf', Path(d)/'fixture.swift'
            script.write_text(generator)
            fixture = subprocess.run(['swift', str(script), str(source)], capture_output=True, text=True)
            self.assertEqual(fixture.returncode, 0, fixture.stderr)
            plain = subprocess.run([str(CLI), 'pdf-text', str(source)], capture_output=True, text=True)
            self.assertEqual(plain.returncode, 1, plain.stderr)
            fallback = subprocess.run([str(CLI), 'pdf-text', str(source), '1', '2', '--ocr-missing'], capture_output=True, text=True)
            self.assertEqual(fallback.returncode, 1, fallback.stderr)
            fallback_pages = json.loads(fallback.stdout)['pages']
            self.assertIn('ORDER 7264 READY', fallback_pages[0]['text'])
            self.assertEqual(fallback_pages[0]['method'], 'vision-ocr')
            self.assertTrue(fallback_pages[0]['no_extractable_text'])
            self.assertTrue(fallback_pages[1]['no_recognized_text'])
            ocr = subprocess.run([str(CLI), 'pdf-ocr', str(source), '1', '2'], capture_output=True, text=True)
            self.assertEqual(ocr.returncode, 1, ocr.stderr)
            pages = json.loads(ocr.stdout)['pages']
            self.assertIn('ORDER 7264 READY', pages[0]['text'])
            self.assertTrue(pages[1]['no_recognized_text'])
            self.assertLessEqual(max(pages[0]['image_width'], pages[0]['image_height']), 2400)
            self.assertEqual(subprocess.run([str(CLI), 'pdf-ocr', str(source), '3'], capture_output=True).returncode, 2)
            self.assertEqual(subprocess.run([str(CLI), 'pdf-ocr', str(Path(d)/'missing.pdf')], capture_output=True).returncode, 2)

    @unittest.skipUnless(shutil.which('ffmpeg'), 'requires ffmpeg')
    def test_video_frame_selection_and_failures(self):
        with tempfile.TemporaryDirectory() as d:
            source, target = Path(d)/'video.mkv', Path(d)/'frame.png'
            generate = ['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=red:s=16x16:r=1:d=2',
                        '-f', 'lavfi', '-i', 'color=blue:s=16x16:r=1:d=2',
                        '-filter_complex', '[0:v][1:v]concat=n=2:v=1:a=0', '-c:v', 'ffv1', str(source)]
            made = subprocess.run(generate, capture_output=True, text=True)
            self.assertEqual(made.returncode, 0, made.stderr)
            cmd = [str(CLI), 'video-frame', str(source), str(target), '2']
            run = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(json.loads(run.stdout)['requested_seconds'], '2')
            self.assertEqual(json.loads(run.stdout)['frame_time_seconds'], 2.0)
            pixels = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(target), '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], capture_output=True, check=True).stdout
            self.assertGreater(pixels[2], 200)
            self.assertLess(pixels[0], 30)
            original = target.read_bytes()
            self.assertNotEqual(subprocess.run(cmd, capture_output=True).returncode, 0)
            self.assertEqual(target.read_bytes(), original)
            fractional = subprocess.run([str(CLI), 'video-frame', str(source), str(Path(d)/'fractional.png'), '1.25'], capture_output=True, text=True)
            self.assertEqual(fractional.returncode, 0, fractional.stderr)
            self.assertEqual(json.loads(fractional.stdout)['frame_time_seconds'], 2.0)
            offset = Path(d)/'offset.mkv'
            shifted = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(source), '-vf', 'setpts=PTS+10/TB', '-c:v', 'ffv1', str(offset)], capture_output=True, text=True)
            self.assertEqual(shifted.returncode, 0, shifted.stderr)
            offset_result = subprocess.run([str(CLI), 'video-frame', str(offset), str(Path(d)/'offset.png'), '1.25'], capture_output=True, text=True)
            self.assertEqual(offset_result.returncode, 0, offset_result.stderr)
            self.assertEqual(json.loads(offset_result.stdout)['frame_time_seconds'], 2.0)
            missing = Path(d)/'missing.png'
            self.assertNotEqual(subprocess.run([str(CLI), 'video-frame', str(source), str(missing), '100'], capture_output=True).returncode, 0)
            self.assertFalse(missing.exists())
            self.assertNotEqual(subprocess.run([str(CLI), 'video-frame', str(source), str(missing), 'NaN'], capture_output=True).returncode, 0)
            self.assertFalse(list(Path(d).glob('.video-frame-*')))

    def test_video_frame_missing_timestamp_is_explicit(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            source, target, fake = root/'input', root/'out.png', root/'ffmpeg'
            source.write_bytes(b'fixture')
            fake.write_text('#!/usr/bin/env python3\nfrom pathlib import Path\nimport sys\nPath(sys.argv[-1]).write_bytes(b"fixture")\n')
            fake.chmod(0o755)
            env = os.environ.copy()
            env['PATH'] = d + os.pathsep + env['PATH']
            result = subprocess.run([str(CLI), 'video-frame', str(source), str(target), '0'], capture_output=True, text=True, env=env)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIsNone(json.loads(result.stdout)['frame_time_seconds'])

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'requires FFmpeg and FFprobe')
    def test_media_info_audio_and_video(self):
        with tempfile.TemporaryDirectory() as d:
            audio, video = Path(d)/'tone.wav', Path(d)/'video.mkv'
            generate_audio = ['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=1', str(audio)]
            generate_video = ['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=red:s=16x16:r=1:d=1', '-c:v', 'ffv1', str(video)]
            for cmd in (generate_audio, generate_video):
                made = subprocess.run(cmd, capture_output=True, text=True)
                self.assertEqual(made.returncode, 0, made.stderr)
            for file, kind in ((audio, 'audio'), (video, 'video')):
                result = subprocess.run([str(CLI), 'media-info', str(file)], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                data = json.loads(result.stdout)
                self.assertEqual(data['source'], str(file))
                self.assertEqual(data['streams'][0]['codec_type'], kind)
                self.assertFalse(data['truncated'])
            broken = Path(d)/'bad.media'
            broken.write_bytes(b'not media')
            self.assertNotEqual(subprocess.run([str(CLI), 'media-info', str(broken)], capture_output=True).returncode, 0)
            self.assertEqual(subprocess.run([str(CLI), 'media-info', str(Path(d)/'missing')], capture_output=True).returncode, 2)

    def test_media_info_flags_stream_truncation(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            source, stub = root/'fixture', root/'ffprobe'
            source.write_text('fixture')
            stub.write_text('#!/usr/bin/env python3\nimport json\nprint(json.dumps({"streams": [{"index": i} for i in range(101)]}))\n')
            stub.chmod(0o755)
            env = os.environ.copy()
            env['PATH'] = d + os.pathsep + env['PATH']
            result = subprocess.run([str(CLI), 'media-info', str(source)], capture_output=True, text=True, env=env)
            self.assertEqual(result.returncode, 1, result.stderr)
            data = json.loads(result.stdout)
            self.assertEqual((data['stream_count'], len(data['streams'])), (101, 100))
            self.assertTrue(data['truncated'])
            self.assertEqual(data['format'], {})

    def test_audio_transcription_adapter(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            audio, model = root/'sample.wav', root/'model.pt'
            audio.write_bytes(b'fixture')
            model.write_bytes(b'fixture')
            stub = root/'whisper'
            stub.write_text('''#!/usr/bin/env python3
import json, os, pathlib, sys
if os.environ.get("FAKE_FAIL"): sys.exit(3)
if os.environ.get("EXPECTED_CLIP"):
    if "--clip_timestamps" not in sys.argv or sys.argv[sys.argv.index("--clip_timestamps") + 1] != os.environ["EXPECTED_CLIP"]: sys.exit(4)
out = pathlib.Path(sys.argv[sys.argv.index("--output_dir") + 1])
count = int(os.environ.get("FAKE_SEGMENTS", "1"))
segments = [{"start": i, "end": i + 0.5, "text": "hello"} for i in range(count)]
(out / (pathlib.Path(sys.argv[1]).stem + ".json")).write_text(json.dumps({"language": "en", "segments": segments}))
''')
            stub.chmod(0o755)
            env = os.environ.copy()
            env['PATH'] = str(root) + os.pathsep + env['PATH']
            cmd = [str(CLI), 'audio-transcribe', str(audio), str(model), '--language', 'en']
            run = subprocess.run(cmd, capture_output=True, text=True, env=env)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(json.loads(run.stdout)['segments'][0], {'start': 0, 'end': 0.5, 'text': 'hello'})
            env['EXPECTED_CLIP'] = '12.5,30'
            run = subprocess.run(cmd + ['--start', '12.5', '--end', '30'], capture_output=True, text=True, env=env)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(json.loads(run.stdout)['requested_range_seconds'], ['12.5', '30'])
            self.assertEqual(subprocess.run(cmd + ['--start', '12'], capture_output=True, env=env).returncode, 2)
            self.assertEqual(subprocess.run(cmd + ['--start', '10', '--end', '5'], capture_output=True, env=env).returncode, 2)
            self.assertEqual(subprocess.run(cmd + ['--start', 'NaN', '--end', '5'], capture_output=True, env=env).returncode, 2)
            del env['EXPECTED_CLIP']
            env['FAKE_SEGMENTS'] = '201'
            run = subprocess.run(cmd, capture_output=True, text=True, env=env)
            self.assertEqual(run.returncode, 1)
            self.assertTrue(json.loads(run.stdout)['truncated'])
            env['FAKE_SEGMENTS'] = '0'
            run = subprocess.run(cmd, capture_output=True, text=True, env=env)
            self.assertEqual(run.returncode, 1)
            self.assertTrue(json.loads(run.stdout)['no_recognized_speech'])
            env['FAKE_FAIL'] = '1'
            self.assertNotEqual(subprocess.run(cmd, capture_output=True, env=env).returncode, 0)
            self.assertEqual(subprocess.run([str(CLI), 'audio-transcribe', str(audio), str(root/'missing.pt')], capture_output=True, env=env).returncode, 2)

    def test_output_recovery_and_status(self):
        with tempfile.TemporaryDirectory() as d:
            file = Path(d) / 'out'
            cmd = [str(CAPTURE), '--output', str(file), '--tail-bytes', '4', '--', 'python3', '-c', 'import sys; print("early failure"); print("end"); sys.exit(7)']
            run = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(run.returncode, 7)
            self.assertIn('early failure', file.read_text())
            self.assertIn('Earlier output omitted', run.stdout)
            self.assertEqual(file.stat().st_mode & 0o777, 0o600)
            self.assertNotEqual(subprocess.run(cmd, capture_output=True).returncode, 0)
            self.assertIn('early failure', file.read_text())

    def test_capture_missing_command_and_invalid_tail(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'out'
            missing = subprocess.run([str(CAPTURE), '--output', str(path), '--', '/no/such/command'], capture_output=True, text=True)
            self.assertEqual(missing.returncode, 127)
            self.assertIn('could not start command', path.read_text())
            self.assertIn('exit: 127', missing.stdout)
            self.assertNotEqual(subprocess.run([str(CAPTURE), '--output', str(path)+'2', '--tail-bytes', '0', '--', 'true'], capture_output=True).returncode, 0)
            blocked = Path(d)/'not-executable'
            blocked.write_text('do not run')
            result = subprocess.run([str(CAPTURE), '--output', str(Path(d)/'permission.log'), '--', str(blocked)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 126)
            self.assertIn('could not start command', (Path(d)/'permission.log').read_text())
            killed = subprocess.run([str(CAPTURE), '--output', str(Path(d)/'signal.log'), '--', 'python3', '-c', 'import os, signal; os.kill(os.getpid(), signal.SIGTERM)'], capture_output=True, text=True)
            self.assertEqual(killed.returncode, 143)
            self.assertIn('exit: 143', killed.stdout)

    def test_capture_timeout_stops_descendants_and_keeps_output(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            sentinel = root/'late'
            child = f'import time; from pathlib import Path; time.sleep(1.5); Path({str(sentinel)!r}).write_text("orphan")'
            parent = f'import subprocess, sys, time; subprocess.Popen([sys.executable, "-c", {child!r}]); print("started", flush=True); time.sleep(10)'
            log = root/'timeout.log'
            result = subprocess.run([str(CAPTURE), '--output', str(log), '--timeout', '0.5', '--', 'python3', '-c', parent], capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 124, result.stderr)
            self.assertIn('started', log.read_text())
            self.assertIn('timed out after', log.read_text())
            time.sleep(1.6)
            self.assertFalse(sentinel.exists())
            for value in ('0', '-1', 'nan', 'inf', '86401'):
                invalid = subprocess.run([str(CAPTURE), '--output', str(root/'invalid.log'), '--timeout', value, '--', 'true'], capture_output=True)
                self.assertEqual(invalid.returncode, 2)
            self.assertFalse((root/'invalid.log').exists())
            success = subprocess.run([str(CAPTURE), '--output', str(root/'ok.log'), '--timeout', '3', '--', 'python3', '-c', 'print("done")'], capture_output=True, text=True)
            self.assertEqual(success.returncode, 0, success.stderr)
            self.assertIn('done', success.stdout)

    def test_image_existing_and_bad_quality(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / 'existing.png'
            out.write_bytes(b'untouched')
            r = subprocess.run([str(IMAGE), str(ROOT/'assets/icon.svg'), str(out)], capture_output=True)
            self.assertNotEqual(r.returncode, 0)
            self.assertEqual(out.read_bytes(), b'untouched')
            r = subprocess.run([str(IMAGE), str(ROOT/'assets/icon.svg'), str(Path(d)/'new.png'), '800', '50'], capture_output=True)
            self.assertNotEqual(r.returncode, 0)

    @unittest.skipUnless(os.path.exists('/usr/bin/sips'), 'requires macOS sips')
    def test_image_creation_and_dangling_symlink(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / 'new.jpg'
            r = subprocess.run([str(IMAGE), str(ROOT/'assets/icon.svg'), str(out), '300', '70'], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue(out.stat().st_size > 0)
            link = Path(d) / 'link.png'
            link.symlink_to(Path(d) / 'missing')
            r = subprocess.run([str(IMAGE), str(ROOT/'assets/icon.svg'), str(link)], capture_output=True)
            self.assertNotEqual(r.returncode, 0)
            self.assertTrue(link.is_symlink())
            self.assertFalse((Path(d) / 'missing').exists())
            original, copy, small = Path(d)/'source.png', Path(d)/'copy.png', Path(d)/'small.png'
            first = subprocess.run([str(IMAGE), str(ROOT/'assets/icon.svg'), str(original), '300'], capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            copied = subprocess.run([str(IMAGE), str(original), str(copy), '300'], capture_output=True, text=True)
            self.assertEqual(copied.returncode, 0, copied.stderr)
            self.assertEqual(copy.read_bytes(), original.read_bytes())
            resized = subprocess.run([str(IMAGE), str(original), str(small), '100'], capture_output=True, text=True)
            self.assertEqual(resized.returncode, 0, resized.stderr)
            self.assertIn('pixelWidth: 100', resized.stdout)
            self.assertEqual(subprocess.run([str(IMAGE), str(original), str(Path(d)/'bad.png'), '000'], capture_output=True).returncode, 2)
            batch_dir = Path(d)/'batch'
            batch = subprocess.run([str(CLI), 'image-batch', str(batch_dir), str(original), str(small)], capture_output=True, text=True)
            self.assertEqual(batch.returncode, 0, batch.stderr)
            report = json.loads(batch.stdout)
            self.assertFalse(report['failed'])
            self.assertEqual(len(report['results']), 2)
            self.assertTrue(all(Path(item['output']).exists() for item in report['results']))
            self.assertTrue(all('bytes_saved' in item for item in report['results']))

    @unittest.skipUnless(os.path.exists('/System/Library/Frameworks/Vision.framework'), 'requires macOS Vision')
    def test_image_ocr_plain_json_truncated_and_empty(self):
        generator = '''import AppKit
for (index, hasText) in [true, false].enumerated() {
    let image = NSImage(size: NSSize(width: 1000, height: 500))
    image.lockFocus()
    NSColor.white.setFill(); NSRect(x: 0, y: 0, width: 1000, height: 500).fill()
    if hasText { ("ORDER 7264 READY" as NSString).draw(at: NSPoint(x: 80, y: 250), withAttributes: [.font: NSFont.systemFont(ofSize: 64), .foregroundColor: NSColor.black]) }
    image.unlockFocus()
    let bitmap = NSBitmapImageRep(data: image.tiffRepresentation!)!
    try! bitmap.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: CommandLine.arguments[index + 1]))
}
'''
        with tempfile.TemporaryDirectory() as d:
            text_image, blank_image, empty_image, script = Path(d)/'text.png', Path(d)/'blank.png', Path(d)/'empty.png', Path(d)/'fixture.swift'
            script.write_text(generator)
            fixture = subprocess.run(['swift', str(script), str(text_image), str(blank_image)], capture_output=True, text=True)
            self.assertEqual(fixture.returncode, 0, fixture.stderr)
            empty_image.write_bytes(b'')
            cmd = [str(CLI), 'image-text', str(text_image)]
            plain = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(plain.returncode, 0, plain.stderr)
            self.assertIn('ORDER 7264 READY', plain.stdout)
            regions = subprocess.run(cmd + ['--regions'], capture_output=True, text=True)
            self.assertEqual(regions.returncode, 0, regions.stderr)
            region_data = json.loads(regions.stdout)['regions']
            self.assertEqual(len(region_data), 1)
            self.assertIn('ORDER 7264 READY', region_data[0]['text'])
            self.assertGreater(region_data[0]['width'], 0)
            self.assertGreaterEqual(region_data[0]['y'], 0)
            self.assertLessEqual(region_data[0]['y'] + region_data[0]['height'], 1.01)
            bounded = subprocess.run(cmd + ['--json', '--max-chars', '5'], capture_output=True, text=True)
            self.assertEqual(bounded.returncode, 1, bounded.stderr)
            data = json.loads(bounded.stdout)
            self.assertEqual(data['text'], 'ORDER')
            self.assertTrue(data['truncated'])
            self.assertGreater(data['characters'], len(data['text']))
            blank = subprocess.run([str(CLI), 'image-text', str(blank_image), '--json'], capture_output=True, text=True)
            self.assertEqual(blank.returncode, 1, blank.stderr)
            self.assertTrue(json.loads(blank.stdout)['no_recognized_text'])
            batch = subprocess.run([str(CLI), 'image-text', '--batch', str(text_image), str(blank_image), str(Path(d)/'missing.png'), str(empty_image)], capture_output=True, text=True)
            self.assertEqual(batch.returncode, 2)
            batch_data = json.loads(batch.stdout)
            self.assertTrue(batch_data['failed'])
            self.assertTrue(batch_data['incomplete'])
            self.assertIn('ORDER 7264 READY', batch_data['results'][0]['text'])
            self.assertTrue(batch_data['results'][1]['no_recognized_text'])
            self.assertIn('error', batch_data['results'][2])
            self.assertIn('no readable dimensions', batch_data['results'][3]['error'])
            self.assertEqual(subprocess.run([str(CLI), 'image-text', str(empty_image)], capture_output=True).returncode, 2)
            partial_batch = subprocess.run([str(CLI), 'image-text', '--batch', str(text_image), str(blank_image)], capture_output=True, text=True)
            self.assertEqual(partial_batch.returncode, 1)
            self.assertTrue(json.loads(partial_batch.stdout)['incomplete'])
            self.assertEqual(subprocess.run(cmd + ['--max-chars', '0'], capture_output=True).returncode, 2)
            self.assertEqual(subprocess.run([str(CLI), 'image-text', str(Path(d)/'missing.png')], capture_output=True).returncode, 2)

    @unittest.skipUnless(sys.platform == 'darwin' and os.path.exists('/usr/bin/swift'), 'requires macOS Swift and ImageIO')
    def test_crop_coordinates_and_overwrite_protection(self):
        def chunk(kind, data):
            return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
        with tempfile.TemporaryDirectory() as d:
            source, target = Path(d)/'source.png', Path(d)/'crop.png'
            # Top half red, bottom half blue. Each scanline uses PNG filter 0.
            pixels = b''.join(b'\0' + (b'\xff\0\0' if y < 2 else b'\0\0\xff') * 4 for y in range(4))
            source.write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 4, 4, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(pixels)) + chunk(b'IEND', b''))
            args = [str(CLI), 'image-crop', str(source), str(target), '1', '2', '2', '1']
            run = subprocess.run(args, capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertIn('pixelWidth: 2', run.stdout)
            self.assertIn('pixelHeight: 1', run.stdout)
            check = 'import AppKit; let i=NSBitmapImageRep(data: try! Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1])))!; let c=i.colorAt(x:0,y:0)!; print(c.blueComponent > 0.9 && c.redComponent < 0.1)'
            pixel = subprocess.run(['swift', '-e', check, str(target)], capture_output=True, text=True)
            self.assertEqual(pixel.returncode, 0, pixel.stderr)
            self.assertEqual(pixel.stdout.strip(), 'true')
            original = target.read_bytes()
            self.assertNotEqual(subprocess.run(args, capture_output=True).returncode, 0)
            self.assertEqual(target.read_bytes(), original)
            self.assertFalse(list(Path(d).glob('.image-crop.*')))
            bad = [str(CLI), 'image-crop', str(source), str(Path(d)/'bad.png'), '3', '3', '2', '2']
            self.assertNotEqual(subprocess.run(bad, capture_output=True).returncode, 0)
            self.assertFalse((Path(d)/'bad.png').exists())

    @unittest.skipUnless(shutil.which('node'), 'requires Node.js')
    def test_image_diff_comparison(self):
        probe = subprocess.run(['node', '-e', "require.resolve('pixelmatch'); require.resolve('pngjs')"], cwd=CLI.parent.parent, capture_output=True)
        if probe.returncode:
            self.skipTest('pixelmatch and pngjs are unavailable to the toolkit')
        def chunk(kind, data):
            return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
        def png(width, height, rgb):
            rows = (b'\0' + rgb * width) * height
            return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(rows)) + chunk(b'IEND', b'')
        with tempfile.TemporaryDirectory() as d:
            red, blue, small = Path(d)/'red.png', Path(d)/'blue.png', Path(d)/'small.png'
            red.write_bytes(png(4, 4, b'\xff\0\0'))
            blue.write_bytes(png(4, 4, b'\0\0\xff'))
            small.write_bytes(png(2, 2, b'\xff\0\0'))
            cmd = [str(CLI), 'image-diff', str(red)]
            same = subprocess.run(cmd + [str(red)], capture_output=True, text=True)
            self.assertEqual(same.returncode, 0, same.stderr)
            self.assertEqual(json.loads(same.stdout)['changed_pixels'], 0)
            different = subprocess.run(cmd + [str(blue)], capture_output=True, text=True)
            self.assertEqual(different.returncode, 0, different.stderr)
            self.assertEqual(json.loads(different.stdout)['changed_pixels'], 16)
            mismatch = subprocess.run(cmd + [str(small)], capture_output=True, text=True)
            self.assertEqual(mismatch.returncode, 1)
            self.assertFalse(json.loads(mismatch.stdout)['dimensions_match'])
            self.assertEqual(subprocess.run(cmd + [str(blue), '2'], capture_output=True).returncode, 2)
            invalid = Path(d)/'invalid.png'
            invalid.write_bytes(b'not a png')
            self.assertEqual(subprocess.run(cmd + [str(invalid)], capture_output=True).returncode, 2)

    def test_browser_rejects_scheme(self):
        r = subprocess.run([str(BROWSER), 'file:///etc/passwd'], capture_output=True)
        self.assertNotEqual(r.returncode, 0)
        r = subprocess.run([str(BROWSER), 'data:text/html,test', '--timeout-ms', '0'], capture_output=True)
        self.assertNotEqual(r.returncode, 0)

    def test_browser_reads_bounded_local_fixture(self):
        report = json.loads(subprocess.run([str(DOCTOR)], capture_output=True, text=True, check=True).stdout)
        if not report['chromium_executable_present']:
            self.skipTest('Playwright Chromium is not available from the current directory')
        r = subprocess.run([str(BROWSER), 'data:text/html,<title>Fixture</title><p>Hello World</p>', '5'], capture_output=True, text=True)
        self.assertEqual(r.returncode, 1, r.stderr)
        page = json.loads(r.stdout)
        self.assertEqual(page['title'], 'Fixture')
        self.assertEqual(page['text'], 'Hello')
        self.assertTrue(page['truncated'])

    def test_browser_main_scope_reduces_chrome_and_reports_fallback(self):
        report = json.loads(subprocess.run([str(DOCTOR)], capture_output=True, text=True, check=True).stdout)
        if not report['chromium_executable_present']:
            self.skipTest('Playwright Chromium is not available from the current directory')
        html = '<nav>' + ' '.join(f'<a href="/#{n}">Navigation item {n}</a>' for n in range(40)) + '</nav><main><h1>Primary title</h1><p>Important result code 42</p></main>'
        url = 'data:text/html,' + quote(html)
        full = subprocess.run([str(BROWSER), url], capture_output=True, text=True)
        focused = subprocess.run([str(BROWSER), url, '--main'], capture_output=True, text=True)
        self.assertEqual(full.returncode, 0, full.stderr)
        self.assertEqual(focused.returncode, 0, focused.stderr)
        full_data, focused_data = json.loads(full.stdout), json.loads(focused.stdout)
        self.assertEqual(full_data['content_scope'], 'body')
        self.assertGreater(full_data['characters'], focused_data['characters'] * 5)
        self.assertEqual(focused_data['content_scope'], 'main')
        self.assertIn('Important result code 42', focused_data['text'])
        self.assertNotIn('Navigation item', focused_data['text'])
        fallback_url = 'data:text/html,' + quote('<p>No semantic container</p>')
        fallback = subprocess.run([str(BROWSER), fallback_url, '--main'], capture_output=True, text=True)
        self.assertEqual(fallback.returncode, 0, fallback.stderr)
        self.assertTrue(json.loads(fallback.stdout)['scope_fallback'])

    def test_browser_unicode_limit_preserves_codepoints(self):
        report = json.loads(subprocess.run([str(DOCTOR)], capture_output=True, text=True, check=True).stdout)
        if not report['chromium_executable_present']:
            self.skipTest('Playwright Chromium is not available from the current directory')
        url = 'data:text/html;charset=utf-8,' + quote('<p>A😀B</p>')
        short = subprocess.run([str(BROWSER), url, '2'], capture_output=True, text=True)
        self.assertEqual(short.returncode, 1, short.stderr)
        data = json.loads(short.stdout)
        self.assertEqual(data['text'], 'A😀')
        self.assertEqual(data['characters'], 3)
        self.assertTrue(data['truncated'])
        complete = subprocess.run([str(BROWSER), url, '3'], capture_output=True, text=True)
        self.assertEqual(complete.returncode, 0, complete.stderr)
        self.assertEqual(json.loads(complete.stdout)['text'], 'A😀B')

    def test_browser_waits_for_delayed_content_and_reports_timeout(self):
        report = json.loads(subprocess.run([str(DOCTOR)], capture_output=True, text=True, check=True).stdout)
        if not report['chromium_executable_present']:
            self.skipTest('Playwright Chromium is not available from the current directory')
        html = '<p>initial</p><script>setTimeout(() => document.body.insertAdjacentHTML("beforeend", "<p id=ready>later content</p>"), 300)</script>'
        url = 'data:text/html,' + quote(html)
        ready = subprocess.run([str(BROWSER), url, '--wait-for', '#ready', '--timeout-ms', '3000'], capture_output=True, text=True, timeout=15)
        self.assertEqual(ready.returncode, 0, ready.stderr)
        self.assertIn('later content', json.loads(ready.stdout)['text'])
        missing = subprocess.run([str(BROWSER), url, '--wait-for', '#missing', '--timeout-ms', '200'], capture_output=True, text=True, timeout=15)
        self.assertEqual(missing.returncode, 1)
        partial = json.loads(missing.stdout)
        self.assertIn('initial', partial['text'])
        self.assertTrue(partial['partial'])
        self.assertIn('Timeout', partial['wait_error'])

    def test_browser_http_status_redirect_and_dynamic_page(self):
        report = json.loads(subprocess.run([str(DOCTOR)], capture_output=True, text=True, check=True).stdout)
        if not report['chromium_executable_present']:
            self.skipTest('Playwright Chromium is not available from the current directory')

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                if self.path == '/redirect':
                    self.send_response(302)
                    self.send_header('Location', '/page')
                    self.end_headers()
                else:
                    self.send_response(404 if self.path == '/missing' else 200)
                    self.send_header('Content-Type', 'text/html; charset=utf-8')
                    self.end_headers()
                    self.wfile.write(b'<title>Result</title><p>Visible</p><script>document.body.append(" dynamic")</script>')

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f'http://127.0.0.1:{server.server_port}'
            response = subprocess.run([str(BROWSER), base + '/redirect'], capture_output=True, text=True, timeout=20)
            self.assertEqual(response.returncode, 0, response.stderr)
            page = json.loads(response.stdout)
            self.assertEqual(page['url'], base + '/page')
            self.assertEqual(page['status'], 200)
            self.assertIn('dynamic', page['text'])
            response = subprocess.run([str(BROWSER), base + '/missing', '--wait-for', '#absent', '--timeout-ms', '200'], capture_output=True, text=True, timeout=20)
            self.assertEqual(response.returncode, 1)
            self.assertEqual(json.loads(response.stdout)['status'], 404)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

if __name__ == '__main__': unittest.main()
