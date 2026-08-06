# Voice Echo: Keyword-Triggered STT/TTS Echo — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An always-on local Windows program that listens for "hey computer listen" / "hey computer stop" (sherpa-onnx keyword spotter), starts/stops live dictation (faster-whisper), and echoes each transcribed line aloud (piper TTS).

**Architecture:** One `sounddevice.InputStream` feeds two queues — a spotter thread (always armed, drives an `IDLE`/`ACTIVE` state machine, speaks "Listening"/"Stopped" cues) and the whisper VAD/ring-buffer pipeline (runs only while `ACTIVE`, echoes via piper). The `/mute` flag `~/.claude/.voice-muted` suppresses all speech and blocks activation.

**Tech Stack:** Python 3.14, sherpa-onnx 1.13.4 (cp314 wheel), piper-tts 1.6.0 (already installed, voice reused), faster-whisper + silero-vad + sounddevice + numpy (already installed). Tests use stdlib `unittest`.

## Global Constraints

- All paths are absolute. Program: `C:\Users\admin\voice-echo.py`; support files under `C:\Users\admin\voice-echo\`; model under `C:\Users\admin\models\sherpa-kws\`.
- Keyword model: `sherpa-onnx-kws-zipformer-gigaspeech-3.3M-2024-01-01` (English only). Download URL is pinned in Task 1.
- Piper voice: **reuse** `C:\Users\admin\.claude\piper-models\en_US-lessac-medium.onnx` — do **not** download a second copy.
- Mute flag: `C:\Users\admin\.claude\.voice-muted` — **existence = muted**. While present: no speech of any kind (cues or echo) and "hey computer listen" must NOT activate dictation. Mute set mid-dictation → halt immediately, drop queued segments, spotter stays armed.
- No new pip dependencies beyond `sherpa-onnx` (everything else is already installed).
- English trigger phrases only in v1. Score `:3.0` and threshold `#0.25` per keyword (tunable later).
- Tests use stdlib `unittest`, runnable without the model or a microphone.
- `C:\Users\admin\voice-echo.py`, `C:\Users\admin\voice-echo\*`, and `C:\Users\admin\models\*` are gitignored by design; only `docs/superpowers/` is committed. Checkpoints verify behavior instead of committing.
- All test/run commands are Bash (`Git Bash`); PowerShell equivalents work too.

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `C:\Users\admin\voice-echo\download_model.py` | Create (T1) | Download + extract the gigaspeech KWS model (stdlib only) |
| `C:\Users\admin\voice-echo\verify_offline.py` | Create (T1) | Load the spotter with a keywords file, run it over the model's bundled `test_wavs/` (stdlib `wave`) |
| `C:\Users\admin\voice-echo\keywords.raw.txt` | Create (T2) | Human-readable keywords source: `hey computer listen :3.0 #0.25` etc. |
| `C:\Users\admin\voice-echo\keywords.txt` | Create (T2) | BPE-tokenized output of `sherpa-onnx-cli text2token`; passed to the spotter |
| `C:\Users\admin\voice-echo\voice-echo.py` → actual `C:\Users\admin\voice-echo.py` | Create (T3) | The program: pure logic + config validation |
| `C:\Users\admin\voice-echo\tests\test_voice_echo.py` | Create (T3) | Unit tests for the pure logic |
| `C:\Users\admin\models\sherpa-kws\sherpa-onnx-kws-zipformer-gigaspeech-3.3M-2024-01-01\` | Download (T1) | tokens.txt, bpe.model, encoder/decoder/joiner onnx, test_wavs/ |
| `C:\Users\admin\.claude\piper-models\en_US-lessac-medium.onnx` | Reuse | Piper voice (exists — do not touch) |

---

### Task 1: Install sherpa-onnx, download the model, verify the engine offline

**Files:**
- Create: `C:\Users\admin\voice-echo\download_model.py`
- Create: `C:\Users\admin\voice-echo\verify_offline.py`

**Interfaces:**
- Consumes: nothing.
- Produces: extracted model at `C:\Users\admin\models\sherpa-kws\sherpa-onnx-kws-zipformer-gigaspeech-3.3M-2024-01-01\`; the `read_wave()` / `make_spotter()` / `detect()` helpers later tasks' offline checks can reuse.

- [ ] **Step 1: Install sherpa-onnx**

Run:
```bash
python -m pip install sherpa-onnx
```
Expected: installs `sherpa-onnx` + `sherpa-onnx-core` (1.13.4, cp314 win_amd64 wheel). Verify the CLI exists: `sherpa-onnx-cli --help` prints usage (it lands in `C:\Users\admin\AppData\Local\Programs\Python\Python314\Scripts\`).

- [ ] **Step 2: Create the downloader script**

Create `C:\Users\admin\voice-echo\download_model.py`:

```python
#!/usr/bin/env python3
"""Download and extract the sherpa-onnx English keyword-spotter model.

Stdlib only (urllib + tarfile), so it works on any Windows Python without
curl/tar. Idempotent: skips re-download if the model directory exists.
"""

import tarfile
import urllib.request
from pathlib import Path

MODEL_DIR = "sherpa-onnx-kws-zipformer-gigaspeech-3.3M-2024-01-01"
DEST = Path.home() / "models" / "sherpa-kws"
TARBALL = DEST / (MODEL_DIR + ".tar.bz2")
URL = ("https://github.com/k2-fsa/sherpa-onnx/releases/download/"
       "kws-models/" + TARBALL.name)


def main() -> int:
    DEST.mkdir(parents=True, exist_ok=True)
    model_dir = DEST / MODEL_DIR
    if model_dir.is_dir():
        print(f"Model already present: {model_dir}")
        return 0
    if not TARBALL.exists():
        print(f"Downloading {URL} ...")
        urllib.request.urlretrieve(URL, TARBALL)
    print("Extracting ...")
    with tarfile.open(TARBALL) as tf:
        tf.extractall(DEST)   # trusted model from the official k2-fsa release
    print(f"Extracted to {model_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Run the downloader**

Run: `python C:/Users/admin/voice-echo/download_model.py`
Expected: prints `Downloading https://.../sherpa-onnx-kws-zipformer-gigaspeech-3.3M-2024-01-01.tar.bz2 ...`, then `Extracted to C:\Users\admin\models\sherpa-kws\sherpa-onnx-kws-zipformer-gigaspeech-3.3M-2024-01-01`. Confirm the four spotter files exist:
```bash
ls C:/Users/admin/models/sherpa-kws/sherpa-onnx-kws-zipformer-gigaspeech-3.3M-2024-01-01/
```
Expected: `tokens.txt`, `bpe.model`, `encoder-epoch-12-avg-2-chunk-16-left-64.int8.onnx`, `decoder-epoch-12-avg-2-chunk-16-left-64.onnx`, `joiner-epoch-12-avg-2-chunk-16-left-64.int8.onnx`, `keywords.txt`, `keywords_raw.txt`, `test_wavs/`.

- [ ] **Step 4: Create the offline verification script**

Create `C:\Users\admin\voice-echo\verify_offline.py`:

```python
#!/usr/bin/env python3
"""Run the sherpa-onnx keyword spotter over the model's bundled test WAVs.

Proves the engine detects keywords before any live-microphone work. The
bundled wavs contain the model's own bundled keywords, so detections are
expected; when pointed at our keywords.txt (--keywords) detections are
expected to be zero, but a clean run proves the phrases tokenized.

Usage:
    python verify_offline.py [--keywords PATH]
"""

import argparse
import sys
import wave
from pathlib import Path

import numpy as np
import sherpa_onnx

MODEL = (Path.home() / "models" / "sherpa-kws"
         / "sherpa-onnx-kws-zipformer-gigaspeech-3.3M-2024-01-01")


def read_wave(path):
    """16-bit mono wave -> (float32 samples in [-1,1], sample_rate)."""
    with wave.open(str(path)) as f:
        assert f.getnchannels() == 1, f"not mono: {path}"
        assert f.getsampwidth() == 2, f"not 16-bit: {path}"
        raw = f.readframes(f.getnframes())
    samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768
    return samples, f.getframerate()


def make_spotter(keywords_file):
    return sherpa_onnx.KeywordSpotter(
        tokens=str(MODEL / "tokens.txt"),
        encoder=str(MODEL / "encoder-epoch-12-avg-2-chunk-16-left-64.int8.onnx"),
        decoder=str(MODEL / "decoder-epoch-12-avg-2-chunk-16-left-64.onnx"),
        joiner=str(MODEL / "joiner-epoch-12-avg-2-chunk-16-left-64.int8.onnx"),
        num_threads=1,
        keywords_file=str(keywords_file),
        provider="cpu",
    )


def detect(spotter, wav_path):
    samples, sr = read_wave(wav_path)
    tail = np.zeros(int(0.66 * sr), dtype=np.float32)
    s = spotter.create_stream()
    s.accept_waveform(sr, samples)
    s.accept_waveform(sr, tail)
    s.input_finished()
    hits = []
    while spotter.is_ready(s):
        spotter.decode_stream(s)
        r = spotter.get_result(s)
        if r:
            hits.append(r)
            spotter.reset_stream(s)
    return hits


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--keywords", default=str(MODEL / "keywords.txt"),
                        help="keywords file to load (default: the model's bundled one)")
    args = parser.parse_args()

    keywords_file = Path(args.keywords)
    if not keywords_file.is_file():
        print(f"keywords file not found: {keywords_file}", file=sys.stderr)
        return 1

    spotter = make_spotter(keywords_file)   # raises on unknown tokens -> good signal
    total = det = 0
    for wav in sorted((MODEL / "test_wavs").glob("*.wav")):
        total += 1
        hits = detect(spotter, wav)
        if hits:
            det += 1
            print(f"{wav.name}: detected {hits}")
        else:
            print(f"{wav.name}: no detection")
    print(f"{det}/{total} wavs produced a detection")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Run the offline verification (bundled keywords)**

Run: `python C:/Users/admin/voice-echo/verify_offline.py`
Expected: the spotter loads without error and **at least one** `test_wavs/*.wav` line reads `detected [...]`. (If zero, try the fp32 encoder/joiner onnx files in `make_spotter` and re-check the filename glob.)

- [ ] **Step 6: Checkpoint**

The engine is proven working offline. (No git commit — `voice-echo/` and `models/` are gitignored.)

---

### Task 2: Generate our keywords.txt

**Files:**
- Create: `C:\Users\admin\voice-echo\keywords.raw.txt`
- Create: `C:\Users\admin\voice-echo\keywords.txt` (generated)

**Interfaces:**
- Consumes: extracted model from Task 1 (`tokens.txt`, `bpe.model`); the `sherpa-onnx-cli` console tool from Task 1 Step 1.
- Produces: `C:\Users\admin\voice-echo\keywords.txt` — the BPE-tokenized file with `:3.0` boost and `#0.25` threshold, consumed by Task 4's `KeywordSpotter(keywords_file=...)`.

- [ ] **Step 1: Write the raw keywords source**

Create `C:\Users\admin\voice-echo\keywords.raw.txt`:

```
hey computer listen :3.0 #0.25
hey computer stop :3.0 #0.25
```

(`:score` = boosting score, larger = easier to trigger; `#threshold` = trigger probability, lower = easier. Format per sherpa-onnx docs — spaces around `:`/`#` are allowed in the *input*, not in the output.)

- [ ] **Step 2: Tokenize with text2token**

Run:
```bash
sherpa-onnx-cli text2token \
  C:/Users/admin/voice-echo/keywords.raw.txt \
  C:/Users/admin/voice-echo/keywords.txt \
  --tokens C:/Users/admin/models/sherpa-kws/sherpa-onnx-kws-zipformer-gigaspeech-3.3M-2024-01-01/tokens.txt \
  --tokens-type bpe \
  --bpe-model C:/Users/admin/models/sherpa-kws/sherpa-onnx-kws-zipformer-gigaspeech-3.3M-2024-01-01/bpe.model
```
Expected: no output on success. If `sherpa-onnx-cli` is not on PATH, call it directly: `C:/Users/admin/AppData/Local/Programs/Python/Python314/Scripts/sherpa-onnx-cli.exe`.

- [ ] **Step 3: Verify the tokenized file**

Run: `cat C:/Users/admin/voice-echo/keywords.txt`
Expected: two lines of BPE tokens (e.g. `▁HE Y ▁C O M P U T ER ▁L I S T E N :3.0 #0.25`), each ending with `:3.0 #0.25`. The `▁` word-boundary markers and space-separated tokens are normal.

- [ ] **Step 4: Verify the spotter accepts our phrases**

Run: `python C:/Users/admin/voice-echo/verify_offline.py --keywords C:/Users/admin/voice-echo/keywords.txt`
Expected: exits 0, prints per-wav `no detection` (the bundled wavs don't say our phrases) and `0/N wavs produced a detection`. The important signal is a **clean run** — the `KeywordSpotter` constructor validates every keyword token and would raise on an unknown token.

- [ ] **Step 5: Checkpoint**

`keywords.txt` is valid and the spotter accepts it. (No git commit.)

---

### Task 3: `voice-echo.py` — pure core + config validation (TDD)

**Files:**
- Create: `C:\Users\admin\voice-echo.py`
- Create: `C:\Users\admin\voice-echo\tests\test_voice_echo.py` (parent dir `tests/` is new)

**Interfaces:**
- Consumes: `keywords.txt` path (Task 2), piper model path (exists), model dir (Task 1).
- Produces — module `voice_echo` with: constants `SAMPLE_RATE=16000`, `CHUNK=512`, `RING_SECONDS=20`, `PAD_BEFORE=0.35`, `MAX_SEGMENT_SEC=8`, `MIN_SILENCE_MS=600`, `WARMUP_CHUNKS=64`, `NOISE_FLOOR=0.01`, `State.IDLE`/`State.ACTIVE`, `MODEL_DIR`, `KEYWORDS_FILE`, `PIPER_MODEL`, `MUTE_FLAG`; functions `next_state(current, keyword, muted) -> (state, cue)`, `keyword_of(result) -> str|None`, `below_noise_floor(rms, floor=NOISE_FLOOR) -> bool`, `ring_slice(ring, dropped, total, start_abs, end_abs, min_samples) -> np.ndarray|None`, `parse_args(argv=None) -> argparse.Namespace`, `missing_assets(args, model_dir=MODEL_DIR, keywords_file=KEYWORDS_FILE) -> list[str]`, and `main()` that validates assets and exits 1 listing anything missing (the runtime loop lands in Task 4). Task 4 relies on every signature above exactly.

- [ ] **Step 1: Write the failing test**

Create `C:\Users\admin\voice-echo\tests\test_voice_echo.py`:

```python
"""Unit tests for voice-echo.py pure logic (stdlib unittest).

voice-echo.py has a hyphen, so it cannot be `import`ed by name; load it by
file path. Run:
    python C:\\Users\\admin\\voice-echo\\tests\\test_voice_echo.py
"""

import argparse
import importlib.util
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent   # C:\\Users\\admin
_spec = importlib.util.spec_from_file_location("voice_echo", ROOT / "voice-echo.py")
ve = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ve)


class NextStateTests(unittest.TestCase):
    def test_listen_activates_when_unmuted(self):
        self.assertEqual(ve.next_state("IDLE", "listen", False),
                         ("ACTIVE", "Listening"))

    def test_listen_is_silent_noop_when_muted(self):
        self.assertEqual(ve.next_state("IDLE", "listen", True), ("IDLE", None))

    def test_listen_while_active_is_noop(self):
        self.assertEqual(ve.next_state("ACTIVE", "listen", False),
                         ("ACTIVE", None))

    def test_stop_deactivates_and_cues(self):
        self.assertEqual(ve.next_state("ACTIVE", "stop", False),
                         ("IDLE", "Stopped"))

    def test_stop_from_idle_is_noop(self):
        self.assertEqual(ve.next_state("IDLE", "stop", False), ("IDLE", None))

    def test_stop_silent_when_muted(self):
        self.assertEqual(ve.next_state("ACTIVE", "stop", True), ("IDLE", None))


class KeywordOfTests(unittest.TestCase):
    def test_maps_phrases(self):
        self.assertEqual(ve.keyword_of("hey computer listen"), "listen")
        self.assertEqual(ve.keyword_of("HEY COMPUTER STOP"), "stop")

    def test_unrecognized_returns_none(self):
        self.assertIsNone(ve.keyword_of("hey computer"))


class NoiseFloorTests(unittest.TestCase):
    def test_below_and_at(self):
        self.assertTrue(ve.below_noise_floor(0.0))
        self.assertTrue(ve.below_noise_floor(0.009))
        self.assertFalse(ve.below_noise_floor(0.01))


class RingSliceTests(unittest.TestCase):
    def _ring(self):
        return [np.arange(5, dtype=np.float32),
                np.arange(5, 10, dtype=np.float32)]

    def test_slices_across_blocks(self):
        out = ve.ring_slice(self._ring(), 0, 10, 3, 8, 1)
        self.assertEqual(out.tolist(), [3., 4., 5., 6., 7.])

    def test_clamps_to_available(self):
        out = ve.ring_slice(self._ring(), 0, 10, -100, 100, 1)
        self.assertEqual(out.tolist(), [float(i) for i in range(10)])

    def test_too_short_returns_none(self):
        self.assertIsNone(ve.ring_slice(self._ring(), 0, 10, 4, 5, 2))

    def test_dropped_offset(self):
        # dropped=5 means indexes [5,10) in absolute space are ring[0:5].
        self.assertEqual(ve.ring_slice(self._ring(), 5, 15, 5, 7, 1),
                         [0., 1.])


class ParseArgsTests(unittest.TestCase):
    def test_defaults(self):
        ns = ve.parse_args([])
        self.assertEqual(ns.model, "small")
        self.assertEqual(ns.threads, 4)
        self.assertIsNone(ns.language)
        self.assertIsNone(ns.device)


class MissingAssetsTests(unittest.TestCase):
    def test_reports_all_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            missing = ve.missing_assets(
                argparse.Namespace(voice=str(d / "voice.onnx")),
                model_dir=d, keywords_file=d / "keywords.txt")
            # 4 spotter files + keywords + piper voice = 6, all absent.
            self.assertEqual(len(missing), 6)
            self.assertTrue(any("keywords" in m for m in missing))
            self.assertTrue(any("piper voice" in m for m in missing))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python C:/Users/admin/voice-echo/tests/test_voice_echo.py`
Expected: FAIL — `ModuleNotFoundError`/`FileNotFoundError` for `voice-echo.py`.

- [ ] **Step 3: Write minimal implementation**

Create `C:\Users\admin\voice-echo.py`:

```python
#!/usr/bin/env python3
"""Voice Echo - keyword-triggered STT/TTS dictation echo.

Listens on the microphone with a sherpa-onnx keyword spotter. "hey computer
listen" starts live dictation (faster-whisper) and echoes each transcribed
line aloud via piper TTS; "hey computer stop" stops it. The /mute flag
(~/.claude/.voice-muted) silences everything and blocks activation.

Design: docs/superpowers/specs/2026-08-04-voice-echo-keyword-trigger-design.md

Usage:
    python voice-echo.py [--device N] [--model small] [--threads 4]
                         [--language en] [--voice PATH]
"""

import argparse
import sys
from pathlib import Path

import numpy as np

SAMPLE_RATE = 16000
CHUNK = 512             # 32 ms of audio per block (Silero VAD window)
RING_SECONDS = 20       # keep this much recent audio so we can slice segments
PAD_BEFORE = 0.35       # seconds of audio kept *before* speech starts
MAX_SEGMENT_SEC = 8     # transcribe even if the user never pauses
MIN_SILENCE_MS = 600    # pause length that ends a sentence
WARMUP_CHUNKS = 64      # feed this much silence so VAD is ready on the first word
NOISE_FLOOR = 0.01      # skip segments below this RMS (reuse whisper-live guard)


class State:
    IDLE = "IDLE"
    ACTIVE = "ACTIVE"


MODEL_NAME = "sherpa-onnx-kws-zipformer-gigaspeech-3.3M-2024-01-01"
MODEL_DIR = Path.home() / "models" / "sherpa-kws" / MODEL_NAME
KEYWORDS_FILE = Path.home() / "voice-echo" / "keywords.txt"
PIPER_MODEL = Path.home() / ".claude" / "piper-models" / "en_US-lessac-medium.onnx"
MUTE_FLAG = Path.home() / ".claude" / ".voice-muted"

SPOTTER_FILES = (
    "tokens.txt",
    "encoder-epoch-12-avg-2-chunk-16-left-64.int8.onnx",
    "decoder-epoch-12-avg-2-chunk-16-left-64.onnx",
    "joiner-epoch-12-avg-2-chunk-16-left-64.int8.onnx",
)


def next_state(current, keyword, muted):
    """Return (new_state, cue) for a keyword event.

    cue is the phrase to speak aloud, or None for silence. While muted nothing
    is ever spoken and "listen" never activates dictation.
    """
    if muted:
        return current, None
    if keyword == "listen":
        if current == State.IDLE:
            return State.ACTIVE, "Listening"
        return State.ACTIVE, None
    if keyword == "stop":
        if current == State.ACTIVE:
            return State.IDLE, "Stopped"
        return State.IDLE, None
    return current, None


def keyword_of(result):
    """Map a spotter result string to a keyword key ('listen'/'stop') or None."""
    r = result.lower()
    if "stop" in r:
        return "stop"
    if "listen" in r:
        return "listen"
    return None


def below_noise_floor(rms, floor=NOISE_FLOOR):
    return rms < floor


def ring_slice(ring, dropped, total, start_abs, end_abs, min_samples):
    """Slice [start_abs, end_abs) out of the ring; None if too short or empty.

    ring holds CHUNK-sized float32 pieces; dropped is the sample count removed
    from its front; total is the absolute sample count seen so far.
    """
    start_abs = max(dropped, start_abs)
    end_abs = min(total, end_abs)
    if end_abs - start_abs < min_samples:
        return None
    lo, hi = start_abs - dropped, end_abs - dropped
    if hi <= lo:
        return None
    return np.concatenate(ring)[lo:hi]


def parse_args(argv=None):
    ap = argparse.ArgumentParser(
        description="Keyword-triggered STT/TTS dictation echo.")
    ap.add_argument("--device", type=int, default=None,
                    help="Sound device index (default: system mic)")
    ap.add_argument("--model", default="small",
                    help="Whisper model size (default: small)")
    ap.add_argument("--threads", type=int, default=4,
                    help="CPU threads for Whisper (default: 4)")
    ap.add_argument("--language", default=None,
                    help="Whisper language code; auto-detect if omitted")
    ap.add_argument("--voice", default=str(PIPER_MODEL),
                    help="Path to a piper voice .onnx")
    return ap.parse_args(argv)


def missing_assets(args, model_dir=MODEL_DIR, keywords_file=KEYWORDS_FILE):
    """Return a list of human-readable strings for required files that are missing."""
    missing = []
    for name in SPOTTER_FILES:
        p = model_dir / name
        if not p.is_file():
            missing.append(f"sherpa model {name}: {p}")
    if not keywords_file.is_file():
        missing.append(f"keywords file: {keywords_file}")
    if not Path(args.voice).is_file():
        missing.append(f"piper voice: {args.voice}")
    return missing


def main():
    args = parse_args()
    missing = missing_assets(args)
    if missing:
        print("Missing required assets:", file=sys.stderr)
        for m in missing:
            print("  - " + m, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python C:/Users/admin/voice-echo/tests/test_voice_echo.py`
Expected: `OK` (all 16 tests pass).

- [ ] **Step 5: Smoke-test the CLI**

Run: `python C:/Users/admin/voice-echo.py`
Expected: since Task 1/2 are done, exits 0 with no output (all assets present).

- [ ] **Step 6: Checkpoint**

Unit tests pass; the CLI validates config. (No git commit.)

---

### Task 4: `voice-echo.py` — runtime pipeline (spotter + dictation + piper echo + mute)

**Files:**
- Modify: `C:\Users\admin\voice-echo.py` — replace the body of `main()`; all module-level constants, `State`, and the pure functions from Task 3 stay unchanged.

**Interfaces:**
- Consumes: Task 3's pure functions/constants; `keywords.txt` (Task 2); the piper voice; the extracted model (Task 1).
- Produces: the always-on program. No later task consumes it — verification is the live test below.

- [ ] **Step 1: Replace `main()` with the runtime**

Replace the Task 3 `main()` (the config-validation stub) with this full implementation. The heavy libraries (`sherpa_onnx`, `sounddevice`, `faster_whisper`, `piper`, `silero_vad`) are imported inside `main()` so the module stays importable without them for the Task 3 unit tests.

```python
def main():
    args = parse_args()
    missing = missing_assets(args)
    if missing:
        print("Missing required assets:", file=sys.stderr)
        for m in missing:
            print("  - " + m, file=sys.stderr)
        return 1

    import queue
    import threading
    from collections import deque

    import sherpa_onnx
    import sounddevice as sd
    from faster_whisper import WhisperModel
    from piper import PiperVoice
    from silero_vad import VADIterator, load_silero_vad

    # ---- keyword spotter (always armed) ----
    spotter = sherpa_onnx.KeywordSpotter(
        tokens=str(MODEL_DIR / "tokens.txt"),
        encoder=str(MODEL_DIR / "encoder-epoch-12-avg-2-chunk-16-left-64.int8.onnx"),
        decoder=str(MODEL_DIR / "decoder-epoch-12-avg-2-chunk-16-left-64.onnx"),
        joiner=str(MODEL_DIR / "joiner-epoch-12-avg-2-chunk-16-left-64.int8.onnx"),
        num_threads=1,
        keywords_file=str(KEYWORDS_FILE),
        provider="cpu",
    )
    kws_stream = spotter.create_stream()

    # ---- piper TTS (reuses ~/.claude/piper-models voice) ----
    voice = PiperVoice.load(args.voice)
    out = sd.OutputStream(samplerate=voice.config.sample_rate,
                          channels=1, dtype="float32")
    speak_lock = threading.Lock()

    def speak(text):
        if MUTE_FLAG.exists():
            return
        with speak_lock:
            for chunk in voice.synthesize(text):
                out.write(chunk.audio_float_array)

    # ---- dictation (models loaded once, stay hot for instant toggling) ----
    vad = VADIterator(load_silero_vad(), sampling_rate=SAMPLE_RATE,
                      min_silence_duration_ms=MIN_SILENCE_MS)
    for _ in range(WARMUP_CHUNKS):
        vad(np.zeros((1, CHUNK), dtype=np.float32))
    model = WhisperModel(args.model, device="cpu", compute_type="int8",
                         cpu_threads=args.threads)
    lang = args.language

    audio_q = queue.Queue(maxsize=200)      # whisper pipeline input (bounded)
    spotter_q = queue.Queue(maxsize=200)    # spotter input (bounded)
    transcribe_q = queue.Queue(maxsize=16)  # ready segments -> transcriber
    active = threading.Event()
    state = State.IDLE

    def drain(q):
        try:
            while True:
                q.get_nowait()
        except queue.Empty:
            pass

    def transcriber():
        nonlocal lang
        while True:
            audio = transcribe_q.get()
            if audio is None:
                return
            if not active.is_set():
                continue                    # "stop" was heard mid-flight; drop it
            if below_noise_floor(float(np.sqrt(np.mean(audio ** 2)))):
                continue
            segments, info = model.transcribe(
                audio, language=lang, beam_size=1,
                condition_on_previous_text=False)
            if lang is None and info.language:
                lang = info.language
            text = "".join(s.text for s in segments).strip()
            if text:
                print("> " + text, flush=True)
                speak(text)

    def spotter_loop():
        nonlocal state
        while True:
            block = spotter_q.get()
            if block is None:
                return
            kws_stream.accept_waveform(SAMPLE_RATE, block)
            while spotter.is_ready(kws_stream):
                spotter.decode_stream(kws_stream)
                result = spotter.get_result(kws_stream)
                if result:
                    spotter.reset_stream(kws_stream)   # mandatory after a hit
                    key = keyword_of(result)
                    if key is None:
                        continue
                    prev = state
                    state, cue = next_state(state, key, MUTE_FLAG.exists())
                    if cue is not None:
                        speak(cue)
                    if prev == State.ACTIVE and state == State.IDLE:
                        active.clear()
                        drain(audio_q)
                        drain(transcribe_q)
                    elif state == State.ACTIVE:
                        active.set()

    def on_audio(indata, frames, time_info, status):
        block = np.asarray(indata, dtype=np.float32).reshape(-1)
        for q in (spotter_q, audio_q):
            try:
                q.put_nowait(block.copy())
            except queue.Full:              # drop oldest, keep newest
                try:
                    q.get_nowait()
                    q.put_nowait(block.copy())
                except Exception:
                    pass

    t_spotter = threading.Thread(target=spotter_loop, daemon=True)
    t_spotter.start()
    t_trans = threading.Thread(target=transcriber, daemon=True)
    t_trans.start()

    try:
        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32",
                            blocksize=CHUNK, device=args.device,
                            callback=on_audio):
            print("Voice-echo ready. Say: \"hey computer listen\" / \"hey computer stop\".")
            ring = deque()
            dropped = 0
            total = 0
            active_start = None
            was_active = False
            pre_roll = int(PAD_BEFORE * SAMPLE_RATE)
            max_seg = int(MAX_SEGMENT_SEC * SAMPLE_RATE)
            min_seg = SAMPLE_RATE // 10      # ignore <100 ms blips

            def emit_segment(start_abs, end_abs):
                seg = ring_slice(ring, dropped, total, start_abs, end_abs, min_seg)
                if seg is not None:
                    try:
                        transcribe_q.put_nowait(seg)
                    except queue.Full:
                        pass

            while True:
                block = np.asarray(audio_q.get(), dtype=np.float32).reshape(-1)

                if active.is_set() and MUTE_FLAG.exists():
                    # Muted mid-dictation: halt immediately (spec state machine).
                    active.clear()
                    drain(audio_q)
                    drain(transcribe_q)
                    was_active = False
                    continue

                if not active.is_set():
                    was_active = False
                    continue

                if not was_active:
                    # Just activated: start a fresh dictation window so no
                    # pre-activation audio is transcribed.
                    ring = deque()
                    dropped = 0
                    total = 0
                    active_start = None
                    was_active = True

                ring.append(block)
                total += len(block)
                while len(ring) * CHUNK > RING_SECONDS * SAMPLE_RATE:
                    ring.popleft()
                    dropped += CHUNK

                event = vad(block.reshape(1, -1))
                if event is not None:
                    if "start" in event and active_start is None:
                        active_start = event["start"]
                    if "end" in event and active_start is not None:
                        emit_segment(active_start - pre_roll, event["end"])
                        active_start = None

                if active_start is not None and total - active_start > max_seg:
                    emit_segment(active_start - pre_roll, total)
                    active_start = None
    except KeyboardInterrupt:
        print("\nStopped.")
        active.clear()
        transcribe_q.put(None)
        t_trans.join(timeout=2)
        spotter_q.put(None)
        t_spotter.join(timeout=2)
    except sd.PortAudioError as e:
        print("\nCould not open the microphone: {}".format(e))
        print("Try --device <index> to pick a different input. Available inputs:")
        for d in sd.query_devices():
            if d["max_input_channels"] > 0:
                print("   {}: {}".format(d["index"], d["name"]))
    finally:
        out.close()
    return 0
```

- [ ] **Step 2: Re-run the unit tests (nothing broke)**

Run: `python C:/Users/admin/voice-echo/tests/test_voice_echo.py`
Expected: still `OK`. The heavy imports are inside `main()`, so the test module never touches them.

- [ ] **Step 3: Static sanity check**

Run: `python -c "import ast; ast.parse(open(r'C:\Users\admin\voice-echo.py',encoding='utf-8').read()); print('syntax ok')"`
Expected: `syntax ok`. Also `python C:/Users/admin/voice-echo.py` still exits 0 (config validation passes before the loop).

- [ ] **Step 4: End-to-end live verification** (requires you + a microphone)

1. Start: `python C:/Users/admin/voice-echo.py` → prints `Voice-echo ready. ...`.
2. Say **"hey computer listen"** → you hear **"Listening"** (cue proves the trigger registered). Dictate a sentence and pause → the line prints as `> <text>` and is spoken aloud.
3. Say **"hey computer stop"** mid-dictation → hear **"Stopped"**, dictation stops, the spotter stays armed.
4. Say **"hey computer listen"** again → dictation resumes (models stayed hot — instant).
5. Ctrl+C → `Stopped.` and a clean exit.

- [ ] **Step 5: Mute integration verification**

1. Run **`/mute`** in Claude Code (creates `~/.claude/.voice-muted`).
2. Say **"hey computer listen"** → **nothing** is spoken and dictation does not start.
3. Say **"hey computer stop"** → nothing spoken (still quiet, spotter armed).
4. Run **`/unmute`** → trigger works again: "hey computer listen" → "Listening", dictation echoes.
5. Mute **mid-dictation** (`/mute` while it is echoing) → echo stops immediately and the state drops to IDLE.

- [ ] **Step 6: Checkpoint**

All live steps pass; environment left **unmuted**; no zombie `python` processes from the test runs (`tasklist | grep -i python` shows only unrelated processes). (No git commit.)

---

## Self-Review

- **Spec coverage:** always-on spotter + single mic stream → Task 4 `on_audio`/`spotter_loop`; `ACTIVE`/`IDLE` state machine + cues → Task 3 `next_state` + Task 4; dictation echo via in-process piper PCM → Task 4 `speak()` (`PiperVoice.synthesize` → `OutputStream`, no ffplay); reuse of whisper-live VAD/ring constants and noise-floor guard → Task 3 constants + `ring_slice`/`below_noise_floor`; mute semantics (no speech, no activation, mid-run halt) → `next_state` muted branch + Task 4 main-loop mute check; errors (bad mic list, missing assets, Ctrl+C) → Task 3 `missing_assets` + Task 4 exception handlers; keywords via `text2token` → Task 2; offline verification over bundled test wavs → Task 1; piper voice reused, not re-downloaded → Global Constraints + Task 4. All spec sections covered.
- **Placeholder scan:** every step has concrete code or an exact command; the only `...` is inside `emit_segment` where the else-branch is intentionally empty (`queue.Full` → drop).
- **Type consistency:** `next_state(current, keyword, muted)`, `keyword_of(result)`, `below_noise_floor(rms, floor)`, `ring_slice(ring, dropped, total, start_abs, end_abs, min_samples)`, `parse_args(argv)`, `missing_assets(args, model_dir, keywords_file)` are defined once (Task 3) and used identically in the Task 3 tests and Task 4. Constants are defined in Task 3 and referenced verbatim in Task 4. `State.IDLE`/`State.ACTIVE` string values match the tests. Model filenames match the Task 1 `ls` listing (`...chunk-16-left-64.int8.onnx` for encoder/joiner, fp32 decoder).
