# Agent integration

Use the shared `skills/agent-tools/SKILL.md` with the `agent-tools` command on the agent's execution-environment PATH. A skill provides instructions; it does not install the CLI or its optional dependencies, and a local installation is not automatically available in a remote container.

## Codex

Codex reads user skills from `~/.agents/skills` and repository skills from `.agents/skills`. See the [OpenAI skill locations](https://learn.chatgpt.com/docs/build-skills). Install or link the reviewed skill into the appropriate directory and confirm it appears in a new session.

## Claude Code

Claude Code reads personal skills from `~/.claude/skills/<name>/SKILL.md` and project skills from `.claude/skills`. A separate profile may use a different configuration directory. See [Claude Code skills](https://code.claude.com/docs/en/skills) and [`CLAUDE_CONFIG_DIR`](https://code.claude.com/docs/en/env-vars). Local personal skills and this machine's CLI are not automatically available to cloud or Cowork sessions; those require their own installation and enabled skill.

## Hermes Agent

Hermes uses `~/.hermes/skills` and can additionally scan configured external skill directories. See [Hermes skills](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills). Install the single reviewed skill into the active profile and verify it with `hermes skills list`; check the execution backend separately. A copied skill needs explicit updates. A shared writable link can expose the checkout to modification by tools that edit installed skills.

## Verify

- Validate the installed skill and run `agent-tools doctor` in each agent's execution environment. Browser and image-diff dependencies are installed with the toolkit; browser reading also needs a Chromium installation.
- Confirm the agent actually discovers and can invoke the skill. A file or symlink alone is not proof of runtime discovery. Use generated fixtures rather than private content for model-backed tests.
- Keep platform-specific commands and OCR/transcription dependencies optional. Skill discovery does not require an automatic hook, model download, permission grant, or credential change.
