"""
HealthSathi — modules/voice_handler.py
STT: Vosk (offline)
TTS: pyttsx3 (offline)
Also handles SSE streaming for /stream_voice Flask route.
"""

import os
import sys
import json
import queue
import threading
from typing import Optional, Generator

# ── TTS ───────────────────────────────────────────────────────
try:
    import pyttsx3 as _pyttsx3

    _engine: Optional[_pyttsx3.Engine] = None
    _engine_lock = threading.Lock()

    def _get_engine() -> _pyttsx3.Engine:
        global _engine
        if _engine is None:
            _engine = _pyttsx3.init()
            _engine.setProperty("rate",   140)
            _engine.setProperty("volume", 0.95)
            voices = _engine.getProperty("voices")
            if voices and hasattr(voices, "__iter__"):
                for v in voices:  # type: ignore[union-attr]
                    v_name = str(getattr(v, "name", "")).lower()
                    v_id   = str(getattr(v, "id",   "")).lower()
                    if "hindi" in v_name or "hi_in" in v_id:
                        _engine.setProperty("voice", v.id)
                        print("[TTS] Hindi voice: {}".format(getattr(v, "name", "")))
                        break
        return _engine

    def speak(text: str) -> None:
        """Speak text via pyttsx3 (thread-safe)."""
        with _engine_lock:
            try:
                print("\n[HealthSathi]: {}\n".format(text))
                eng = _get_engine()
                eng.say(text)
                eng.runAndWait()
            except Exception as ex:
                print("[TTS Error] {}".format(ex))

except ImportError:
    def speak(text: str) -> None:  # type: ignore[misc]
        print("\n[HealthSathi - NO pyttsx3]: {}".format(text))
        print("Fix: pip install pyttsx3")


# ── Vosk model finder ─────────────────────────────────────────
def _find_vosk_model() -> Optional[str]:
    """Find Vosk model folder in project directory."""
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    preferred = [
        "vosk-model-small-hi-0.22",
        "vosk-model-hi-0.22",
        "vosk-model-en-in-0.5",
        "vosk-model-small-en-in-0.4",
        "vosk-model-small-en-us-0.15",
    ]
    for name in preferred:
        path = os.path.join(base, name)
        if os.path.isdir(path):
            print("[Voice] Model: {}".format(name))
            return path
    try:
        for item in os.listdir(base):
            full = os.path.join(base, item)
            if item.startswith("vosk-model") and os.path.isdir(full):
                print("[Voice] Auto-detected: {}".format(item))
                return full
    except OSError:
        pass
    return None


# ── listen() — blocking, used by /process_voice ───────────────
def listen(timeout_total: int = 10) -> str:
    """
    Record mic and return recognized text.
    Returns empty string on silence.
    Returns 'ERROR: Mic issue - ...' on hardware error.
    """
    try:
        import sounddevice as sd  # noqa: PLC0415
        from vosk import Model, KaldiRecognizer  # noqa: PLC0415
    except ImportError as ex:
        return "ERROR: Mic issue - {}".format(ex)

    model_path = _find_vosk_model()
    if not model_path:
        return "ERROR: Mic issue - No Vosk model found"

    try:
        model      = Model(model_path)
        samplerate = 16000
        rec        = KaldiRecognizer(model, samplerate)
        aq: queue.Queue = queue.Queue()

        def callback(indata, frames, time, status) -> None:  # type: ignore[misc]
            if status:
                print("[Audio] {}".format(status), file=sys.stderr)
            aq.put(bytes(indata))

        import time as time_mod  # noqa: PLC0415
        final_text = ""

        with sd.RawInputStream(
            samplerate=samplerate, blocksize=8000,
            dtype="int16", channels=1, callback=callback
        ):
            start = time_mod.time()
            while time_mod.time() - start < timeout_total:
                try:
                    data = aq.get(timeout=1.0)
                except queue.Empty:
                    continue
                if rec.AcceptWaveform(data):
                    result = json.loads(rec.Result())
                    text   = str(result.get("text", "")).strip()
                    if text:
                        final_text = text
                        break

            if not final_text:
                partial    = json.loads(rec.PartialResult())
                final_text = str(partial.get("partial", "")).strip()

        return final_text

    except Exception as ex:
        return "ERROR: Mic issue - {}".format(str(ex))


# ── listen_generator() — SSE streaming, used by /stream_voice ─
def listen_generator(timeout: int = 8) -> Generator[str, None, None]:
    """
    Generator for Server-Sent Events.
    Yields JSON strings:
      {"type": "partial", "text": "..."}
      {"type": "final",   "text": "..."}
      {"type": "error",   "text": "..."}
    """
    try:
        import sounddevice as sd  # noqa: PLC0415
        from vosk import Model, KaldiRecognizer  # noqa: PLC0415
    except ImportError as ex:
        yield json.dumps({"type": "error", "text": "Library missing: {}".format(ex)})
        return

    model_path = _find_vosk_model()
    if not model_path:
        yield json.dumps({"type": "error", "text": "Vosk model not found. Download from alphacephei.com/vosk/models"})
        return

    try:
        model      = Model(model_path)
        samplerate = 16000
        rec        = KaldiRecognizer(model, samplerate)
        aq: queue.Queue = queue.Queue()

        def callback(indata, frames, time, status) -> None:  # type: ignore[misc]
            aq.put(bytes(indata))

        import time as time_mod  # noqa: PLC0415

        with sd.RawInputStream(
            samplerate=samplerate, blocksize=4000,
            dtype="int16", channels=1, callback=callback
        ):
            start     = time_mod.time()
            last_part = ""

            while time_mod.time() - start < timeout:
                try:
                    data = aq.get(timeout=0.5)
                except queue.Empty:
                    continue

                if rec.AcceptWaveform(data):
                    result = json.loads(rec.Result())
                    text   = str(result.get("text", "")).strip()
                    if text:
                        yield json.dumps({"type": "final", "text": text})
                        return
                else:
                    partial_result = json.loads(rec.PartialResult())
                    p_text = str(partial_result.get("partial", "")).strip()
                    if p_text and p_text != last_part:
                        last_part = p_text
                        yield json.dumps({"type": "partial", "text": p_text})

        final_result = json.loads(rec.FinalResult())
        final_text   = str(final_result.get("text", "")).strip()
        yield json.dumps({"type": "final", "text": final_text})

    except Exception as ex:
        yield json.dumps({"type": "error", "text": str(ex)})