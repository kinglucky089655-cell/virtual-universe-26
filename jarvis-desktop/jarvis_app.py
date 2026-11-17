#!/usr/bin/env python3
"""macOS desktop assistant with local wake-word detection and optional AI."""

from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
import time
import tkinter as tk
from tkinter import scrolledtext, ttk
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel
from openwakeword.model import Model
from openwakeword.utils import download_models

SAMPLE_RATE = 16_000
FRAME_SAMPLES = 1_280  # 80 ms at 16 kHz
FRAME_SECONDS = FRAME_SAMPLES / SAMPLE_RATE
WAKE_THRESHOLD = float(os.getenv("JARVIS_WAKE_THRESHOLD", "0.5"))
WHISPER_MODEL = os.getenv("JARVIS_WHISPER_MODEL", "base")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
MACOS_VOICE = os.getenv("JARVIS_VOICE", "")  # Empty uses the macOS default voice.


class JarvisApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Jarvis Desktop Assistant")
        self.root.geometry("700x560")
        self.root.minsize(520, 420)

        self.audio_queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=80)
        self.stop_event = threading.Event()
        self.worker: threading.Thread | None = None
        self.audio_stream: sd.InputStream | None = None
        self.listening = False
        self.speaking_lock = threading.Lock()
        self.whisper: WhisperModel | None = None
        self.history: list[dict[str, str]] = []

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def _build_ui(self) -> None:
        container = ttk.Frame(self.root, padding=16)
        container.pack(fill=tk.BOTH, expand=True)
        ttk.Label(container, text="JARVIS", font=("TkDefaultFont", 22, "bold")).pack(anchor="w")
        ttk.Label(
            container,
            text='Click Start listening, then say “Hey Jarvis” followed by your command.',
        ).pack(anchor="w", pady=(2, 12))
        self.transcript = scrolledtext.ScrolledText(
            container, wrap=tk.WORD, state=tk.DISABLED, height=18
        )
        self.transcript.pack(fill=tk.BOTH, expand=True)

        entry_row = ttk.Frame(container)
        entry_row.pack(fill=tk.X, pady=(12, 8))
        self.command_entry = ttk.Entry(entry_row)
        self.command_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.command_entry.bind("<Return>", lambda _event: self.send_typed_command())
        ttk.Button(entry_row, text="Send", command=self.send_typed_command).pack(
            side=tk.LEFT, padx=(8, 0)
        )

        controls = ttk.Frame(container)
        controls.pack(fill=tk.X)
        self.start_button = ttk.Button(controls, text="Start listening", command=self.start)
        self.start_button.pack(side=tk.LEFT)
        self.stop_button = ttk.Button(controls, text="Stop", command=self.stop, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=8)
        self.status = tk.StringVar(value="Stopped")
        ttk.Label(controls, textvariable=self.status).pack(side=tk.LEFT, padx=8)

        if not os.getenv("OPENAI_API_KEY"):
            self._append(
                "Jarvis",
                "Set OPENAI_API_KEY in Terminal before launching for AI answers. "
                "Time/date and typed commands work without it.",
            )

    def _ui(self, callback, *args) -> None:
        try:
            self.root.after(0, callback, *args)
        except tk.TclError:
            pass

    def _append(self, speaker: str, text: str) -> None:
        self.transcript.configure(state=tk.NORMAL)
        self.transcript.insert(tk.END, f"{speaker}: {text}\n\n")
        self.transcript.see(tk.END)
        self.transcript.configure(state=tk.DISABLED)

    def _set_status(self, text: str) -> None:
        self.status.set(text)

    def start(self) -> None:
        if self.listening:
            return
        self.stop_event.clear()
        self.listening = True
        self.start_button.configure(state=tk.DISABLED)
        self.stop_button.configure(state=tk.NORMAL)
        self._set_status("Loading local wake-word model…")
        self.worker = threading.Thread(target=self._listen_loop, daemon=True)
        self.worker.start()

    def stop(self) -> None:
        self.listening = False
        self.stop_event.set()
        if self.audio_stream is not None:
            try:
                self.audio_stream.stop()
                self.audio_stream.close()
            except Exception:
                pass
            self.audio_stream = None
        self.start_button.configure(state=tk.NORMAL)
        self.stop_button.configure(state=tk.DISABLED)
        self._set_status("Stopped")

    def _audio_callback(self, indata, _frames, _time_info, status) -> None:
        if status:
            self._ui(self._set_status, f"Audio: {status}")
        samples = np.asarray(indata[:, 0], dtype=np.float32).copy()
        try:
            self.audio_queue.put_nowait(samples)
        except queue.Full:
            try:
                self.audio_queue.get_nowait()
                self.audio_queue.put_nowait(samples)
            except (queue.Empty, queue.Full):
                pass

    def _clear_audio_queue(self) -> None:
        while True:
            try:
                self.audio_queue.get_nowait()
            except queue.Empty:
                return

    def _listen_loop(self) -> None:
        try:
            download_models()
            wake_model = Model(wakeword_models=["hey_jarvis"], inference_framework="onnx")
            self._ui(self._set_status, 'Listening for “Hey Jarvis”…')
            self._clear_audio_queue()

            with sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="float32",
                blocksize=FRAME_SAMPLES,
                callback=self._audio_callback,
            ) as stream:
                self.audio_stream = stream
                while not self.stop_event.is_set():
                    try:
                        frame = self.audio_queue.get(timeout=0.25)
                    except queue.Empty:
                        continue
                    pcm = np.clip(frame * 32767, -32768, 32767).astype(np.int16)
                    scores = wake_model.predict(pcm)
                    if max(scores.values(), default=0.0) >= WAKE_THRESHOLD:
                        self._ui(self._set_status, "Wake word detected. Say your command…")
                        self._speak("Yes?")
                        command_audio = self._record_command()
                        if command_audio is not None and not self.stop_event.is_set():
                            self._transcribe_and_answer(command_audio)
                        self._clear_audio_queue()
                        self._ui(self._set_status, 'Listening for “Hey Jarvis”…')
                        time.sleep(0.8)
        except Exception as exc:
            self._ui(self._append, "Jarvis", f"Could not start voice listening: {exc}")
            self._ui(self._set_status, "Voice setup failed; see the message above.")
        finally:
            self.listening = False
            self._ui(self._restore_buttons)

    def _restore_buttons(self) -> None:
        self.start_button.configure(state=tk.NORMAL)
        self.stop_button.configure(state=tk.DISABLED)
        if not self.stop_event.is_set():
            self._set_status("Stopped")

    def _record_command(self) -> np.ndarray | None:
        time.sleep(0.35)
        chunks: list[np.ndarray] = []
        speech_started = False
        silence_seconds = 0.0
        elapsed = 0.0
        self._ui(self._set_status, "Listening for your command…")

        while not self.stop_event.is_set() and elapsed < 12.0:
            try:
                frame = self.audio_queue.get(timeout=0.5)
            except queue.Empty:
                continue
            elapsed += FRAME_SECONDS
            rms = float(np.sqrt(np.mean(np.square(frame))))
            if rms > 0.012:
                speech_started = True
                silence_seconds = 0.0
                chunks.append(frame)
            elif speech_started:
                chunks.append(frame)
                silence_seconds += FRAME_SECONDS
                if silence_seconds >= 0.9:
                    break
            elif elapsed >= 5.0:
                self._ui(self._set_status, 'No command heard. Say “Hey Jarvis” to try again.')
                return None

        return np.concatenate(chunks).astype(np.float32) if chunks else None

    def _transcribe_and_answer(self, audio: np.ndarray) -> None:
        try:
            self._ui(self._set_status, "Transcribing locally…")
            if self.whisper is None:
                self.whisper = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
            segments, _info = self.whisper.transcribe(audio, language="en", vad_filter=True)
            command = " ".join(segment.text.strip() for segment in segments).strip()
            if not command:
                self._ui(self._set_status, 'No speech recognized. Say “Hey Jarvis” to try again.')
                return
            self._ui(self._append, "You", command)
            self._ui(self._set_status, "Thinking…")
            reply = self._get_reply(command)
            self._ui(self._append, "Jarvis", reply)
            self._speak(reply)
        except Exception as exc:
            self._ui(self._append, "Jarvis", f"I couldn't process that request: {exc}")
            self._ui(self._set_status, "Ready")

    def send_typed_command(self) -> None:
        command = self.command_entry.get().strip()
        if not command:
            return
        self.command_entry.delete(0, tk.END)
        self._append("You", command)
        threading.Thread(target=self._answer_typed, args=(command,), daemon=True).start()

    def _answer_typed(self, command: str) -> None:
        self._ui(self._set_status, "Thinking…")
        try:
            reply = self._get_reply(command)
            self._ui(self._append, "Jarvis", reply)
            self._speak(reply)
        except Exception as exc:
            self._ui(self._append, "Jarvis", f"Request failed: {exc}")
        finally:
            self._ui(self._set_status, 'Listening for “Hey Jarvis”…' if self.listening else "Ready")

    def _get_reply(self, command: str) -> str:
        lowered = command.lower()
        if "time" in lowered:
            from datetime import datetime
            return f"It is {datetime.now().strftime('%I:%M %p').lstrip('0')}."
        if "date" in lowered or "what day" in lowered:
            from datetime import datetime
            return f"Today is {datetime.now().strftime('%A, %B %d, %Y')}\."

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return "AI answers need OPENAI_API_KEY. Time and date requests work without it."

        self.history.append({"role": "user", "content": command})
        messages = [
            {"role": "system", "content": "You are Jarvis, a helpful desktop voice assistant. Be concise and suitable for spoken replies."},
            *self.history[-12:],
        ]
        payload = json.dumps({"model": OPENAI_MODEL, "messages": messages}).encode("utf-8")
        request = Request(
            "https://api.openai.com/v1/chat/completions",
            data=payload,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=45) as response:
                result = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            self.history.pop()
            raise RuntimeError(f"AI service returned HTTP {exc.code}: {detail}") from exc
        except (URLError, TimeoutError) as exc:
            self.history.pop()
            raise RuntimeError(f"Could not reach the AI service: {exc}") from exc

        reply = result["choices"][0]["message"]["content"].strip()
        self.history.append({"role": "assistant", "content": reply})
        return reply or "I don't have a response for that yet."

    def _speak(self, text: str) -> None:
        # macOS's built-in `say` avoids extra TTS packages and uses installed voices.
        with self.speaking_lock:
            try:
                command = ["say", "-r", "175"]
                if MACOS_VOICE:
                    command.extend(["-v", MACOS_VOICE])
                command.append(text)
                subprocess.run(command, check=True, capture_output=True, text=True)
            except (OSError, subprocess.CalledProcessError) as exc:
                self._ui(self._append, "Jarvis", f"macOS text-to-speech failed: {exc}")

    def close(self) -> None:
        self.stop()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    JarvisApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
