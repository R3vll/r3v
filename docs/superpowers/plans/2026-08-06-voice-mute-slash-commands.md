# Voice Mute/Unmute Slash Commands — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add user-level Claude Code `/mute` and `/unmute` slash commands that silence and restore the whole voice system (piper TTS output + whisper-live dictation) via a shared mute flag file.

**Architecture:** `C:\Users\admin\.claude\.voice-muted` is the single source of truth (existence = muted). The `/mute` and `/unmute` slash commands each run `voice-mute.py --mute|--unmute`, which sets/clears the flag and, on mute, kills running whisper-live. The two existing hooks (`piper-speak/speak.py`, `whisper-trigger.py`) gain small guards that read the same flag.

**Tech Stack:** Python 3.14 (stdlib only: `argparse`, `subprocess`, `pathlib`, `unittest`), Windows PowerShell (CIM) for the process scan, Claude Code custom slash commands (markdown in `~/.claude/commands/`).

## Global Constraints

- All paths are absolute under `C:\Users\admin\.claude\`.
- Mute flag file: `C:\Users\admin\.claude\.voice-muted` — **existence = muted**. Never committed.
- No audible output from any new code (text output only).
- Idempotent both directions: muting while muted and unmuting while unmuted are safe no-ops.
- Stdlib only — no new pip dependencies.
- Tests use Python's built-in `unittest` (no pytest dependency).
- **`C:\Users\admin\.claude\**` is gitignored by design** (`C:\Users\admin\.gitignore` ignores everything except `docs/`). Implementation files are NOT committed; the only version-controlled artifact is the spec at `docs/superpowers/specs/2026-08-06-voice-mute-slash-commands-design.md` (already committed). Task "checkpoints" verify behavior instead of committing.

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `C:\Users\admin\.claude\voice-mute.py` | Create | Toggle script; `--mute`/`--unmute` CLI |
| `C:\Users\admin\.claude\tests\test_voice_mute.py` | Create | Unit tests for the toggle script |
| `C:\Users\admin\.claude\piper-speak\speak.py` | Modify | Add `is_muted()` helper + early-return guard |
| `C:\Users\admin\.claude\whisper-trigger.py` | Modify | Add mute check in the `*Whisper` branch |
| `C:\Users\admin\.claude\commands\mute.md` | Create | Slash command → runs `voice-mute.py --mute` |
| `C:\Users\admin\.claude\commands\unmute.md` | Create | Slash command → runs `voice-mute.py --unmute` |
| `C:\Users\admin\.claude\settings.local.json` | Modify | Allow rule for the toggle command |

All test/run commands in this plan are Bash (`Git Bash`); they also work in PowerShell with the pipe/`python` form given.

---

### Task 1: `voice-mute.py` toggle script (TDD)

**Files:**
- Create: `C:\Users\admin\.claude\voice-mute.py`
- Create: `C:\Users\admin\.claude\tests\test_voice_mute.py` (parent dir `tests/` is new)

**Interfaces:**
- Consumes: nothing.
- Produces: module `voice_mute` with `is_muted(flag) -> bool`, `set_muted(flag) -> None`, `clear_muted(flag) -> None`, `build_taskkill(pid) -> list[str]`, `build_cmdline_kill_ps() -> list[str]`, `kill_whisper() -> int`, `run(argv) -> int`. Module-level constants `FLAG_FILE` and `PID_FILE` under `Path.home()/".claude"`. Task 4's commands depend on the CLI: `python voice-mute.py --mute` prints `Voice muted.` and exits 0; `--unmute` prints `Voice unmuted.` and exits 0.

- [ ] **Step 1: Write the failing test**

Create `C:\Users\admin\.claude\tests\test_voice_mute.py`:

```python
"""Unit tests for the Claude Code voice mute toggle (voice_mute.py).

Run from anywhere:
    python C:\\Users\\admin\\.claude\\tests\\test_voice_mute.py
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import voice_mute  # noqa: E402


class MuteFlagTests(unittest.TestCase):
    """The flag file is the single source of truth for muted state."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.flag = Path(self._tmp.name) / ".voice-muted"

    def test_flag_absent_means_unmuted(self):
        self.assertFalse(voice_mute.is_muted(self.flag))

    def test_set_muted_creates_flag(self):
        voice_mute.set_muted(self.flag)
        self.assertTrue(self.flag.exists())
        self.assertTrue(voice_mute.is_muted(self.flag))

    def test_clear_muted_removes_flag(self):
        voice_mute.set_muted(self.flag)
        voice_mute.clear_muted(self.flag)
        self.assertFalse(self.flag.exists())
        self.assertFalse(voice_mute.is_muted(self.flag))

    def test_set_muted_is_idempotent(self):
        voice_mute.set_muted(self.flag)
        voice_mute.set_muted(self.flag)  # must not raise
        self.assertTrue(self.flag.exists())

    def test_clear_muted_is_idempotent(self):
        voice_mute.clear_muted(self.flag)  # flag never existed; must not raise
        self.assertFalse(self.flag.exists())


class KillCommandTests(unittest.TestCase):
    """Kill-command construction is pure and system-independent."""

    def test_taskkill_command_shape(self):
        self.assertEqual(
            voice_mute.build_taskkill(7348),
            ["taskkill", "/PID", "7348", "/T", "/F"],
        )

    def test_cmdline_scan_is_powershell_cim(self):
        cmd = voice_mute.build_cmdline_kill_ps()
        self.assertEqual(cmd[:3], ["powershell", "-NoProfile", "-Command"])
        body = cmd[3]
        self.assertIn("whisper-live", body)
        self.assertIn("Stop-Process", body)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python C:\Users\admin\.claude\tests\test_voice_mute.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'voice_mute'` (module does not exist yet).

- [ ] **Step 3: Write minimal implementation**

Create `C:\Users\admin\.claude\voice-mute.py`:

```python
#!/usr/bin/env python3
"""Toggle the Claude Code whole-voice-system mute.

The /mute and /unmute slash commands delegate here. "Muted" is defined as the
existence of the flag file ~/.claude/.voice-muted; the two voice hooks
(piper-speak/speak.py and whisper-trigger.py) consult the same flag so the
state is shared without coupling the hooks to this script.

Usage:
    python voice-mute.py --mute
    python voice-mute.py --unmute

Text output only - never speaks. Idempotent in both directions.
"""

import argparse
import subprocess
import sys
from pathlib import Path

HOOK_ROOT = Path.home() / ".claude"
FLAG_FILE = HOOK_ROOT / ".voice-muted"
PID_FILE = HOOK_ROOT / "whisper-live.pid"


def is_muted(flag: Path = FLAG_FILE) -> bool:
    return flag.exists()


def set_muted(flag: Path = FLAG_FILE) -> None:
    flag.touch(exist_ok=True)


def clear_muted(flag: Path = FLAG_FILE) -> None:
    flag.unlink(missing_ok=True)


def build_taskkill(pid: int) -> list[str]:
    return ["taskkill", "/PID", str(pid), "/T", "/F"]


def build_cmdline_kill_ps() -> list[str]:
    ps = (
        "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
        "Where-Object { $_.CommandLine -match 'whisper-live' } | "
        "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
    )
    return ["powershell", "-NoProfile", "-Command", ps]


def kill_whisper() -> int:
    """Kill running whisper-live dictation; returns number of kill attempts made.

    Reads the pid file whisper-trigger.py writes (may be stale - taskkill on a
    dead pid fails harmlessly), then runs a CIM scan to catch instances launched
    outside the hook (e.g. whisper-live.bat or a !-prefixed command).
    """
    attempts = 0
    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text().strip())
        except ValueError:
            pid = None
        if pid is not None:
            subprocess.run(build_taskkill(pid), capture_output=True, text=True)
            attempts += 1
    subprocess.run(build_cmdline_kill_ps(), capture_output=True, text=True)
    attempts += 1
    return attempts


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Mute or unmute the Claude Code voice system.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--mute", action="store_true",
                       help="silence TTS output and dictation")
    group.add_argument("--unmute", action="store_true",
                       help="restore TTS output and dictation")
    args = parser.parse_args(argv)

    if args.mute:
        set_muted()
        kill_whisper()
        print("Voice muted.")
    else:
        clear_muted()
        print("Voice unmuted.")
    return 0


if __name__ == "__main__":
    sys.exit(run())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python C:\Users\admin\.claude\tests\test_voice_mute.py`
Expected: `OK` (7 tests pass).

- [ ] **Step 5: Smoke-test the CLI, then clean up**

Run:
```bash
python C:/Users/admin/.claude/voice-mute.py --mute
test -f C:/Users/admin/.claude/.voice-muted && echo "flag created"
python C:/Users/admin/.claude/voice-mute.py --unmute
test ! -f C:/Users/admin/.claude/.voice-muted && echo "flag removed"
```
Expected: prints `Voice muted.`, `flag created`, `Voice unmuted.`, `flag removed` (in order). The environment is left **unmuted**.

- [ ] **Step 6: Checkpoint**

Verify `python C:\Users\admin\.claude\tests\test_voice_mute.py` reports `OK` and the flag file does not exist. (No git commit — `~/.claude/**` is gitignored by design.)

---

### Task 2: Mute guard in `speak.py`

**Files:**
- Modify: `C:\Users\admin\.claude\piper-speak\speak.py` — add `MUTE_FLAG` constant and `is_muted()` near the existing `MODEL`/`MAX_CHARS` constants (around line 27), and an early-return in `main()` (line 64).

**Interfaces:**
- Consumes: `voice_mute.FLAG_FILE` path semantics — the guard reads `Path.home()/".claude/.voice-muted"`.
- Produces: `speak.is_muted() -> bool`; `main()` returns `0` immediately (no TTS) when muted.

- [ ] **Step 1: Add the guard**

In `speak.py`, after the `MAX_CHARS = 5000` line (line 27), add:

```python
# Existence of this file = voice system muted. voice-mute.py owns it.
MUTE_FLAG = Path.home() / ".claude" / ".voice-muted"


def is_muted() -> bool:
    return MUTE_FLAG.exists()
```

At the top of `main()`, immediately after the `def main() -> int:` line and before the `try: payload = json.loads(...)` block, add:

```python
    if is_muted():
        return 0
```

(`speak.py` already imports `Path` from `pathlib` — no import change needed.)

- [ ] **Step 2: Verify the guard reads the shared flag**

Run:
```bash
python -c "import sys; sys.path.insert(0, r'C:\Users\admin\.claude\piper-speak'); import speak; from pathlib import Path; f = speak.MUTE_FLAG; assert speak.is_muted() is False; f.touch(); assert speak.is_muted() is True; f.unlink(); assert speak.is_muted() is False; print('speak guard ok')"
```
Expected: prints `speak guard ok`. The `main()` early-return is exercised end-to-end in Task 4 (flag set → no speech).

- [ ] **Step 3: Checkpoint**

Confirm the constant points at `C:\Users\admin\.claude\.voice-muted` and the environment is left **unmuted** (flag removed by the verification step). (No git commit.)

---

### Task 3: Mute guard in `whisper-trigger.py`

**Files:**
- Modify: `C:\Users\admin\.claude\whisper-trigger.py` — add `from pathlib import Path` to the imports and a mute check in the `*Whisper` branch, right after the `if prompt.lower() != "*whisper": sys.exit(0)` line (line 39) and before the launch code.

**Interfaces:**
- Consumes: the flag file path `C:\Users\admin\.claude\.voice-muted` (via existing `HOOK_ROOT` constant).
- Produces: when muted, the hook prints `{"decision": "block", "reason": "Voice is muted - run /unmute to re-enable dictation."}` and returns without launching; all other behavior unchanged.

- [ ] **Step 1: Add the import**

In `whisper-trigger.py`, after the existing `import sys` line, add:

```python
from pathlib import Path
```

- [ ] **Step 2: Add the mute check**

Immediately after the `if prompt.lower() != "*whisper":` / `sys.exit(0)` pair, add:

```python
    if Path(HOOK_ROOT, ".voice-muted").exists():
        print(json.dumps({"decision": "block",
                          "reason": "Voice is muted - run /unmute to re-enable dictation."}))
        return
```

(The existing `json` import is already present.)

- [ ] **Step 3: Verify behavior — muted blocks, unmuted does not**

Run (muted):
```bash
touch C:/Users/admin/.claude/.voice-muted
printf '{"prompt":"*Whisper"}' | python C:/Users/admin/.claude/whisper-trigger.py
```
Expected: prints a block-decision JSON containing `"decision": "block"` and the reason text; **no** `whisper-live.py` process is launched. Verify with `tasklist | grep -i whisper` → no match.

Run (unmuted — only the trigger branch, no launch occurs for a non-trigger prompt):
```bash
rm C:/Users/admin/.claude/.voice-muted
printf '{"prompt":"hello"}' | python C:/Users/admin/.claude/whisper-trigger.py
```
Expected: no output, exit 0.

- [ ] **Step 4: Checkpoint**

Environment left **unmuted** (flag removed). The muted `*Whisper` block is re-verified end-to-end in Task 4. (No git commit.)

---

### Task 4: Slash commands + allow rule + end-to-end

**Files:**
- Create: `C:\Users\admin\.claude\commands\mute.md`
- Create: `C:\Users\admin\.claude\commands\unmute.md`
- Modify: `C:\Users\admin\.claude\settings.local.json` — add one allow rule.

**Interfaces:**
- Consumes: Task 1's CLI (`python voice-mute.py --mute` / `--unmute`).
- Produces: user-level slash commands `/mute` and `/unmute`, prompt-free via the allow rule.

- [ ] **Step 1: Create `mute.md`**

Create `C:\Users\admin\.claude\commands\mute.md`:

```markdown
---
description: Mute the voice system (TTS output + whisper dictation)
allowed-tools:
  - Bash
---

Run the command:

```
python C:\Users\admin\.claude\voice-mute.py --mute
```

Report the printed status to the user in one short line. Do not elaborate.
```

- [ ] **Step 2: Create `unmute.md`**

Create `C:\Users\admin\.claude\commands\unmute.md`:

```markdown
---
description: Unmute the voice system (restore TTS output + whisper dictation)
allowed-tools:
  - Bash
---

Run the command:

```
python C:\Users\admin\.claude\voice-mute.py --unmute
```

Report the printed status to the user in one short line. Do not elaborate.
```

- [ ] **Step 3: Add the allow rule to `settings.local.json`**

Open `C:\Users\admin\.claude\settings.local.json`. In the `permissions.allow` array, add this entry (JSON-escaped backslashes):

```json
"Bash(python C:\\Users\\admin\\.claude\\voice-mute.py *)"
```

The array currently ends with `"Bash(git config *)"` — add a comma after it and append the new entry.

- [ ] **Step 4: Verify JSON is still valid**

Run: `python -c "import json; json.load(open(r'C:\Users\admin\.claude\settings.local.json')); print('settings ok')"`
Expected: prints `settings ok`. Also confirm the commands exist: `ls C:/Users/admin/.claude/commands/` shows `mute.md` and `unmute.md`.

- [ ] **Step 5: End-to-end manual verification** (requires a Claude Code session)

1. In Claude Code, run **`/mute`** → expect reply "Voice muted." and `C:\Users\admin\.claude\.voice-muted` exists.
2. Ask Claude a question → the `Stop` hook stays **silent** (no speech).
3. Type **`*Whisper`** → blocked with "Voice is muted - run /unmute"; dictation does not launch.
4. Run **`/unmute`** → expect reply "Voice unmuted." and the flag file gone.
5. Ask Claude a question → the reply is **spoken** again.
6. Run `/mute`, start a **new Claude Code session**, confirm it is still muted (flag persisted), then `/unmute`.

- [ ] **Step 6: Checkpoint**

All end-to-end steps pass; environment left **unmuted**. (No git commit — the only version-controlled artifact is the spec, already committed.)

---

## Self-Review

- **Spec coverage:** flag file (`~/.claude/.voice-muted`) → Task 1; `voice-mute.py` toggle → Task 1; `speak.py` guard → Task 2; `whisper-trigger.py` guard → Task 3; kill logic (pid file + CIM scan) → Task 1 `kill_whisper()`; allow rule → Task 4 Step 3; slash command files → Task 4 Steps 1–2; no-audible-confirmation → `voice-mute.py` prints text only; idempotency → unit-tested in Task 1; persistence-across-restarts → flag file (Task 4 Step 5.6); voice-echo future hook-point → documented in the spec only, no code (YAGNI). All spec sections covered.
- **Placeholder scan:** every step has concrete code or an exact command; no TBD/TODO.
- **Type consistency:** `is_muted(flag=FLAG_FILE)`, `set_muted`, `clear_muted`, `build_taskkill(pid)`, `build_cmdline_kill_ps`, `kill_whisper`, `run` are defined in Task 1 and used identically in the test file and Task 2/4 references. `speak.is_muted()` is defined in Task 2 and used in its verification. Flag path is `C:\Users\admin\.claude\.voice-muted` everywhere.
