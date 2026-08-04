# Voice Echo: Keyword-Triggered STT/TTS Dictation Echo

- **Date:** 2026-08-04
- **Status:** Design approved; pending spec review

## Summary

An always-on Windows program that listens on the microphone for the English
phrases **"start listening"** and **"stop listening"** using sherpa-onnx
keyword spotting.

- **"start listening"** → enables live dictation (faster-whisper) and echoes
  each transcribed line aloud via piper TTS.
- **"stop listening"** → disables dictation and the echo, leaving only the
  keyword spotter running.

Fully local, offline, CPU-only, private.

## Goals

- **One always-on process.** The faster-whisper model stays loaded in memory
  for the whole run, so toggling is an instant flag flip — no per-toggle model
  reload (the reload would cost seconds each time).
- **Always-on keyword spotter.** Even while dictation is active, the spotter
  keeps listening so "stop listening" is always actionable.
- **Single microphone stream.** One `sounddevice.InputStream` feeds both the
  keyword spotter and the STT pipeline — no double-opening the mic.
- **Clean `ACTIVE`/`IDLE` state machine.** IDLE is silent and CPU-idle apart
  from the lightweight spotter.

## Non-goals (YAGNI)

- No `--type` clipboard-paste mode — that is whisper-live.py's job.
- No custom Chinese piper voice — English echo by default; a `--voice` flag
  exists so other voices can be supplied later.
- No GUI / tray icon.

## Architecture

```
                 ┌────────────────────────────────────────────────┐
  mic ─► InputStream ─► dispatch ─┬─► sherpa-onnx keyword spotter (ALWAYS on)
 (16 kHz, 512-blk)│                 │  ┌─ "start listening" ─► state=ACTIVE, speak "Listening"
                 │                 │  └─ "stop listening"  ─► state=IDLE,   speak "Stopped"
                 └─► when ACTIVE: silero VAD + ring buffer
                                     └─► faster-whisper transcriber thread
                                           └─► print "> text" + piper synth → sounddevice play
```

- One audio stream dispatches each block to the spotter and (when ACTIVE) the
  VAD/ring-buffer pipeline.
- The whisper model and piper voice are loaded once at startup and stay hot.

## State machine

| Event | From → To | Actions |
|---|---|---|
| (startup) | — → `IDLE` | Load whisper model + piper voice; start spotter |
| "start listening" | `IDLE` → `ACTIVE` | Speak "Listening"; prime VAD; begin transcription |
| "stop listening" | `ACTIVE` → `IDLE` | Halt transcription loop; drop queued/in-flight segments; speak "Stopped" |
| "stop listening" | `IDLE` → `IDLE` | No-op (spotter stays quiet) |
| Ctrl+C | any → exit | Clean shutdown; no audio |

## Components

| File / path | Purpose |
|---|---|
| `C:\Users\admin\voice-echo.py` | The program. Constants + CLI args mirroring whisper-live.py: `--device`, `--model`, `--threads`, `--language`, `--voice` |
| `C:\Users\admin\voice-echo\keywords.txt` | sherpa-onnx keywords: `start listening,10` / `stop listening,10` |
| `C:\Users\admin\models\sherpa-kws\` | sherpa-onnx int8 zipformer keyword-spotter model (one-time download, ~tens of MB) |
| `C:\Users\admin\models\piper\` | English piper voice, e.g. `en_US-lessac-medium` (one-time download) |

## Behavior details

- **Echo:** each transcribed segment is spoken by piper. Raw PCM is
  synthesized in-process (`PiperVoice.synthesize_stream_raw`) and played via a
  `sounddevice` output stream — all-Python, no new playback dependency.
- **State cues:** "Listening" / "Stopped" are spoken aloud at each transition
  so the user gets audible confirmation the trigger registered.
- **Mid-sentence stop:** if the spotter hears "stop listening" mid-sentence,
  the in-progress segment is discarded cleanly.
- **Noise-floor guard:** reuse whisper-live.py's guard (skip segments whose
  RMS < 0.01) so silence isn't transcribed.
- **Acoustic feedback (known limitation):** piper's own output may be picked
  up by the mic and either transcribed or (rarely) misheard as a phrase.
  Mitigations: headphones, or tune spotter thresholds. Acceptable for v1.
- **Errors** mirror whisper-live.py: bad mic → list available devices; model
  download failure → clear message; `Ctrl+C` → clean shutdown.

## Technical approach notes

- **sherpa-onnx:** `pip install sherpa-onnx`. `KeywordSpotter(config)` built
  from `FeatureConfig` + `OnlineZipformerKwsModelConfig` + `keywords_file`.
  Feed 16 kHz mono frames; loop `is_ready(stream)` / `decode_stream(stream)` /
  `get_result(stream)`. Verify offline with the model's bundled test WAVs
  before the live mic test.
- **piper:** already installed (`piper-tts` 1.6.0). `PiperVoice.load(model)`,
  then `synthesize_stream_raw(text)` → int16 PCM → `sounddevice` output.
- **STT:** faster-whisper + silero-vad + ring buffer — reuse the proven
  pattern from whisper-live.py (WARMUP priming, `PAD_BEFORE`, `MAX_SEGMENT_SEC`,
  `MIN_SILENCE_MS`, `emit_segment`).

## Verification

1. **Offline:** run the keyword spotter over the sherpa-onnx test WAVs;
   confirm both "start listening" and "stop listening" are detected.
2. **Live mic test:** user says "start listening" → hear "Listening", then
   dictate → lines echo aloud; say "stop listening" → hear "Stopped", dictation
   stops, spotter remains armed.

## Out of scope / future

- Chinese trigger phrases (would require a different engine or custom training).
- `--type` paste mode integration.
- Tray icon / autostart.
