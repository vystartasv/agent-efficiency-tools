# Publishing

The `ci.yml` workflow tests the npm package on macOS and Linux, and tests/builds the native CLI on Windows, Linux, and macOS. A matching `vX.Y.Z` tag publishes the npm package and attaches six native binary archives to a GitHub release after all test jobs pass.

## One-time npm setup

Configure npm trusted publishing for `agent-efficiency-tools`:

- Provider: GitHub Actions
- Owner: `vystartasv`
- Repository: `agent-efficiency-tools`
- Workflow filename: `ci.yml`
- Allow direct `npm publish`

npm requires account-level two-factor authentication for trusted-publisher setup. The publisher uses GitHub OIDC and does not need a long-lived npm token. Since the repository and package are public, npm creates provenance automatically.

After adding the trusted publisher, its first successful release must complete within two days or npm expires that configuration.

The equivalent npm CLI command is:

```sh
npm trust github agent-efficiency-tools \
  --file ci.yml \
  --repo vystartasv/agent-efficiency-tools \
  --allow-publish
```

## Standalone native binaries

Every version tag also builds standalone binaries for Windows, Linux, and macOS. The native build/test job runs on all three operating systems; release archives are attached to the GitHub release. They are separate from the npm package and require Tesseract only for OCR commands. See [native/README.md](native/README.md).

## Release

1. Update `package.json` and `package-lock.json` to the next version and commit the release.
2. Push the commit to GitHub.
3. Create and push the matching tag, for example `git tag v0.1.3 && git push origin v0.1.3`.
4. Confirm the `Tests` workflow passes both platforms and the `publish` job succeeds. If the tag push does not start a run, manually dispatch `ci.yml` with the tag as its ref (for example, `gh workflow run ci.yml --ref v0.1.3`). The publish job only runs for a version tag and still waits for both test jobs.

The workflow rejects a tag that does not exactly match the package version. Do not reuse a published npm version.

See [npm trusted publishers](https://docs.npmjs.com/trusted-publishers/) and [npm staged publishing](https://docs.npmjs.com/staged-publishing/).
