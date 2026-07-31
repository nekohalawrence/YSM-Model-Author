---
name: aionui-config
description: >-
  Configure AionUi itself through the bundled aioncore config CLI: create and edit assistants, update assistant rules, inspect and import skills, manage MCP servers, configure model providers, update settings, manage agents, configure scheduled tasks, and manage app configuration from an agent conversation. Use when the user wants you to set up or modify an AionUi assistant, attach skills, change an assistant's system prompt, add MCP or model provider configuration, schedule recurring work, or otherwise configure their AionUi installation, including when the user needs to know whether assistant changes affect the current conversation or only new conversations.
---

# AionUi Config

Configure AionUi with the bundled agent-facing CLI. Do not discover ports, do
not call raw backend paths, and do not depend on tools outside the bundled
`aioncore` binary.

## Rules

1. Use only `"$AIONUI_HELPER_BIN" config ...`.
2. Never pass, inline, export, echo, or set any `AIONUI_...` environment variable.
3. Put all command input in stdin JSON.
4. Do not use flags for business fields.
5. Use `"$AIONUI_HELPER_BIN" config capabilities` when unsure which config command or stdin fields are supported.
6. Read context before changing the current assistant.
7. Read before writing, then read back after writing.
8. Use `"assistant_id": "current"` when the user asks to change the assistant used by this conversation.
9. Use `"conversation_id": "current"` when a command accepts a conversation selector.
10. Do not show internal ids unless the user needs them for a follow-up operation.
11. Never reveal provider keys, MCP headers, environment values, or other secrets.
12. If the CLI fails, report the stable `CONFIG_...` error from stderr in normal prose and do not claim the change was made.
13. After assistant changes, explain both persistence and effect timing. Saving and read-back do not mean the current running conversation has reloaded the changed runtime behavior.

## Output

Successful commands print a JSON envelope:

```json
{
  "success": true,
  "data": {},
  "meta": {
    "schema_version": 1
  }
}
```

Failures print one stable error line to stderr. Treat stderr as authoritative.

## Capability Discovery

Ask aioncore what this version supports:

```bash
"$AIONUI_HELPER_BIN" config capabilities
```

The result is a JSON envelope whose `data.domains[].commands[]` entries list
supported command paths, input mode, expected stdin fields, selector fields,
read-back behavior, destructive behavior, context requirements, and fields
redacted from ordinary output.

## Context

Read the current user, conversation, assistant, and local runtime context:

```bash
"$AIONUI_HELPER_BIN" config context
```

If `data.assistant` is `null`, the current conversation is not backed by an
assistant. Ask the user which assistant to edit before changing assistant
rules or defaults.

## Assistant Change Timing

AionUi persists assistant configuration immediately, but running conversations
may keep the assistant snapshot created when the conversation started. Use this
timing model when reporting successful assistant changes:

- Identity fields such as name, description, avatar, and recommended prompts are
  saved immediately. If the open UI still shows old values, tell the user to
  refresh or reopen the assistant view.
- Runtime fields such as agent, default model, default permission, default
  skills, default MCPs, thought level, and rules apply to new conversations
  created from that assistant. Do not claim they change the current running
  conversation.
- Skills and MCP defaults are not retroactively injected into the current agent
  runtime. If a tool is already available in the current conversation, it can be
  used; otherwise the user should start a new conversation with the assistant.

When reporting a successful runtime-field change, say that the change was saved
and read back, then state that it will affect new conversations only.

## Assistants

List assistants:

```bash
"$AIONUI_HELPER_BIN" config assistants list
```

Inspect the current assistant:

```bash
"$AIONUI_HELPER_BIN" config assistants get <<'JSON'
{
  "assistant_id": "current",
  "locale": "en-US"
}
JSON
```

Examples use English sample text and `en-US`. For real localized assistant
content, use the user's actual locale.

Create an assistant:

```bash
"$AIONUI_HELPER_BIN" config assistants create <<'JSON'
{
  "name": "Requirements Analyst",
  "description": "Turn rough product ideas into clear PRDs",
  "agent_id": "2d23ff1c",
  "prompts": [
    "Turn this feature idea into a PRD",
    "Review this PRD and identify confusing parts for new users"
  ],
  "enabled_skills": ["aionui-config"]
}
JSON
```

Update assistant metadata or defaults:

```bash
"$AIONUI_HELPER_BIN" config assistants update <<'JSON'
{
  "assistant_id": "current",
  "locale": "en-US",
  "description": "Updated assistant description",
  "defaults": {
    "permission": {
      "mode": "fixed",
      "value": "plan"
    }
  }
}
JSON
```

For `name`, `description`, `avatar`, or recommended prompt changes, report that
the change is saved and may require refreshing or reopening the UI to see. For
`agent_id`, `defaults`, `enabled_skills`, or other runtime defaults (MCP
defaults are set via `defaults.mcps`, not `default_mcp_ids`), report that the
saved change applies to new conversations only.

Enable, disable, or reorder an assistant:

```bash
"$AIONUI_HELPER_BIN" config assistants state <<'JSON'
{
  "assistant_id": "current",
  "enabled": true,
  "sort_order": 10
}
JSON
```

## Assistant Rules

Assistant rules are the system prompt that defines assistant behavior.

Read the current assistant rule:

```bash
"$AIONUI_HELPER_BIN" config assistants rule read <<'JSON'
{
  "assistant_id": "current",
  "locale": "en-US"
}
JSON
```

Write the current assistant rule:

```bash
"$AIONUI_HELPER_BIN" config assistants rule write <<'JSON'
{
  "assistant_id": "current",
  "locale": "en-US",
  "content": "# Role\nYou are..."
}
JSON
```

For rule edits, preserve the user's existing useful instructions unless the
user explicitly asks to replace them.

After a successful rule write or delete, always tell the user that the rule was
saved and read back, but it applies only to new conversations created from this
assistant. The current conversation continues using the rule snapshot it started
with.

## Skills

List available skills:

```bash
"$AIONUI_HELPER_BIN" config skills list
```

Inspect a skill directory before importing:

```bash
"$AIONUI_HELPER_BIN" config skills info <<'JSON'
{
  "skill_path": "/absolute/path/to/skill"
}
JSON
```

Import a skill:

```bash
"$AIONUI_HELPER_BIN" config skills import <<'JSON'
{
  "skill_path": "/absolute/path/to/skill-or-parent-or-zip"
}
JSON
```

Attach skills to an assistant by updating the assistant's full skill list:

```bash
"$AIONUI_HELPER_BIN" config assistants update <<'JSON'
{
  "assistant_id": "current",
  "enabled_skills": ["aionui-config", "cron"]
}
JSON
```

Do not append blindly. Read the assistant first, merge the list locally, then
send the full intended `enabled_skills` value.

Enabled skills are assistant defaults for new conversations. Do not tell the
user that newly attached skills are available in the current conversation unless
the current runtime already exposes them.

Manage external skill paths:

```bash
"$AIONUI_HELPER_BIN" config skills external-paths list
```

```bash
"$AIONUI_HELPER_BIN" config skills external-paths add <<'JSON'
{
  "name": "Team Skills",
  "path": "/absolute/path/to/team-skills"
}
JSON
```

```bash
"$AIONUI_HELPER_BIN" config skills external-paths remove <<'JSON'
{
  "path": "/absolute/path/to/team-skills"
}
JSON
```

Enable or disable the skills market:

```bash
"$AIONUI_HELPER_BIN" config skills market enable
```

```bash
"$AIONUI_HELPER_BIN" config skills market disable
```

## MCP Servers

List MCP servers:

```bash
"$AIONUI_HELPER_BIN" config mcp servers list
```

Create an MCP server:

```bash
"$AIONUI_HELPER_BIN" config mcp servers create <<'JSON'
{
  "name": "Local Tools",
  "transport": {
    "type": "stdio",
    "command": "my-mcp-server",
    "args": [],
    "env": {}
  }
}
JSON
```

Update an MCP server:

```bash
"$AIONUI_HELPER_BIN" config mcp servers update <<'JSON'
{
  "server_id": "mcp_123",
  "description": "Updated description"
}
JSON
```

Test a server configuration:

```bash
"$AIONUI_HELPER_BIN" config mcp test-connection <<'JSON'
{
  "name": "Local Tools",
  "transport": {
    "type": "stdio",
    "command": "my-mcp-server",
    "args": []
  }
}
JSON
```

OAuth helpers:

```bash
"$AIONUI_HELPER_BIN" config mcp oauth check-status <<'JSON'
{
  "server_url": "https://mcp.example.com"
}
JSON
```

Never show MCP headers or stdio env values to the user. CLI output redacts
sensitive fields by default.

## Providers

List model providers:

```bash
"$AIONUI_HELPER_BIN" config providers list
```

Create a provider:

```bash
"$AIONUI_HELPER_BIN" config providers create <<'JSON'
{
  "name": "OpenAI",
  "platform": "openai",
  "base_url": "https://api.openai.com/v1",
  "api_key": "sk-..."
}
JSON
```

Update a provider:

```bash
"$AIONUI_HELPER_BIN" config providers update <<'JSON'
{
  "provider_id": "provider_123",
  "api_key": "sk-..."
}
JSON
```

Detect protocol, fetch models, or run a provider health check:

```bash
"$AIONUI_HELPER_BIN" config providers detect-protocol <<'JSON'
{
  "base_url": "https://api.example.com/v1",
  "api_key": "..."
}
JSON
```

```bash
"$AIONUI_HELPER_BIN" config providers models fetch <<'JSON'
{
  "provider_id": "provider_123"
}
JSON
```

```bash
"$AIONUI_HELPER_BIN" config providers health-check <<'JSON'
{
  "provider_id": "provider_123",
  "model": "gpt-4.1"
}
JSON
```

Never reveal provider keys. Do not repeat secret values from the user's input.

## Settings

Read backend settings:

```bash
"$AIONUI_HELPER_BIN" config settings get
```

Patch backend settings:

```bash
"$AIONUI_HELPER_BIN" config settings patch <<'JSON'
{
  "language": "en-US",
  "notification_enabled": true
}
JSON
```

Supported patch fields: `language`, `notification_enabled`, `cron_notification_enabled`,
`command_queue_enabled`, `save_upload_to_workspace`. Unknown fields are silently ignored.

Read or update client preferences:

```bash
"$AIONUI_HELPER_BIN" config settings client get
```

```bash
"$AIONUI_HELPER_BIN" config settings client put <<'JSON'
{
  "ui.zoomFactor": 1.2
}
JSON
```

Client preferences are a free-form key-value map. Pass `null` to remove a key. Ask the
user or read back first to discover keys in use — there is no fixed schema.

## Agents

List available agents:

```bash
"$AIONUI_HELPER_BIN" config agents list
```

Enable or disable an agent:

```bash
"$AIONUI_HELPER_BIN" config agents enable <<'JSON'
{
  "agent_id": "codex",
  "enabled": true
}
JSON
```

Read or set per-agent overrides:

```bash
"$AIONUI_HELPER_BIN" config agents overrides get <<'JSON'
{
  "agent_id": "codex"
}
JSON
```

```bash
"$AIONUI_HELPER_BIN" config agents overrides set <<'JSON'
{
  "agent_id": "codex",
  "command_override": "/absolute/path/to/codex"
}
JSON
```

Create, update, delete, or try-connect a custom agent:

```bash
"$AIONUI_HELPER_BIN" config agents custom create <<'JSON'
{
  "name": "Custom Agent",
  "command": "/absolute/path/to/agent-cli"
}
JSON
```

```bash
"$AIONUI_HELPER_BIN" config agents custom update <<'JSON'
{
  "agent_id": "custom_agent_123",
  "name": "Custom Agent",
  "command": "/absolute/path/to/agent-cli"
}
JSON
```

Test whether a custom agent binary is reachable (does not persist anything):

```bash
"$AIONUI_HELPER_BIN" config agents custom try-connect <<'JSON'
{
  "command": "/absolute/path/to/agent-cli"
}
JSON
```

Do not reveal agent env values or secret override values.

## Scheduled Tasks

For tasks tied to the current conversation, use the cron current commands.

List current conversation tasks:

```bash
"$AIONUI_HELPER_BIN" config cron current list
```

Create a task:

```bash
"$AIONUI_HELPER_BIN" config cron current create <<'JSON'
{
  "name": "Daily Summary",
  "schedule": "0 18 * * MON-FRI",
  "schedule_description": "Weekdays at 6:00 PM",
  "message": "Review the conversation context and produce a concise end-of-day summary."
}
JSON
```

Update a task:

```bash
"$AIONUI_HELPER_BIN" config cron current update <<'JSON'
{
  "job_id": "cron_123",
  "name": "Daily Summary",
  "schedule": "0 18 * * MON-FRI",
  "schedule_description": "Weekdays at 6:00 PM",
  "message": "Review the conversation context and produce a concise end-of-day summary."
}
JSON
```

After a successful create or update, explain the task name and schedule in
normal user-facing language. Do not show `cron_...` ids unless needed.

For global cron job administration, use `config cron jobs`.

List all cron jobs:

```bash
"$AIONUI_HELPER_BIN" config cron jobs list
```

Create a cron job:

```bash
"$AIONUI_HELPER_BIN" config cron jobs create <<'JSON'
{
  "name": "Weekly Report",
  "schedule": { "kind": "cron", "expr": "0 9 * * MON", "tz": "Asia/Shanghai" },
  "message": "Produce the weekly report.",
  "conversation_id": "current",
  "created_by": "user"
}
JSON
```

The `schedule` field is a tagged object, not a flat string:
- `{ "kind": "cron", "expr": "<cron-expr>", "tz": "<IANA-tz>" }` — recurring cron schedule
- `{ "kind": "every", "every_ms": <milliseconds> }` — fixed interval
- `{ "kind": "at", "at_ms": <epoch-ms> }` — one-shot at a specific time

`conversation_id` and `created_by` are required. `message` carries the task text.
Use `"conversation_id": "current"` to attach the job to the current conversation.

Update, run, or manage a cron job skill:

Note: `cron jobs` uses the tagged `schedule` object (same shape as create). This
is different from `cron current`, where `schedule` is a flat cron string.

```bash
"$AIONUI_HELPER_BIN" config cron jobs update <<'JSON'
{
  "job_id": "cron_123",
  "name": "Weekly Report",
  "schedule": { "kind": "cron", "expr": "0 10 * * MON" }
}
JSON
```

```bash
"$AIONUI_HELPER_BIN" config cron jobs run <<'JSON'
{
  "job_id": "cron_123"
}
JSON
```

```bash
"$AIONUI_HELPER_BIN" config cron jobs skill save <<'JSON'
{
  "job_id": "cron_123",
  "content": "# Skill\nTask-specific instructions."
}
JSON
```

## Safety

Configuration changes affect the user's live app. Keep changes narrow, show
what changed in plain language, and avoid exposing raw JSON unless the user
asks for implementation detail.
