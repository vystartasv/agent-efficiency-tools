#!/usr/bin/env node
import { mkdir, readFile } from 'node:fs/promises';
import { spawnSync } from 'node:child_process';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const nativeRoot = join(root, 'native');
const version = JSON.parse(await readFile(join(root, 'package.json'), 'utf8')).version;
const targets = [
  ['darwin', 'arm64'], ['darwin', 'amd64'],
  ['linux', 'arm64'], ['linux', 'amd64'],
  ['windows', 'arm64'], ['windows', 'amd64'],
];

for (const [goos, goarch] of targets) {
  const directory = join(root, 'bin', 'native', `${goos}-${goarch}`);
  const binary = join(directory, `agent-tools-native${goos === 'windows' ? '.exe' : ''}`);
  await mkdir(directory, { recursive: true });
  const result = spawnSync('go', [
    'build', '-trimpath', '-ldflags', `-s -w -X main.version=v${version}`,
    '-o', binary, '.',
  ], { cwd: nativeRoot, env: { ...process.env, GOOS: goos, GOARCH: goarch, CGO_ENABLED: '0' }, stdio: 'inherit' });
  if (result.error) throw result.error;
  if (result.status !== 0) process.exit(result.status ?? 1);
  process.stderr.write(`Built ${goos}-${goarch} native tools.\n`);
}
