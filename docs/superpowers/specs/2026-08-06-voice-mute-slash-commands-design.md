# Voice Mute/Unmute Slash Commands

- **Date:** 2026-08-06
- **Status:** Design approved

## Summary

Two user-level Claude Code slash commands, **`/mute`** and **`/unmute`**, that
silence and restore the whole voice system: piper TTS output (Claude's replies
read aloud) and whisper-live dictation input.

- **`/mute`** → TTS stops reading replies, any running whisper-live dictation is
  killed, and new `*Whisper` launches are blocked.
- **`/unmute`** → restores all of it.

## Background / context

The user's voice setup in `~/.claude/settings.json`:

- **Output:** a `Stop` hook runs `~/.claude/piper-speak/speak.py`, which reads
  the last assistant message from the session transcript and speaks it aloud
  via piper TTS.
- **Input:** a `UserPromptSubmit` hook runs `~/.claude/whisper-trigger.py`. A
  prompt of exactly `*Whisper` launches `~/.claude/whisper-live.py` live
  dictation in its own console window, recording the PID to
  `~/.claude/whisper-live.pid`.
- `~/.claude/voice-echo.py` (keyword spotter, "hey computer listen/stop") is a
  separate design spec and is **not yet implemented**.

## Goals

- `/mute` silences the entire voice system: output stops, running dictation is
  killed, future launches are blocked.
- `/unmute` restores everything with no other side effects.
- Mute state **persists across Claude Code restarts** until explicitly unmuted.
- **No audible confirmation** — confirmation is text-only, relayed in Claude's
  reply.
- Idempotent in both directions (muting while muted and unmuting while unmuted
  are no-ops that still report success).

## Non-goals (YAGNI)

- No spoken "Muted" / "Unmuted" cue.
- No single toggle command — the pair `/mute` + `/unmute` is explicit.
- No control over `voice-echo.py` today (it does not exist yet); the mute flag
  is simply designated as the canonical signal it will honor when implemented.
- No GUI / tray icon.

## Architecture

One source of truth: the **mute flag file** `~/.claude/.voice-muted`.
**Existence of the file = muted.** Both hooks consult the flag; a small toggle
script sets/clears it and kills running whisper-live.

```
                        ┌─ exists? ─► speak.py exits 0 (no TTS)
~/.claude/.voice-muted ─┤
                        └─ exists? ─► whisper-trigger.py blocks *Whisper
                                     ("Voice is muted — run /unmute")

/mute   ─► voice-mute.py --mute   ─► create flag + kill whisper-live
/unmute ─► voice-mute.py --unmute ─► remove flag
```

## Components

| File | Type | Purpose |
|---|---|---|
| `~/.claude/.voice-muted` | flag file (new) | Empty file; existence = muted. Never committed. |
| `~/.claude/voice-mute.py` | script (new) | `--mute` / `--unmute` toggle. Text output only. Idempotent. |
| `~/.claude/commands/mute.md` | slash command (new) | Runs `voice-mute.py --mute`; replies "Voice muted." |
| `~/.claude/commands/unmute.md` | slash command (new) | Runs `voice-mute.py --unmute`; replies "Voice unmuted." |
| `~/.claude/piper-speak/speak.py` | hook (modified) | New guard: return 0 silently when muted. |
| `~/.claude/whisper-trigger.py` | hook (modified) | New guard: block `*Whisper` when muted. |
| `~/.claude/settings.local.json` | config (modified) | Allow rule for the toggle command so it runs without a prompt. |

The `commands/` directory is created at the **user level**, so `/mute` and
`/unmute` work in every project, matching the user-level hooks.

## Behavior details

### `voice-mute.py --mute`

1. Create `~/.claude/.voice-muted` (no-op if it already exists).
2. Kill running whisper-live:
   - Read `~/.claude/whisper-live.pid`; if the PID is alive, run
     `taskkill /PID <pid> /T /F`.
   - Additionally scan for any `python.exe` whose command line contains
     `whisper-live.py` (via CIM/PowerShell) and kill it — catches instances
     launched outside the hook (e.g. the `.bat` or a `!`-prefixed command).
   - Missing or stale pid file → skip silently.
3. Print `Voice muted.` and exit 0.

### `voice-mute.py --unmute`

1. Delete `~/.claude/.voice-muted` if present.
2. Print `Voice unmuted.` and exit 0.

The script never speaks; it only prints status text that Claude relays.

### Guard in `speak.py`

At the top of `main()`, before reading stdin: if
`~/.claude/.voice-muted` exists → `return 0`. The `Stop` hook therefore stays
registered but is a silent no-op while muted.

### Guard in `whisper-trigger.py`

In the `*Whisper` branch, before launching: if the flag exists → return
`{"decision": "block", "reason": "Voice is muted — run /unmute"}` so the
trigger text is never sent to Claude and dictation is not launched.

### Allow rule

Add to `permissions.allow` in `~/.claude/settings.local.json`:

```
Bash(python C:\Users\admin\.claude\voice-mute.py *)
```

so `/mute` and `/unmute` run without a permission prompt.

### Slash command files

`mute.md` / `unmute.md` frontmatter: `description` + `allowed-tools: Bash`.
Body: instruct Claude to run the toggle script with the matching argument and
reply with the printed status. No arguments.

## Flow

- **`/mute`**: flag created + whisper killed → Claude replies "Voice muted." →
  the `Stop` hook fires at the end of the turn → `speak.py` sees the flag →
  silent. No race: the flag is set during the tool call, before Claude's reply.
- **`/unmute`**: flag removed → Claude replies "Voice unmuted." → the `Stop`
  hook reads the reply aloud (normal TTS restored).
- **`*Whisper`** while muted → blocked with the text note; nothing launched.
- **Restart**: the flag file persists, so mute survives restarts until `/unmute`.

## Edge cases

- **Stale pid file** → kill step skips; the CIM scan still catches live
  whisper-live processes by command line.
- **Manually launched whisper-live** (not via `*Whisper`) → caught by the CIM
  scan; if it somehow escapes, only future `*Whisper` launches are blocked.
- **Idempotency** → both directions are safe to run repeatedly.
- **No audible feedback** → the toggle script prints text only; no piper synth.
- **Future voice-echo** → `voice-echo.py`, when implemented, should check the
  same `~/.claude/.voice-muted` flag (suppress TTS echo and disable dictation
  activation). Documented here as the canonical signal; not implemented now.

## Verification

1. `python C:\Users\admin\.claude\voice-mute.py --mute` → flag file exists;
   no whisper-live process in tasklist.
2. Type `*Whisper` → blocked with "Voice is muted — run /unmute".
3. Ask Claude a question → the `Stop` hook stays silent (no speech).
4. `python C:\Users\admin\.claude\voice-mute.py --unmute` → flag gone.
5. Ask Claude a question → the reply is spoken again.
6. `*Whisper` → dictation launches again.
7. Run `/mute`, then in a new Claude Code session confirm it is still muted;
   run `/unmute` to restore.
8. Run each command twice consecutively to confirm idempotency.

## Out of scope / future

- `voice-echo.py` integration (honor the mute flag) once that program exists.
- An audible "Muted"/"Unmuted" cue if ever desired.
- A single toggle command.
