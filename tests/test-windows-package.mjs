#!/usr/bin/env node
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { deflateSync } from 'node:zlib';

const root = join(fileURLToPath(new URL('..', import.meta.url)));
const temp = await mkdtemp(join(tmpdir(), 'agent-tools-windows-'));

function runResult(command, args, cwd) {
  return spawnSync(command, args, { cwd, encoding: 'utf8', windowsHide: true, shell: process.platform === 'win32' });
}

function run(command, args, cwd) {
  const result = runResult(command, args, cwd);
  if (result.error || result.status !== 0) {
    throw new Error(`${command} ${args.join(' ')} failed (${result.status ?? result.error?.message})\nstdout:\n${result.stdout}\nstderr:\n${result.stderr}`);
  }
  return result.stdout;
}

function crc32(buffer) {
  let crc = 0xffffffff;
  for (const byte of buffer) {
    crc ^= byte;
    for (let bit = 0; bit < 8; bit++) crc = (crc >>> 1) ^ (crc & 1 ? 0xedb88320 : 0);
  }
  return (crc ^ 0xffffffff) >>> 0;
}

function chunk(type, data) {
  const name = Buffer.from(type);
  const body = Buffer.concat([name, data]);
  const header = Buffer.alloc(4);
  header.writeUInt32BE(data.length);
  const checksum = Buffer.alloc(4);
  checksum.writeUInt32BE(crc32(body));
  return Buffer.concat([header, body, checksum]);
}

function onePixelPNG() {
  const header = Buffer.alloc(13);
  header.writeUInt32BE(1, 0);
  header.writeUInt32BE(1, 4);
  header[8] = 8;
  header[9] = 6;
  return Buffer.concat([
    Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]),
    chunk('IHDR', header),
    chunk('IDAT', deflateSync(Buffer.from([0, 255, 0, 0, 255]))),
    chunk('IEND', Buffer.alloc(0)),
  ]);
}

function textPDF(text) {
  const content = `BT /F1 12 Tf 20 180 Td (${text}) Tj ET`;
  const objects = [
    '<< /Type /Catalog /Pages 2 0 R >>',
    '<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
    '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
    '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
    `<< /Length ${Buffer.byteLength(content)} >>\nstream\n${content}\nendstream`,
  ];
  let body = '%PDF-1.4\n';
  const offsets = [];
  objects.forEach((object, index) => {
    offsets.push(Buffer.byteLength(body));
    body += `${index + 1} 0 obj\n${object}\nendobj\n`;
  });
  const xref = Buffer.byteLength(body);
  body += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`;
  body += offsets.map((offset) => `${String(offset).padStart(10, '0')} 00000 n \n`).join('');
  body += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
  return body;
}

try {
  const packed = JSON.parse(run('npm', ['pack', '--json', '--pack-destination', temp], root))[0];
  const tarball = join(temp, packed.filename);
  const prefix = join(temp, 'install');
  run('npm', ['install', '--prefix', prefix, '--ignore-scripts', '--no-audit', '--no-fund', '--no-save', '--package-lock=false', tarball], temp);
  const cli = join(prefix, 'node_modules', 'agent-efficiency-tools', 'bin', 'agent-tools');
  const shim = join(prefix, 'node_modules', '.bin', process.platform === 'win32' ? 'agent-tools.cmd' : 'agent-tools');
  assert.match(run(process.execPath, [cli, '--version'], temp), /agent-efficiency-tools 0\.1\.9/);
  assert.match(run(shim, ['--version'], temp), /agent-efficiency-tools 0\.1\.9/, 'installed npm command shim did not invoke the CLI');
  const nativeOS = { win32: 'windows', darwin: 'darwin', linux: 'linux' }[process.platform];
  const nativeArch = { x64: 'amd64', arm64: 'arm64' }[process.arch];
  const nativeName = `agent-tools-native${process.platform === 'win32' ? '.exe' : ''}`;
  const nativeBinary = join(prefix, 'node_modules', 'agent-efficiency-tools', 'bin', 'native', `${nativeOS}-${nativeArch}`, nativeName);
  assert.match(run(nativeBinary, ['--version'], temp), /agent-tools-native v0\.1\.9/);
  const doctor = JSON.parse(run(process.execPath, [cli, 'doctor'], temp));
  assert.equal(doctor.native_binary_available, true, 'doctor did not detect the packaged Windows binary');

  const source = join(temp, 'input.png');
  const output = join(temp, 'small.png');
  const original = onePixelPNG();
  await writeFile(source, original);
  run(process.execPath, [cli, 'image-prepare', source, output, '1'], temp);
  assert.deepEqual(await readFile(source), original, 'image preparation changed the original');
  assert.ok((await readFile(output)).length > 0, 'image preparation did not create its output');

  const pdf = join(temp, 'report.pdf');
  await writeFile(pdf, textPDF('WINDOWS PACKAGE PDF TEST'));
  const extracted = run(process.execPath, [cli, 'pdf-text', pdf, '1'], temp);
  assert.match(extracted, /WINDOWS PACKAGE PDF TEST/);

  const log = join(temp, 'build.log');
  await writeFile(log, 'start\nERROR: Windows smoke fixture\n  at sample.js:2\n');
  const scan = runResult(process.execPath, [cli, 'log-scan', log], temp);
  assert.equal(scan.status, 1, `log-scan returned ${scan.status}: ${scan.stderr}`);
  const scanned = JSON.parse(scan.stdout);
  assert.equal(scanned.match_count, 1, 'Python command dispatch failed on Windows');
  const capturePath = join(temp, 'captured.log');
  const capture = run(process.execPath, [cli, 'output-capture', '--output', capturePath, '--', process.execPath, '-e', 'console.log("Windows command capture")'], temp);
  assert.match(capture, /Windows command capture/);
  assert.match(await readFile(capturePath, 'utf8'), /Windows command capture/);

  const timeout = runResult(process.execPath, [cli, 'output-capture', '--output', join(temp, 'timeout.log'), '--timeout', '0.2', '--', process.execPath, '-e', 'setTimeout(() => {}, 5000)'], temp);
  assert.equal(timeout.status, 124, `Windows timeout returned ${timeout.status}: ${timeout.stderr}`);
  process.stdout.write('Windows npm package smoke passed: npm install and shim, doctor, native image/PDF commands, Python log scan, output capture, and timeout.\n');
} finally {
  await rm(temp, { recursive: true, force: true });
}
