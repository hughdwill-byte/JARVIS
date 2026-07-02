"""Push-to-talk: press Enter to record, Enter again to stop, then transcribe.

Deliberately simple and reliable — no key-hold detection, no global hotkeys,
no root permissions. A visible [MIC ACTIVE] banner shows while recording.

Run `python -m app.audio.push_to_talk --list` to list audio input devices.
"""

from __future__ import annotations

import sys

from app.audio.speech_to_text import Transcriber
from app.config import Config, load_config
from app.logger import get_logger

log = get_logger("ptt")

try:
    import numpy as np
    import sounddevice as sd
except ImportError:
    sd = None
    np = None

MAX_RECORD_SECONDS = 60


class PushToTalk:
    def __init__(self, cfg: Config, transcriber: Transcriber):
        self.cfg = cfg
        self.transcriber = transcriber

    @property
    def available(self) -> bool:
        if sd is None:
            return False
        try:
            devices = sd.query_devices()
        except Exception:
            return False
        return any(d["max_input_channels"] > 0 for d in devices)

    def why_unavailable(self) -> str:
        if sd is None:
            return ("Voice input needs: pip install sounddevice numpy "
                    "(Linux/Pi also: sudo apt install libportaudio2)")
        if not self.transcriber.available:
            return ("Speech-to-text needs: pip install faster-whisper "
                    "(or set STT_PROVIDER=none to silence this)")
        return "No microphone detected. Plug one in and check your OS sound settings."

    def record_once(self) -> str:
        """Record until the user presses Enter, return the transcript ('' on failure)."""
        if not self.available or not self.transcriber.available:
            print(f"  {self.why_unavailable()}")
            return ""

        sample_rate = self.cfg.mic_sample_rate
        chunks: list = []

        def _callback(indata, _frames, _time, status):
            if status:
                log.warning("Audio status: %s", status)
            chunks.append(indata.copy())

        try:
            with sd.InputStream(
                samplerate=sample_rate,
                channels=1,
                dtype="float32",
                device=self.cfg.mic_device_index,
                callback=_callback,
            ):
                print("  [MIC ACTIVE] Recording — press Enter to stop.")
                input()
        except Exception as exc:
            print(f"  Microphone error: {exc}. Check the device with "
                  "`python -m app.audio.push_to_talk --list` and set MIC_DEVICE_INDEX in .env.")
            return ""
        finally:
            print("  [MIC OFF] Transcribing...")

        if not chunks:
            return ""
        audio = np.concatenate(chunks).flatten()[: sample_rate * MAX_RECORD_SECONDS]
        if float(np.abs(audio).max() or 0) < 0.005:
            print("  I heard silence — check the mic isn't muted, or set MIC_DEVICE_INDEX.")
            return ""
        return self.transcriber.transcribe_array(audio, sample_rate)


def list_devices() -> None:
    if sd is None:
        print("sounddevice not installed. Run: pip install sounddevice")
        return
    print(sd.query_devices())
    print("\nSet MIC_DEVICE_INDEX in .env to the number of your microphone.")


if __name__ == "__main__":
    if "--list" in sys.argv:
        list_devices()
    else:
        cfg = load_config()
        ptt = PushToTalk(cfg, Transcriber(cfg))
        print("Mic test — speak after pressing Enter, press Enter again to stop.")
        input("Press Enter to start recording...")
        print(f"Transcript: {ptt.record_once() or '(nothing understood)'}")
