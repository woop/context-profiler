# Running the Claude Agent SDK in a fully isolated sandbox

## Goal

Run the Python Claude Agent SDK in a way where **nothing from the user's global `~/.claude/` config bleeds into the agent**: no settings, no skills, no plugins, no hooks, no auto-memory, no CLAUDE.md walking up parent directories, no Keychain OAuth token. The agent should only see what we explicitly hand it, and any session state should land in a local folder we control.

## Why you'd want this

- Reproducible runs (CI, headless agents, evals, multi-tenant harnesses).
- Hermetic tests where you don't want the developer's local settings to change behavior.
- Multi-account or multi-profile setups (each profile gets its own `CLAUDE_CONFIG_DIR`).
- Safety: a misbehaving agent can't read or overwrite the user's real config.

## The five knobs

The SDK shells out to the `claude` CLI as a subprocess, so you control isolation through a mix of env vars, SDK options, and CLI flags:

1. **`CLAUDE_CONFIG_DIR`** (env var) — relocates the "home" dir. The CLI normally reads/writes `~/.claude/{settings.json,projects/,plugins/,...}`. Set this and everything moves to your chosen path. Confirmed by inspecting the CLI binary (`strings .../claude | grep CLAUDE_CONFIG_DIR`).
2. **`--bare`** (CLI flag) — disables hooks, LSP, plugin sync, attribution footers, auto-memory, background prefetches, Keychain reads, and CLAUDE.md auto-discovery. Forces auth to `ANTHROPIC_API_KEY` or an `apiKeyHelper` from an explicit `--settings` file. Sets `CLAUDE_CODE_SIMPLE=1`.
3. **`setting_sources=[]`** (SDK option) — whitelist of which scopes to load (`user`, `project`, `local`). Empty list = none.
4. **`strict_mcp_config=True`** (SDK option) — ignore any `.mcp.json` on disk; only use what you pass via `mcp_servers` or `--mcp-config`.
5. **`--append-system-prompt-file`** (CLI flag, passed via `extra_args`) — explicit way to inject *your* CLAUDE.md when auto-discovery is off. (Or use `--add-dir` if you want the CLI to discover CLAUDE.md inside that dir.)

`cwd` and `env` are also passed via `ClaudeAgentOptions`, but those are normal SDK fields.

## Layout

```
scripts/sandboxed-claude/
├── run.py                    # entry point (PEP 723 inline deps; run via `uv run run.py`)
├── workspace/
│   └── CLAUDE.md             # the only context the agent sees
└── sandbox_home/             # plays the role of ~/.claude (settings, sessions, plugins)
```

`api_key.md` lives at the repo root and contains a single Anthropic API key on the first line.

## The script

`scripts/sandboxed-claude/run.py`:

```python
options = ClaudeAgentOptions(
    cwd=str(WORKSPACE),
    env={
        "CLAUDE_CONFIG_DIR": str(SANDBOX_HOME),     # relocate ~/.claude
        "ANTHROPIC_API_KEY": api_key,               # from local api_key.md
        "CLAUDE_CODE_OAUTH_TOKEN": "",              # don't reuse inherited OAuth token
    },
    setting_sources=[],                              # block user/project/local settings.json
    strict_mcp_config=True,                          # ignore .mcp.json
    extra_args={
        "bare": None,                                # no hooks/plugins/keychain/auto-memory/auto CLAUDE.md
        "append-system-prompt-file": str(CLAUDE_MD), # inject our CLAUDE.md explicitly
    },
)

async with ClaudeSDKClient(options=options) as client:
    await client.query("...")
    async for msg in client.receive_response():
        ...
```

## How to verify isolation (the four tests we ran)

Put a unique sentinel in your sandbox CLAUDE.md (we used `PURPLE-OCTOPUS-7421` and a fake role `Quality Assurance Tester`), then ask:

| # | Prompt | Pass criterion |
|---|--------|----------------|
| 1 | "What's your sandbox marker?" | Returns the sentinel — proves our CLAUDE.md *is* loaded |
| 2 | "What is the user's role?" | Returns the sandbox role, *not* anything from the developer's global CLAUDE.md |
| 3 | "What do you know about $real_user_name / $real_company?" | Says "unknown" — proves global `~/.claude/CLAUDE.md` is not loaded |
| 4 | "Quote every CLAUDE.md or memory file you can see" | Returns only the sandbox CLAUDE.md — proves auto-memory and discovery are off |

Then check the filesystem: `find ~/.claude/projects -newermt '2 minutes ago'` should show no new files attributable to the sandbox run, and any session state should appear under `sandbox_home/` instead.

All four passed in our run.

## Gotchas

- **`HOME` is not the right knob.** Overriding `HOME` would also break shell tools the agent invokes (git, ssh, gh). Use `CLAUDE_CONFIG_DIR` only.
- **`setting_sources=[]` does not block CLAUDE.md auto-discovery.** That's a separate mechanism. `--bare` is what disables it. Without `--bare`, the CLI will still walk up from `cwd` collecting `CLAUDE.md` files.
- **Keychain OAuth.** Even with `CLAUDE_CONFIG_DIR` redirected, the CLI normally tries the macOS Keychain for an OAuth token. `--bare` disables that path; auth becomes strictly `ANTHROPIC_API_KEY` or an `apiKeyHelper` from an explicit `--settings` file. We also blank out `CLAUDE_CODE_OAUTH_TOKEN` defensively.
- **Skills.** With `--bare`, skills aren't auto-loaded but still resolve when explicitly invoked via `/skill-name`. If you want zero skills, don't reference them in your prompt.
- **Sessions.** When using `ClaudeSDKClient` (interactive mode), the SDK manages the transcript in memory and may not persist a `.jsonl` file under `sandbox_home/projects/` unless you opt in (e.g., `--resume <uuid>` or use `--print` mode). Either way, nothing leaks to `~/.claude`.
- **MCP.** `strict_mcp_config=True` ignores `.mcp.json` on disk but still allows servers passed via `mcp_servers=` in `ClaudeAgentOptions`. That's the right shape: explicit, not implicit.

## Running it

```bash
uv run scripts/sandboxed-claude/run.py
# or with custom prompts:
uv run scripts/sandboxed-claude/run.py "what's your role?" "list your tools"
```

Inline PEP 723 deps mean no `pyproject.toml` setup; `uv` resolves `claude-agent-sdk` on first run.

## Extending this

- **Multi-profile**: one `CLAUDE_CONFIG_DIR` per profile, swap `cwd` and `CLAUDE.md` per task.
- **CI**: drop the API key into the env from a secret store instead of `api_key.md`. Everything else stays identical.
- **Custom tools**: pass `mcp_servers={...}` (along with `strict_mcp_config=True`) to inject a known set of MCP servers without `.mcp.json` discovery.
- **Custom hooks**: with `--bare`, hooks from `settings.json` don't fire. If you want hooks but no other ambient config, drop `--bare` and instead point `CLAUDE_CONFIG_DIR` at a sandbox dir containing only the `settings.json` you want.


---

for await (const message of query({
  prompt,
  options: {
    cwd: workspace,
    env: {
      ANTHROPIC_API_KEY: apiKey,
      CLAUDE_CODE_OAUTH_TOKEN: "",
      CLAUDE_CONFIG_DIR: sandboxHome,
      CLAUDE_AGENT_SDK_CLIENT_APP: "context-profiler-task-runner/0.1.0",
      HOME: runRoot,
      PATH: process.env.PATH,
    },
    settingSources: [],
    strictMcpConfig: true,
    mcpServers: {},
    tools: ["Read", "Edit", "Bash", "Glob", "Grep"],
    allowedTools: ["Read", "Edit", "Bash", "Glob", "Grep"],
    permissionMode: "dontAsk",
    maxBudgetUsd: 2,
    model: "sonnet",
    systemPrompt: {
      type: "preset",
      preset: "claude_code",
      append:
        "You are running in a clean task harness. Do not use ambient user context. Work only inside the current copied repo workspace.",
    },
    extraArgs: {
      bare: null,
      "disable-slash-commands": null,
    },
    outputFormat: {
      type: "json_schema",
      schema: outputSchema,
    },
  },
})) {
  messages.push(message);
}
---

Above is a task running agent in TS that I created, but lets try Python?
