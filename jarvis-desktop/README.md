# Jarvis desktop assistant for macOS

A small Python desktop assistant for macOS. It uses openWakeWord for local **“Hey Jarvis”** detection, faster-whisper for local speech-to-text, the built-in macOS `say` command for voice output, and optionally OpenAI for AI answers. The microphone audio is processed locally for wake-word detection and transcription; the recognized command text is sent to OpenAI only if `OPENAI_API_KEY` is configured.

## Requirements

- macOS 12 or later (Apple Silicon or Intel)
- Python 3.10–3.12 recommended
- Homebrew
- Microphone and speakers

## Install on macOS

Install PortAudio, required by the Python microphone package:

```bash
brew install portaudio
```

In Terminal, from the repository root:

```bash
cd jarvis-desktop
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If the app reports that Tk is missing, install a Python distribution that includes Tcl/Tk (the official python.org macOS installer is one option), recreate the virtual environment with that Python, and verify Tk with `python -m tkinter`.

## Allow microphone access

Start the app once and approve the macOS microphone permission prompt for the app that launched it (usually Terminal or iTerm). If you dismissed the prompt, open **System Settings → Privacy & Security → Microphone** and enable access for that terminal app. Quit and reopen the terminal after changing permissions.

## Enable AI answers (optional)

Create an API key with your AI provider, then set it in the same Terminal session before starting Jarvis:

```bash
export OPENAI_API_KEY="your-key"
```

The key is read from the environment and is not saved in the project. Without it, time/date answers and typed commands still work, but general AI answers are unavailable. Requests with the key send recognized command text to OpenAI.

## Run

With the virtual environment active:

```bash
python jarvis_app.py
```

Click **Start listening**, then say **“Hey Jarvis”** and wait for “Yes?” before speaking your command. You can also type a command. The first run downloads the wake-word and transcription models; allow time and disk space for those downloads.

## macOS voice and configuration

The app speaks using macOS's built-in `say` utility, so `pyttsx3` is not needed. List available voices with:

```bash
say -v '?'
```

Choose one by setting (replace `Samantha` with a voice shown on your Mac) before launching:

```bash
export JARVIS_VOICE="Samantha"
```

Configuration:

- `OPENAI_API_KEY`: optional key for AI responses.
- `OPENAI_MODEL`: chat model name; defaults to `gpt-4o-mini`.
- `JARVIS_VOICE`: optional macOS `say` voice; empty uses the system default.
- `JARVIS_WHISPER_MODEL`: local transcription model; defaults to `base`. Use `tiny` for faster inference or `small` for better accuracy with higher resource use. The first run downloads it.
- `JARVIS_WAKE_THRESHOLD`: wake confidence threshold from 0 to 1; defaults to `0.5`. Raise it to reduce false activations or lower it if it misses the phrase.

## Troubleshooting

- **No microphone / permission denied:** grant microphone access to Terminal or iTerm in System Settings, then restart it.
- **PortAudio or sounddevice install error:** ensure Homebrew PortAudio is installed (`brew install portaudio`) and install the Python packages again in the activated venv.
- **Tkinter error:** use Python with Tcl/Tk support; verify with `python -m tkinter`.
- **Wake model / ONNX error:** ensure model downloads can access the internet, then restart the app. Dependencies and model runtime support can vary by Python and macOS version.
- **No AI response:** verify `echo $OPENAI_API_KEY` is non-empty in the same Terminal session used to launch the app.

Press **Stop** before closing if you want to disable microphone listening. Never commit your API key to the repository.
