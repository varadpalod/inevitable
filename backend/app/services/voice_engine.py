"""
Voice Subsystem Architecture v2.0 — Project AEGIS
===================================================
Multi-threaded, event-driven voice pipeline.

Pipeline:
  Microphone → AudioCaptureService → VAD → WakeWordDetector → SessionManager
  → SpeechRecognitionService → IntentAnalyzer → SecurityGateway → ToolRuntime → AuditLogger

Every module is an independent class with a single responsibility.
Inter-module communication uses thread-safe queues.
"""

import threading
import queue
import time
import logging
import io
import struct
import wave
import re
from enum import Enum, auto
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
import sounddevice as sd
import speech_recognition as sr

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Shared Data Types
# ─────────────────────────────────────────────────────────────────────────────

class SessionState(Enum):
    IDLE = auto()
    LISTENING = auto()
    AUTHENTICATING = auto()
    COMMAND = auto()
    EXECUTING = auto()


@dataclass
class AudioFrame:
    """A chunk of raw PCM audio with metadata."""
    samples: np.ndarray          # float32, mono
    sample_rate: int
    timestamp: float = field(default_factory=time.time)


@dataclass
class SpeechSegment:
    """A complete utterance extracted by VAD."""
    audio: np.ndarray            # float32, mono, concatenated frames
    sample_rate: int
    duration_sec: float
    timestamp: float = field(default_factory=time.time)


@dataclass
class Intent:
    """Structured intent parsed from user speech."""
    action: str                  # e.g. "READ_FILE", "DELETE_FILE", "WEATHER", "CHAT"
    target: str = ""             # e.g. "system_config.txt"
    raw_text: str = ""
    required_level: int = 0
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AuditEntry:
    """A single audit trail record."""
    timestamp: str
    user: str
    intent: str
    auth_method: str
    tool: str
    result: str
    duration_sec: float = 0.0


@dataclass
class VoicePipelineEvent:
    """Generic event published to subscribers."""
    event_type: str              # e.g. "WAKE_WORD", "COMMAND_READY", "AUTH_REQUIRED"
    payload: Dict[str, Any] = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Audio Capture Service
# ─────────────────────────────────────────────────────────────────────────────

class AudioCaptureService:
    """
    Continuously records audio from the system microphone using sounddevice InputStream.
    Pushes AudioFrame objects into a shared queue. Never performs recognition or auth.

    Key design decisions:
    - Uses the device's NATIVE sample rate (typically 44100/48000Hz for Realtek)
      instead of forcing 16000Hz which many laptop mics don't support and causes
      the stream to repeatedly fail/restart (mic on/off every second).
    - Applies software gain amplification because Realtek mic arrays on Windows
      typically deliver extremely quiet signals (~0.000015 RMS raw).
    - Exposes real-time RMS and peak values for the UI debug volume meter.
    """

    # Software gain multiplier — Realtek arrays on Windows typically need 100-200x
    SOFTWARE_GAIN = 150.0

    def __init__(self, audio_queue: queue.Queue, sample_rate: Optional[int] = None,
                 block_size: int = 2048, device_index: Optional[int] = None):
        self._audio_queue = audio_queue
        self._requested_sample_rate = sample_rate  # None = auto-detect native rate
        self.sample_rate = sample_rate or 44100     # will be overridden on start
        self.block_size = block_size
        self.device_index = device_index
        self._stream: Optional[sd.InputStream] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None

        # Real-time monitoring (read by status API)
        self.current_rms: float = 0.0
        self.current_peak: float = 0.0
        self.frames_captured: int = 0
        self._rms_lock = threading.Lock()

    # ── public API ──

    def start(self):
        if self._running:
            return
        if self.device_index is None:
            self.device_index = self._discover_mic()
        # Detect native sample rate
        if self._requested_sample_rate is None:
            self.sample_rate = self._get_native_sample_rate(self.device_index)
        else:
            self.sample_rate = self._requested_sample_rate
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True, name="AudioCapture")
        self._thread.start()
        logger.info(
            f"[AudioCapture] Started on device #{self.device_index} "
            f"@ {self.sample_rate}Hz (gain={self.SOFTWARE_GAIN}x)"
        )

    def stop(self):
        self._running = False
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
        logger.info("[AudioCapture] Stopped")

    @property
    def is_running(self) -> bool:
        return self._running

    def get_levels(self) -> Dict[str, float]:
        """Returns current audio levels for UI debug meter."""
        with self._rms_lock:
            return {
                "rms": self.current_rms,
                "peak": self.current_peak,
                "rms_raw": self.current_rms / max(self.SOFTWARE_GAIN, 1),
                "frames_captured": self.frames_captured,
            }

    # ── internals ──

    def _run(self):
        """Opens the mic stream ONCE and keeps it alive. Retries on failure."""
        retry_count = 0
        while self._running and retry_count < 5:
            try:
                logger.info(f"[AudioCapture] Opening stream (attempt {retry_count + 1})...")
                self._stream = sd.InputStream(
                    samplerate=self.sample_rate,
                    blocksize=self.block_size,
                    device=self.device_index,
                    channels=1,
                    dtype="float32",
                    callback=self._audio_callback,
                )
                self._stream.start()
                logger.info("[AudioCapture] Stream opened successfully — mic is live")
                retry_count = 0  # reset on success
                while self._running:
                    time.sleep(0.1)
                # Clean exit
                break
            except Exception as e:
                retry_count += 1
                logger.error(
                    f"[AudioCapture] Stream error (attempt {retry_count}): {e}. "
                    f"Retrying in 2s..."
                )
                time.sleep(2)

        if retry_count >= 5:
            logger.error("[AudioCapture] Max retries reached. Mic capture disabled.")
            self._running = False

    def _audio_callback(self, indata, frames, time_info, status):
        if status:
            logger.warning(f"[AudioCapture] Stream status: {status}")

        raw_samples = indata[:, 0].copy()

        # Apply software gain amplification
        amplified = raw_samples * self.SOFTWARE_GAIN
        np.clip(amplified, -1.0, 1.0, out=amplified)

        # Update real-time monitoring levels
        rms = float(np.sqrt(np.mean(amplified ** 2)))
        peak = float(np.max(np.abs(amplified)))
        with self._rms_lock:
            self.current_rms = rms
            self.current_peak = peak
            self.frames_captured += 1

        frame = AudioFrame(
            samples=amplified,
            sample_rate=self.sample_rate,
        )
        try:
            self._audio_queue.put_nowait(frame)
        except queue.Full:
            pass  # drop frames silently to avoid blocking the audio thread

    def _discover_mic(self) -> Optional[int]:
        """Auto-select the best hardware input device."""
        try:
            devices = sd.query_devices()
            # Prefer "Microphone Array" style devices
            for idx, dev in enumerate(devices):
                if dev["max_input_channels"] > 0 and "microphone" in dev["name"].lower():
                    logger.info(f"[AudioCapture] Auto-selected mic #{idx}: {dev['name']}")
                    return idx
            # Fallback to default
            default = sd.default.device[0]
            if default is not None and default >= 0:
                logger.info(f"[AudioCapture] Using system default input #{default}")
                return int(default)
        except Exception as e:
            logger.warning(f"[AudioCapture] Mic discovery failed: {e}")
        return None

    @staticmethod
    def _get_native_sample_rate(device_index: Optional[int]) -> int:
        """Query the device's native/default sample rate instead of guessing."""
        try:
            if device_index is not None:
                info = sd.query_devices(device_index)
                rate = int(info.get("default_samplerate", 44100))
                logger.info(f"[AudioCapture] Device #{device_index} native rate: {rate}Hz")
                return rate
        except Exception as e:
            logger.warning(f"[AudioCapture] Could not query native rate: {e}")
        return 44100  # safe fallback for most Realtek devices


# ─────────────────────────────────────────────────────────────────────────────
# 2. Voice Activity Detector (VAD)
# ─────────────────────────────────────────────────────────────────────────────

class VoiceActivityDetector:
    """
    Consumes AudioFrames, evaluates RMS energy.
    Groups consecutive above-threshold frames into SpeechSegments
    and pushes them to speech_queue when silence is detected again.
    """

    def __init__(self, audio_queue: queue.Queue, speech_queue: queue.Queue,
                 energy_threshold: float = 0.0020, silence_frames: int = 30,
                 min_speech_frames: int = 3):
        self._audio_queue = audio_queue
        self._speech_queue = speech_queue
        self.energy_threshold = energy_threshold  # Tuned for gain-amplified Realtek signal
        self.silence_frames = silence_frames       # ~1.9s of silence at 2048-block/44100Hz
        self.min_speech_frames = min_speech_frames  # minimum ~0.14s of speech
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._is_speech_active = False
        self.current_rms: float = 0.0  # exposed for monitoring

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True, name="VAD")
        self._thread.start()
        logger.info("[VAD] Started")

    def stop(self):
        self._running = False
        logger.info("[VAD] Stopped")

    @property
    def is_speech_active(self) -> bool:
        return self._is_speech_active

    def _run(self):
        buffer: List[np.ndarray] = []
        silence_count = 0
        sample_rate = 16000

        while self._running:
            try:
                frame: AudioFrame = self._audio_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            sample_rate = frame.sample_rate
            rms = float(np.sqrt(np.mean(frame.samples ** 2)))
            self.current_rms = rms  # expose for monitoring

            if rms >= self.energy_threshold:
                # Speech detected
                self._is_speech_active = True
                buffer.append(frame.samples)
                silence_count = 0
            else:
                if buffer:
                    silence_count += 1
                    buffer.append(frame.samples)  # include trailing silence
                    if silence_count >= self.silence_frames:
                        # End of utterance
                        self._is_speech_active = False
                        if len(buffer) >= self.min_speech_frames:
                            concatenated = np.concatenate(buffer)
                            segment = SpeechSegment(
                                audio=concatenated,
                                sample_rate=sample_rate,
                                duration_sec=len(concatenated) / sample_rate,
                            )
                            try:
                                self._speech_queue.put_nowait(segment)
                                logger.info(f"[VAD] Speech segment captured: {segment.duration_sec:.2f}s")
                            except queue.Full:
                                logger.warning("[VAD] Speech queue full, dropping segment")
                        buffer.clear()
                        silence_count = 0


# ─────────────────────────────────────────────────────────────────────────────
# 3. Wake Word Detector
# ─────────────────────────────────────────────────────────────────────────────

class WakeWordDetector:
    """
    Listens for the wake word in SpeechSegments.
    Performs quick STT on short segments and checks for wake phrases.
    When detected, publishes a WAKE_WORD event and routes the audio onwards.
    """

    WAKE_PHRASES = ["jarvis", "hey jarvis", "hello jarvis", "okay jarvis", "ok jarvis", "javis"]

    def __init__(self, speech_queue: queue.Queue, command_queue: queue.Queue,
                 on_wake_word: Optional[Callable] = None):
        self._speech_queue = speech_queue
        self._command_queue = command_queue
        self._on_wake_word = on_wake_word
        self._recognizer = sr.Recognizer()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self.last_detection_text: str = ""

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True, name="WakeWord")
        self._thread.start()
        logger.info("[WakeWord] Started — listening for 'Hey Jarvis'")

    def stop(self):
        self._running = False
        logger.info("[WakeWord] Stopped")

    def _run(self):
        while self._running:
            try:
                segment: SpeechSegment = self._speech_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            text = self._quick_transcribe(segment)
            if not text:
                continue

            lower = text.lower()
            logger.info(f"[WakeWord] Heard: '{text}'")

            if any(phrase in lower for phrase in self.WAKE_PHRASES):
                logger.info(">>> WAKE WORD DETECTED <<<")
                self.last_detection_text = text

                # Strip wake word prefix to get the trailing command (if any)
                command_part = lower
                for phrase in sorted(self.WAKE_PHRASES, key=len, reverse=True):
                    if phrase in command_part:
                        command_part = command_part.replace(phrase, "").strip(" ,.")
                        break

                event = VoicePipelineEvent(
                    event_type="WAKE_WORD",
                    payload={
                        "raw_text": text,
                        "command_fragment": command_part,
                        "audio_segment": segment,
                    },
                )

                try:
                    self._command_queue.put_nowait(event)
                except queue.Full:
                    pass

                if self._on_wake_word:
                    try:
                        self._on_wake_word(text)
                    except Exception as e:
                        logger.error(f"[WakeWord] Callback error: {e}")

    def _quick_transcribe(self, segment: SpeechSegment) -> str:
        """Convert a speech segment to text using Google Web STT."""
        try:
            wav_bytes = self._to_wav_bytes(segment.audio, segment.sample_rate)
            audio = sr.AudioData(wav_bytes, segment.sample_rate, 2)  # 16-bit PCM
            text = self._recognizer.recognize_google(audio)
            return text
        except sr.UnknownValueError:
            return ""
        except sr.RequestError as e:
            logger.warning(f"[WakeWord] STT API unavailable: {e}")
            return ""
        except Exception as e:
            logger.error(f"[WakeWord] Transcribe error: {e}")
            return ""

    @staticmethod
    def _to_wav_bytes(audio: np.ndarray, sample_rate: int) -> bytes:
        """Convert float32 numpy audio to 16-bit PCM WAV bytes."""
        pcm = (audio * 32767).astype(np.int16)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(pcm.tobytes())
        return buf.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# 4. Session Manager
# ─────────────────────────────────────────────────────────────────────────────

class VoiceSessionManager:
    """
    State machine controlling the assistant lifecycle.
    States: IDLE → LISTENING → AUTHENTICATING → COMMAND → EXECUTING → IDLE
    Contains NO business logic — only state transitions.
    """

    def __init__(self):
        self._state = SessionState.IDLE
        self._lock = threading.Lock()
        self._listeners: List[Callable] = []
        self.session_id: Optional[str] = None
        self.auth_level: int = 0

    @property
    def state(self) -> SessionState:
        with self._lock:
            return self._state

    def transition(self, new_state: SessionState):
        with self._lock:
            old = self._state
            self._state = new_state
            logger.info(f"[SessionManager] {old.name} → {new_state.name}")
        for cb in self._listeners:
            try:
                cb(old, new_state)
            except Exception as e:
                logger.error(f"[SessionManager] Listener error: {e}")

    def on_transition(self, callback: Callable):
        self._listeners.append(callback)

    def bind_session(self, session_id: str, auth_level: int):
        self.session_id = session_id
        self.auth_level = auth_level


# ─────────────────────────────────────────────────────────────────────────────
# 5. Speech Recognition Service
# ─────────────────────────────────────────────────────────────────────────────

class SpeechRecognitionService:
    """
    Converts speech audio into text. Nothing else.
    Replacement-friendly: swap Google STT for Whisper without touching other modules.
    """

    def __init__(self):
        self._recognizer = sr.Recognizer()

    def transcribe(self, segment: SpeechSegment) -> str:
        """Returns transcribed text or empty string on failure."""
        try:
            wav_bytes = WakeWordDetector._to_wav_bytes(segment.audio, segment.sample_rate)
            audio = sr.AudioData(wav_bytes, segment.sample_rate, 2)
            text = self._recognizer.recognize_google(audio)
            logger.info(f"[STT] Transcribed: '{text}'")
            return text
        except sr.UnknownValueError:
            logger.info("[STT] Could not understand audio")
            return ""
        except sr.RequestError as e:
            logger.warning(f"[STT] API error: {e}")
            return ""
        except Exception as e:
            logger.error(f"[STT] Error: {e}")
            return ""


# ─────────────────────────────────────────────────────────────────────────────
# 6. Intent Analyzer
# ─────────────────────────────────────────────────────────────────────────────

class IntentAnalyzer:
    """
    Translates natural language text into structured Intent objects.
    No execution — only understanding.
    """

    # keyword → (action, required_level)
    _RULES = [
        # Level 4 — Vault
        (["vault", "secret", "credentials", "api key", "password"], "READ_VAULT", 4),
        # Level 3 — Admin
        (["uninstall", "system configuration", "admin settings", "reboot"], "ADMIN_ACTION", 3),
        # Level 2 — Write/Delete
        (["write file", "save file", "execute script", "run code"], "WRITE_FILE", 2),
        (["delete file", "remove file", "rm "], "DELETE_FILE", 2),
        # Level 1 — Read
        (["read file", "list files", "search files", "open file"], "READ_FILE", 1),
        (["calendar", "emails", "schedule"], "READ_DATA", 1),
        # Level 0 — Public
        (["weather", "forecast"], "WEATHER", 0),
        (["news", "headlines"], "NEWS", 0),
        (["search", "browse", "look up"], "WEB_SEARCH", 0),
    ]

    def analyze(self, text: str) -> Intent:
        lower = text.lower()

        for keywords, action, level in self._RULES:
            if any(kw in lower for kw in keywords):
                target = self._extract_target(lower, action)
                return Intent(action=action, target=target, raw_text=text, required_level=level)

        return Intent(action="CHAT", raw_text=text, required_level=0)

    @staticmethod
    def _extract_target(text: str, action: str) -> str:
        """Best-effort extraction of the target argument from the command."""
        if action in ("READ_FILE", "WRITE_FILE", "DELETE_FILE"):
            match = re.search(r"(?:file|open)\s+([\w.\-/]+)", text)
            if match:
                return match.group(1)
        return ""


# ─────────────────────────────────────────────────────────────────────────────
# 7. Security Gateway
# ─────────────────────────────────────────────────────────────────────────────

class VoiceSecurityGateway:
    """
    The single authority that decides Allow / Reject / Require-Auth.
    Receives an Intent + current auth level and returns a security verdict.
    """

    @dataclass
    class Verdict:
        allowed: bool
        require_voice: bool = False
        require_face: bool = False
        require_pin: bool = False
        require_confirmation: bool = False
        reason: str = ""

    def evaluate(self, intent: Intent, current_level: int) -> "VoiceSecurityGateway.Verdict":
        if current_level >= intent.required_level:
            return self.Verdict(allowed=True, reason="Sufficient clearance")

        # Determine what auth is still needed
        v = self.Verdict(allowed=False)
        gap = intent.required_level - current_level

        if current_level < 1:
            v.require_voice = True
        if intent.required_level >= 2 and current_level < 2:
            v.require_pin = True
        if intent.required_level >= 3 and current_level < 3:
            v.require_face = True
        if intent.required_level >= 4:
            v.require_confirmation = True

        v.reason = (
            f"Action '{intent.action}' requires Level {intent.required_level}; "
            f"current session is Level {current_level}."
        )
        logger.info(f"[SecurityGateway] BLOCKED: {v.reason}")
        return v


# ─────────────────────────────────────────────────────────────────────────────
# 8. Voice Authentication Service
# ─────────────────────────────────────────────────────────────────────────────

class VoiceAuthenticationService:
    """
    Speaker verification — completely independent of speech recognition.
    Answers "WHO said it?", not "WHAT was said?"
    Phase 1: simulated confidence matching.
    """

    def verify(self, audio: np.ndarray, enrolled_user_id: str) -> Dict[str, Any]:
        """Compare speaker embedding against enrolled template."""
        logger.info(f"[VoiceAuth] Verifying speaker for user {enrolled_user_id}")
        # Simulate embedding comparison
        time.sleep(0.3)
        if len(audio) > 1000:
            return {"authenticated": True, "confidence": 0.97, "method": "voice_embedding"}
        return {"authenticated": False, "confidence": 0.0, "method": "voice_embedding"}


# ─────────────────────────────────────────────────────────────────────────────
# 9. Face Authentication Service
# ─────────────────────────────────────────────────────────────────────────────

class FaceAuthenticationService:
    """
    On-demand facial verification. Camera activates ONLY when invoked.
    Phase 1: simulated matching.
    """

    def verify(self, user_id: str) -> Dict[str, Any]:
        """Capture frame from camera and compare against enrolled face template."""
        logger.info(f"[FaceAuth] Activating camera for user {user_id}")
        time.sleep(0.5)  # simulate capture + inference
        logger.info("[FaceAuth] Camera deactivated")
        return {"authenticated": True, "confidence": 0.98, "method": "face_recognition"}


# ─────────────────────────────────────────────────────────────────────────────
# 10. Tool Registry & Tool Runtime
# ─────────────────────────────────────────────────────────────────────────────

class ToolDescriptor:
    """Describes a registered tool's capabilities and constraints."""

    def __init__(self, name: str, required_level: int, handler: Callable,
                 description: str = "", rollback: Optional[Callable] = None):
        self.name = name
        self.required_level = required_level
        self.handler = handler
        self.description = description
        self.rollback = rollback


class ToolRegistry:
    """
    Central registry of all available tools.
    Adding a new tool requires only registration — no planner changes.
    """

    def __init__(self):
        self._tools: Dict[str, ToolDescriptor] = {}

    def register(self, tool: ToolDescriptor):
        self._tools[tool.name] = tool
        logger.info(f"[ToolRegistry] Registered tool '{tool.name}' (level {tool.required_level})")

    def get(self, name: str) -> Optional[ToolDescriptor]:
        return self._tools.get(name)

    def list_tools(self) -> List[str]:
        return list(self._tools.keys())


class ToolRuntime:
    """
    The ONLY module allowed to touch the operating system.
    Executes pre-authorized tool calls. Never makes permission decisions.
    """

    def __init__(self, registry: ToolRegistry):
        self._registry = registry

    def execute(self, tool_name: str, **kwargs) -> Dict[str, Any]:
        descriptor = self._registry.get(tool_name)
        if descriptor is None:
            return {"success": False, "output": f"Unknown tool: {tool_name}"}

        start = time.time()
        try:
            result = descriptor.handler(**kwargs)
            elapsed = time.time() - start
            logger.info(f"[ToolRuntime] '{tool_name}' completed in {elapsed:.3f}s")
            return {"success": True, "output": result, "duration_sec": elapsed}
        except Exception as e:
            elapsed = time.time() - start
            logger.error(f"[ToolRuntime] '{tool_name}' failed: {e}")
            return {"success": False, "output": str(e), "duration_sec": elapsed}


# ─────────────────────────────────────────────────────────────────────────────
# 11. Audit Logger
# ─────────────────────────────────────────────────────────────────────────────

class VoiceAuditLogger:
    """
    Records every privileged action into an immutable in-memory log
    and optionally writes to the database audit table.
    """

    def __init__(self):
        self._log: List[AuditEntry] = []
        self._lock = threading.Lock()
        self._db_writer: Optional[Callable] = None

    def set_db_writer(self, writer: Callable):
        """Inject a callable that persists entries to the database."""
        self._db_writer = writer

    def record(self, entry: AuditEntry):
        with self._lock:
            self._log.append(entry)
        logger.info(
            f"[Audit] {entry.timestamp} | {entry.user} | {entry.intent} | "
            f"Auth:{entry.auth_method} | Tool:{entry.tool} | {entry.result} | {entry.duration_sec:.2f}s"
        )
        if self._db_writer:
            try:
                self._db_writer(entry)
            except Exception as e:
                logger.error(f"[Audit] DB write failed: {e}")

    def get_recent(self, n: int = 20) -> List[AuditEntry]:
        with self._lock:
            return list(self._log[-n:])


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline Orchestrator
# ─────────────────────────────────────────────────────────────────────────────

class VoicePipeline:
    """
    Wires all modules together. Each module owns its own thread.
    The pipeline is started/stopped as a unit.
    """

    def __init__(self, device_index: Optional[int] = None):
        # Shared queues
        self._audio_queue = queue.Queue(maxsize=200)
        self._speech_queue = queue.Queue(maxsize=20)
        self._command_queue = queue.Queue(maxsize=10)

        # Modules — sample_rate=None means auto-detect native rate
        self.audio_capture = AudioCaptureService(
            self._audio_queue, sample_rate=None, device_index=device_index
        )
        self.vad = VoiceActivityDetector(self._audio_queue, self._speech_queue)
        self.wake_word = WakeWordDetector(self._speech_queue, self._command_queue)
        self.session_manager = VoiceSessionManager()
        self.stt = SpeechRecognitionService()
        self.intent_analyzer = IntentAnalyzer()
        self.security_gateway = VoiceSecurityGateway()
        self.voice_auth = VoiceAuthenticationService()
        self.face_auth = FaceAuthenticationService()
        self.audit_logger = VoiceAuditLogger()

        # Tool Registry
        self.tool_registry = ToolRegistry()
        self.tool_runtime = ToolRuntime(self.tool_registry)

        # Command processing thread
        self._cmd_thread: Optional[threading.Thread] = None
        self._running = False

        # External callbacks
        self._on_command_result: Optional[Callable] = None
        self._on_wake_word: Optional[Callable] = None

        # Public status fields (polled by API)
        self.live_transcript: str = ""
        self.last_event: str = "IDLE"
        self.pipeline_log: List[str] = []

    # ── public API ──

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def mic_device_index(self) -> Optional[int]:
        return self.audio_capture.device_index

    def set_on_wake_word(self, callback: Callable):
        self._on_wake_word = callback
        self.wake_word._on_wake_word = callback

    def set_on_command_result(self, callback: Callable):
        self._on_command_result = callback

    def start(self):
        if self._running:
            return
        self._running = True

        self.audio_capture.start()
        self.vad.start()
        self.wake_word.start()

        self._cmd_thread = threading.Thread(target=self._command_loop, daemon=True, name="CmdProcessor")
        self._cmd_thread.start()

        self.session_manager.transition(SessionState.IDLE)
        self.last_event = "PIPELINE_STARTED"
        self._log("Voice Pipeline v2.0 started — all threads active")
        logger.info("[Pipeline] All modules started")

    def stop(self):
        self._running = False
        self.audio_capture.stop()
        self.vad.stop()
        self.wake_word.stop()
        self.session_manager.transition(SessionState.IDLE)
        self.last_event = "PIPELINE_STOPPED"
        self._log("Voice Pipeline stopped")
        logger.info("[Pipeline] All modules stopped")

    def get_status(self) -> Dict[str, Any]:
        levels = self.audio_capture.get_levels() if self._running else {"rms": 0, "peak": 0, "rms_raw": 0, "frames_captured": 0}
        return {
            "is_running": self._running,
            "mic_device_index": self.audio_capture.device_index,
            "sample_rate": self.audio_capture.sample_rate,
            "software_gain": AudioCaptureService.SOFTWARE_GAIN,
            "state": self.session_manager.state.name,
            "last_event": self.last_event,
            "live_transcript": self.live_transcript,
            "vad_active": self.vad.is_speech_active if self._running else False,
            "vad_rms": self.vad.current_rms if self._running else 0,
            "vad_threshold": self.vad.energy_threshold,
            "mic_rms": levels["rms"],
            "mic_peak": levels["peak"],
            "mic_rms_raw": levels["rms_raw"],
            "frames_captured": levels["frames_captured"],
            "audio_queue_size": self._audio_queue.qsize(),
            "speech_queue_size": self._speech_queue.qsize(),
            "pipeline_log": self.pipeline_log[-10:],
        }

    # ── command processing loop (Thread) ──

    def _command_loop(self):
        """
        Processes WAKE_WORD events from the command_queue.
        Runs the full intent→security→execute pipeline.
        """
        while self._running:
            try:
                event: VoicePipelineEvent = self._command_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            if event.event_type != "WAKE_WORD":
                continue

            self.session_manager.transition(SessionState.LISTENING)
            self.last_event = "WAKE_WORD_DETECTED"
            raw_text = event.payload.get("raw_text", "")
            command_fragment = event.payload.get("command_fragment", "")
            audio_segment: Optional[SpeechSegment] = event.payload.get("audio_segment")

            self._log(f"Wake word detected: '{raw_text}'")

            # If there is a command fragment after the wake word, use it directly
            # Otherwise, listen for the next utterance as the command
            command_text = command_fragment
            if not command_text:
                self._log("Listening for command...")
                self.session_manager.transition(SessionState.COMMAND)
                # Wait for next speech segment
                try:
                    next_segment: SpeechSegment = self._speech_queue.get(timeout=8.0)
                    command_text = self.stt.transcribe(next_segment)
                    audio_segment = next_segment
                except queue.Empty:
                    self._log("No command heard — returning to IDLE")
                    self.session_manager.transition(SessionState.IDLE)
                    self.last_event = "IDLE"
                    continue

            if not command_text:
                self._log("Could not understand command — returning to IDLE")
                self.session_manager.transition(SessionState.IDLE)
                self.last_event = "IDLE"
                continue

            self.live_transcript = command_text
            self._log(f"Command transcribed: '{command_text}'")

            # Intent Analysis
            intent = self.intent_analyzer.analyze(command_text)
            self._log(f"Intent: {intent.action} | Target: '{intent.target}' | Required Level: {intent.required_level}")

            # Security Gateway check
            verdict = self.security_gateway.evaluate(intent, self.session_manager.auth_level)

            if not verdict.allowed:
                self.session_manager.transition(SessionState.AUTHENTICATING)
                self.last_event = "AUTH_REQUIRED"
                self._log(f"Security Gateway BLOCKED: {verdict.reason}")

                # Attempt automatic voice auth if needed
                auth_methods_used = []
                if verdict.require_voice and audio_segment is not None:
                    vauth = self.voice_auth.verify(audio_segment.audio, "current_user")
                    if vauth["authenticated"]:
                        self.session_manager.auth_level = max(self.session_manager.auth_level, 1)
                        auth_methods_used.append(f"Voice ({vauth['confidence']:.0%})")
                        self._log(f"Voice auth passed: {vauth['confidence']:.0%}")

                # Re-evaluate after automatic auth
                verdict = self.security_gateway.evaluate(intent, self.session_manager.auth_level)
                if not verdict.allowed:
                    self._log(f"Still blocked — manual elevation required (PIN/Face/Vault)")
                    self.last_event = "ELEVATION_REQUIRED"

                    self.audit_logger.record(AuditEntry(
                        timestamp=datetime.now().isoformat(),
                        user=self.session_manager.session_id or "unknown",
                        intent=intent.action,
                        auth_method=", ".join(auth_methods_used) or "none",
                        tool="none",
                        result=f"BLOCKED — Level {intent.required_level} required",
                    ))

                    if self._on_command_result:
                        self._on_command_result({
                            "status": "UPGRADE_REQUIRED",
                            "text": command_text,
                            "intent": intent.action,
                            "required_level": intent.required_level,
                            "current_level": self.session_manager.auth_level,
                        })
                    self.session_manager.transition(SessionState.IDLE)
                    continue

            # Execute via Tool Runtime
            self.session_manager.transition(SessionState.EXECUTING)
            self.last_event = "EXECUTING"
            self._log(f"Executing intent '{intent.action}' via Tool Runtime")

            tool_name = self._intent_to_tool(intent.action)
            result = self.tool_runtime.execute(tool_name, intent=intent)

            auth_desc = f"Level {self.session_manager.auth_level}"
            self.audit_logger.record(AuditEntry(
                timestamp=datetime.now().isoformat(),
                user=self.session_manager.session_id or "unknown",
                intent=intent.action,
                auth_method=auth_desc,
                tool=tool_name,
                result="SUCCESS" if result["success"] else "FAILED",
                duration_sec=result.get("duration_sec", 0),
            ))

            self._log(f"Execution result: {result.get('output', '')[:100]}")
            self.last_event = "COMMAND_COMPLETE"

            if self._on_command_result:
                self._on_command_result({
                    "status": "SUCCESS" if result["success"] else "FAILED",
                    "text": command_text,
                    "intent": intent.action,
                    "output": result.get("output", ""),
                })

            self.session_manager.transition(SessionState.IDLE)

    @staticmethod
    def _intent_to_tool(action: str) -> str:
        mapping = {
            "READ_FILE": "file_read",
            "WRITE_FILE": "file_write",
            "DELETE_FILE": "file_delete",
            "READ_VAULT": "vault_read",
            "WEATHER": "browser_search",
            "NEWS": "browser_search",
            "WEB_SEARCH": "browser_search",
            "ADMIN_ACTION": "admin_tool",
            "CHAT": "assistant_chat",
            "READ_DATA": "assistant_chat",
        }
        return mapping.get(action, "assistant_chat")

    def _log(self, message: str):
        entry = f"[{datetime.now().strftime('%H:%M:%S')}] {message}"
        self.pipeline_log.append(entry)
        # Keep last 50 entries
        if len(self.pipeline_log) > 50:
            self.pipeline_log = self.pipeline_log[-50:]
        logger.info(f"[Pipeline] {message}")


# ─────────────────────────────────────────────────────────────────────────────
# Module-level singleton (replaces old voice_engine global)
# ─────────────────────────────────────────────────────────────────────────────

voice_pipeline = VoicePipeline()

# Register default tools from the agents module
try:
    from app.services.agents import file_agent, browser_agent, coding_agent, vault_agent

    voice_pipeline.tool_registry.register(ToolDescriptor(
        name="file_read", required_level=1, description="Read a file from sandbox",
        handler=lambda intent=None, **kw: file_agent.execute("read", intent.target if intent else "default.txt"),
    ))
    voice_pipeline.tool_registry.register(ToolDescriptor(
        name="file_write", required_level=2, description="Write a file in sandbox",
        handler=lambda intent=None, **kw: file_agent.execute("write", intent.target if intent else "output.txt", intent.extra.get("content", "data") if intent else "data"),
    ))
    voice_pipeline.tool_registry.register(ToolDescriptor(
        name="file_delete", required_level=2, description="Delete a file from sandbox",
        handler=lambda intent=None, **kw: file_agent.execute("delete", intent.target if intent else "temp.txt"),
    ))
    voice_pipeline.tool_registry.register(ToolDescriptor(
        name="vault_read", required_level=4, description="Read secrets from vault",
        handler=lambda **kw: vault_agent.execute("read_secrets"),
    ))
    voice_pipeline.tool_registry.register(ToolDescriptor(
        name="browser_search", required_level=0, description="Web search",
        handler=lambda intent=None, **kw: browser_agent.execute("search", intent.raw_text if intent else "general query"),
    ))
    voice_pipeline.tool_registry.register(ToolDescriptor(
        name="admin_tool", required_level=3, description="Administrative system action",
        handler=lambda intent=None, **kw: f"[Admin] Simulated admin action: {intent.raw_text if intent else 'N/A'}",
    ))
    voice_pipeline.tool_registry.register(ToolDescriptor(
        name="assistant_chat", required_level=0, description="General AI chat",
        handler=lambda intent=None, **kw: f"[Assistant] Processed: {intent.raw_text if intent else 'Hello'}",
    ))
except ImportError as e:
    logger.warning(f"[Pipeline] Could not register default tools: {e}")

# Backward compatibility alias
voice_engine = voice_pipeline
