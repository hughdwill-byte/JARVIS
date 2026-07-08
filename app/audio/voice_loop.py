"""Hands-free voice loop: say "hey jarvis" (or just "jarvis"), then speak.

State machine (privacy states are explicit and visible):

  LISTENING  — mic streams locally; every 80ms chunk is scored by the wake
               detector and immediately discarded. Nothing is stored/uploaded.
               Banner: [MIC ACTIVE — waiting for 'jarvis'; say 'shutdown' to stop]
  AWAKE      — wake word heard; records ONE utterance (until you pause),
               transcribes it locally, answers it, then returns to LISTENING.
  ASLEEP     — after you say "shutdown" (or type /sleep): the microphone
               device is CLOSED, not just ignored. Banner: [MIC OFF]
               Typing anything in the terminal (or /listen) re-arms it.

Runs as a daemon thread beside the terminal loop; both funnel through
Assistant.handle(), which is lock-protected.
"""

from __future__ import annotations

import re
import threading
import time
from typing import TYPE_CHECKING

from app.audio.wake_word import CHUNK_SAMPLES, WakeWordDetector
from app.logger import get_logger

if TYPE_CHECKING:
    from app.assistant import Assistant

log = get_logger("voiceloop")

try:
    import numpy as np
    import sounddevice as sd
except ImportError:
    sd = None
    np = None

SAMPLE_RATE = 16000          # required by both openwakeword and whisper
SPEECH_RMS = 0.006           # voice-activity threshold (lower = hears quieter mics)
START_TIMEOUT_S = 6.0        # give up if you say "jarvis" then nothing
FOLLOW_UP_WINDOW_S = 8.0     # reply window after JARVIS speaks (no wake word needed)
MAX_UTTERANCE_S = 15.0
END_SILENCE_S = 1.2          # stop recording after this much quiet
MIN_VOICED_S = 0.25          # ignore blips shorter than this (coughs, keyboard, door)
TTS_COOLDOWN_S = 0.8         # ignore the mic briefly after JARVIS speaks (room echo tail)
BARGE_RMS = 0.02             # louder-than-playback level that counts as talking over it
BARGE_SUSTAIN_S = 0.4        # sustained speech needed to interrupt (not a cough)
REMINDER_POLL_S = 5.0        # how often the idle loop checks for due reminders

# Whisper invents these from noise/near-silence. If a follow-up "reply" is just
# one of these, treat it as no reply at all — stay silent.
_NOISE_TRANSCRIPTS = {
    "thank you", "thanks", "thank you very much", "thanks for watching",
    "you", "bye", "uh", "um", "hmm", "mm", "oh", "ah", "the",
}


def is_noise_transcript(text: str) -> bool:
    cleaned = re.sub(r"[^a-z ]", "", text.lower()).strip()
    return len(cleaned) <= 1 or cleaned in _NOISE_TRANSCRIPTS


# Common filler words carry no evidence about WHO spoke; judging echo on them
# made real follow-ups like "do that now" vanish.
_STOPWORDS = frozenset(
    "the a an and or to of in on for you your i it that this is are do now too "
    "with my me at be was so just can will would have has had not no yes okay ok "
    "please what about how we they them his her its as by from".split()
)


def looks_like_echo(transcript: str, last_spoken: str) -> bool:
    """True if the mic mostly heard JARVIS's own words (speaker bleed/echo)."""
    if not last_spoken or not transcript:
        return False
    t = re.sub(r"[^a-z ]", "", transcript.lower()).strip()
    s = re.sub(r"[^a-z ]", "", last_spoken.lower()).strip()
    if not t:
        return False
    if len(t) > 12 and t in s:
        return True  # a contiguous chunk of what it just said
    # Word-overlap check on CONTENT words only — stop-words prove nothing.
    t_content = {w for w in t.split() if w not in _STOPWORDS}
    if len(t_content) < 2:
        return False  # too little evidence — let it through rather than eat it
    s_content = {w for w in s.split() if w not in _STOPWORDS}
    return len(t_content & s_content) / len(t_content) >= 0.9

# Say any of these (as a short utterance) to close the mic completely.
SLEEP_PHRASES = ("shutdown", "shut down", "stop listening", "go to sleep", "power down")


def is_sleep_phrase(text: str) -> bool:
    """True only if the WHOLE utterance is a sleep command ('Shutdown.').

    Exact match on purpose: 'shut down the server' or 'stop listening to
    spotify' are tasks, not requests to close the microphone.
    """
    cleaned = re.sub(r"[^a-z ]", "", text.lower()).strip()
    return cleaned in SLEEP_PHRASES


class VoiceLoop(threading.Thread):
    def __init__(self, assistant: "Assistant"):
        super().__init__(daemon=True, name="jarvis-voice-loop")
        self.assistant = assistant
        self.cfg = assistant.cfg
        self.detector = WakeWordDetector(
            self.cfg.wake_word_model, self.cfg.wake_word_threshold
        )
        self._listen = threading.Event()
        self._listen.set()  # start in LISTENING mode when the loop is started
        self._stop = False
        self._load_error: str | None = None

    # --- availability ------------------------------------------------------
    @property
    def available(self) -> bool:
        return (sd is not None and self.detector.available
                and self.assistant.transcriber.available)

    def why_unavailable(self) -> str:
        if self._load_error:
            return self._load_error
        if sd is None:
            return ("Hands-free mode needs: pip install sounddevice numpy "
                    "(Linux/Pi also: sudo apt install libportaudio2)")
        if not self.detector.available:
            return self.detector.why_unavailable()
        if not self.assistant.transcriber.available:
            return "Hands-free mode needs speech-to-text: pip install faster-whisper"
        return "Hands-free mode is unavailable (unknown reason — check the log)."

    # --- state controls (called from terminal/dashboard threads) ------------
    @property
    def listening(self) -> bool:
        return self.is_alive() and self._listen.is_set()

    def ensure_started(self) -> None:
        if not self.is_alive():
            self.start()

    def wake_up(self) -> None:
        self.ensure_started()
        self._listen.set()

    def go_to_sleep(self) -> None:
        self._listen.clear()

    def shutdown_thread(self) -> None:
        self._stop = True
        self._listen.set()  # unblock the wait so the thread can exit

    # --- thread body ---------------------------------------------------------
    def run(self) -> None:
        if not self.available:
            log.warning("Voice loop not started: %s", self.why_unavailable())
            return
        try:
            self.detector.load()
        except RuntimeError as exc:
            self._load_error = str(exc)
            print(f"\n  Wake word disabled: {exc}")
            return
        # Warm the whisper model now so the first command isn't slow.
        self.assistant.transcriber.transcribe_array(
            np.zeros(SAMPLE_RATE, dtype=np.float32), SAMPLE_RATE
        )
        while not self._stop:
            self._listen.wait()  # ASLEEP: parked here with the mic device closed
            if self._stop:
                break
            try:
                self._listening_session()
            except Exception as exc:
                log.exception("Voice session crashed; retrying in 2s")
                print(f"\n  Voice loop error: {exc} — retrying. "
                      "(Set MIC_DEVICE_INDEX in .env if the mic changed.)")
                time.sleep(2)

    def _listening_session(self) -> None:
        """One LISTENING period: open the mic until sleep/stop is requested."""
        with sd.InputStream(
            samplerate=SAMPLE_RATE, channels=1, dtype="int16",
            blocksize=CHUNK_SAMPLES, device=self.cfg.mic_device_index,
        ) as stream:
            print("\n  [MIC ACTIVE — waiting for 'jarvis'; say 'shutdown' to stop]")
            self.detector.reset()
            chunk_s = CHUNK_SAMPLES / SAMPLE_RATE
            barge_run = 0.0
            last_reminder_check = 0.0
            while not self._stop and self._listen.is_set():
                chunk, _overflowed = stream.read(CHUNK_SAMPLES)
                if (self.assistant.speaker.is_speaking
                        or self.assistant.speaker.seconds_since_speech < TTS_COOLDOWN_S):
                    self.detector.reset()  # own voice / echo tail can't wake it
                    # Barge-in: sustained loud speech over the top interrupts it.
                    if self.cfg.barge_in and self.assistant.speaker.is_speaking:
                        rms = float(np.sqrt(np.mean(
                            (chunk[:, 0].astype(np.float32) / 32768.0) ** 2)))
                        barge_run = barge_run + chunk_s if rms >= BARGE_RMS else 0.0
                        if barge_run >= BARGE_SUSTAIN_S:
                            barge_run = 0.0
                            print("\n  [interrupted — go ahead]")
                            self.assistant.speaker.stop()
                            self._drain(stream)
                            self._conversation(stream, first_timeout=5.0)
                            self._drain(stream)
                            self.detector.reset()
                    continue
                barge_run = 0.0
                # Proactive: speak due reminders while idle (film-JARVIS volunteers).
                now = time.monotonic()
                if now - last_reminder_check >= REMINDER_POLL_S:
                    last_reminder_check = now
                    for msg in self.assistant.due_reminder_messages():
                        print(f"\n  REMINDER: {msg}")
                        self.assistant.record_activity("assistant", f"Reminder: {msg}")
                        self.assistant.speaker.enqueue(f"Reminder: {msg}")
                if self.detector.process(chunk[:, 0]):
                    self._handle_wake(stream)
                    self._drain(stream)
                    self.detector.reset()
        print("  [MIC OFF] Hands-free mode stopped. Type anything (or /listen) to restart it.")

    def _handle_wake(self, stream) -> None:
        print("\n  [JARVIS] Yes? (listening...)")
        self._chime()
        self._conversation(stream)

    def _conversation(self, stream, first_timeout: float = START_TIMEOUT_S) -> None:
        spoke = self._one_exchange(stream, first_timeout, first=True)
        # Conversation mode: after each spoken reply, keep listening briefly so
        # the user can respond without saying the wake word again.
        while (spoke and self.cfg.follow_up_listen
               and not self._stop and self._listen.is_set()):
            self.assistant.speaker.wait()   # let JARVIS finish talking first
            time.sleep(TTS_COOLDOWN_S)      # let the room echo die down
            self._drain(stream)             # discard everything heard so far
            print("  [still listening — reply now, or stay quiet to end]")
            spoke = self._one_exchange(stream, FOLLOW_UP_WINDOW_S, first=False)
        if not self._stop and self._listen.is_set():
            print("  [conversation closed — say 'jarvis' anytime]")

    def _one_exchange(self, stream, start_timeout: float, first: bool) -> bool:
        """Record one utterance and answer it. Returns True if a reply was spoken
        (i.e. the conversation should stay open)."""
        audio = self._record_utterance(stream, start_timeout)
        if audio is None:
            if first:
                print("  Didn't catch anything — say 'jarvis' to try again.")
            return False
        text = self.assistant.transcriber.transcribe_array(audio, SAMPLE_RATE)
        if not text:
            if first:
                print("  Couldn't make that out — say 'jarvis' and try again.")
            return False
        if not first and is_noise_transcript(text):
            return False  # background noise, not a reply — say nothing
        if looks_like_echo(text, self.assistant.speaker.last_text):
            log.info("Discarded self-echo: %r", text)
            return False  # the mic heard JARVIS's own voice — disregard it
        print(f"\nyou (voice)> {text}")
        self.assistant.record_activity("user_voice", text)
        if is_sleep_phrase(text):
            self.go_to_sleep()
            self.assistant.record_activity("assistant", "Microphone off. Type anything to re-enable.")
            self.assistant.speaker.speak("Going quiet. Type anything when you need me.")
            return False
        # Stream: speak each sentence the moment it's generated instead of
        # waiting for the whole reply to finish.
        streamed = {"n": 0}

        def speak_sentence(sentence: str) -> None:
            streamed["n"] += 1
            self.assistant.speaker.enqueue(sentence)

        reply = self.assistant.handle(text, on_sentence=speak_sentence)
        if reply.text:
            print(f"\njarvis> {reply.text}\n")
            self.assistant.record_activity("assistant", reply.text)
            if streamed["n"] > 0:
                return True  # already speaking — started mid-generation
            if reply.speak:
                self.assistant.speaker.speak(reply.spoken)
                return True
        return False

    def _record_utterance(self, stream,
                          start_timeout: float = START_TIMEOUT_S) -> "np.ndarray | None":
        """Record until you finish talking (silence-based endpointing)."""
        chunks: list = []
        started = False
        silence_run = 0.0
        voiced_s = 0.0
        chunk_s = CHUNK_SAMPLES / SAMPLE_RATE
        waited = 0.0
        # Light up the "Listening" pill while we're actually capturing you.
        self.assistant.status.set_recording(True)
        try:
            while True:
                chunk, _ = stream.read(CHUNK_SAMPLES)
                audio = chunk[:, 0].astype(np.float32) / 32768.0
                rms = float(np.sqrt(np.mean(audio ** 2)))
                if not started:
                    waited += chunk_s
                    if rms >= SPEECH_RMS:
                        started = True
                        voiced_s = chunk_s
                        chunks.append(audio)
                    elif waited >= start_timeout:
                        return None
                    continue
                chunks.append(audio)
                if rms >= SPEECH_RMS:
                    voiced_s += chunk_s
                    silence_run = 0.0
                else:
                    silence_run += chunk_s
                if silence_run >= END_SILENCE_S or len(chunks) * chunk_s >= MAX_UTTERANCE_S:
                    if voiced_s < MIN_VOICED_S:
                        return None  # a blip, not speech — don't even transcribe it
                    return np.concatenate(chunks)
        finally:
            self.assistant.status.set_recording(False)

    def _drain(self, stream) -> None:
        """Discard audio that piled up while we were transcribing/answering."""
        try:
            while stream.read_available >= CHUNK_SAMPLES:
                stream.read(CHUNK_SAMPLES)
        except Exception:
            pass

    def _chime(self) -> None:
        """Short beep so you know it's recording (best-effort)."""
        try:
            t = np.linspace(0, 0.12, int(0.12 * SAMPLE_RATE), endpoint=False)
            tone = (0.25 * np.sin(2 * np.pi * 880 * t)).astype(np.float32)
            sd.play(tone, SAMPLE_RATE, blocking=False)
        except Exception:
            pass
