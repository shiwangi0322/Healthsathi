"""
HealthSathi — voice_assistant.py
Standalone terminal voice assistant (no browser needed).
Run: python voice_assistant.py

Flow: Mic → Vosk STT → NLP → DB → pyttsx3 TTS → Speaker
"""

import os
import sys
import json
import queue
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.health_db         import init_db
from modules.symptom_processor import process_nlp

try:
    import pyttsx3
    import sounddevice as sd
    from vosk import Model, KaldiRecognizer
except ImportError as ex:
    print("\n[ERROR] Missing library: {}".format(ex))
    print("Install: pip install vosk sounddevice pyttsx3")
    sys.exit(1)

# ── TTS ───────────────────────────────────────────────────────
_tts = pyttsx3.init()
_tts.setProperty("rate",   140)
_tts.setProperty("volume", 0.95)

_voices = _tts.getProperty("voices")
if _voices and hasattr(_voices, "__iter__"):
    for _v in _voices:  # type: ignore[union-attr]
        if "hindi" in str(getattr(_v, "name", "")).lower():
            _tts.setProperty("voice", _v.id)
            print("[TTS] Hindi voice: {}".format(getattr(_v, "name", "")))
            break


def speak(text: str) -> None:
    print("\n[HealthSathi]: {}\n".format(text))
    _tts.say(text)
    _tts.runAndWait()


# ── Model finder ──────────────────────────────────────────────
def find_model() -> Optional[str]:
    base = os.path.dirname(os.path.abspath(__file__))
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
            return path
    try:
        for item in os.listdir(base):
            full = os.path.join(base, item)
            if item.startswith("vosk-model") and os.path.isdir(full):
                return full
    except OSError:
        pass
    return None


# ── Audio queue ───────────────────────────────────────────────
_audio_q: queue.Queue = queue.Queue()


def _audio_callback(indata, frames, time, status) -> None:  # type: ignore[misc]
    if status:
        print("[Audio] {}".format(status), file=sys.stderr)
    _audio_q.put(bytes(indata))


# ── Main voice loop ───────────────────────────────────────────
def run_assistant() -> None:
    print("\n" + "=" * 52)
    print("   HealthSathi — Aapka Swasthya Sahayak")
    print("=" * 52)

    print("\n[Setup] Database shuru ho raha hai...")
    init_db()

    model_path = find_model()
    if not model_path:
        print("\n[ERROR] Vosk model nahi mila!")
        print("Download: https://alphacephei.com/vosk/models")
        print("Folder ko C:\\Healthsathi\\Healthsathi\\ mein rakhen.")
        sys.exit(1)

    print("[Setup] Voice model load ho raha hai...")
    model      = Model(model_path)
    samplerate = 16000
    recognizer = KaldiRecognizer(model, samplerate)
    print("[Setup] Taiyaar hai! Model: {}\n".format(os.path.basename(model_path)))

    speak("Namaste! Main HealthSathi hoon. Apni takleef batayen.")

    print("-" * 52)
    print("Sun raha hoon... bolein.")
    print("Rokne ke liye: 'exit' bolein ya Ctrl+C dabayein")
    print("-" * 52)

    try:
        with sd.RawInputStream(
            samplerate=samplerate,
            blocksize=8000,
            dtype="int16",
            channels=1,
            callback=_audio_callback,
        ):
            while True:
                data = _audio_q.get()

                if recognizer.AcceptWaveform(data):
                    result = json.loads(recognizer.Result())
                    text   = str(result.get("text", "")).strip()

                    if not text:
                        continue

                    print("\n[Aap]: {}".format(text))

                    exit_words = ["exit", "stop", "band karo", "alvida", "bye", "khatam"]
                    if any(w in text.lower() for w in exit_words):
                        speak("Alvida! Apna khyal rakhein.")
                        break

                    try:
                        nlp_result = process_nlp(text)
                        response   = str(nlp_result["hindi_response"])
                        speak(response)
                    except Exception as ex:
                        print("[NLP Error] {}".format(ex))
                        speak("Maaf karein, kuch gadbad hui. Dobara batayen.")

                    while not _audio_q.empty():
                        try:
                            _audio_q.get_nowait()
                        except queue.Empty:
                            break

                    print("\nSun raha hoon...")

    except KeyboardInterrupt:
        print("\n\n[HealthSathi] Band ho raha hai...")
        speak("Alvida!")
    except Exception as ex:
        print("\n[ERROR] {}".format(ex))
        speak("Takniki samasya aayi. Dobara shuru karein.")


if __name__ == "__main__":
    run_assistant()