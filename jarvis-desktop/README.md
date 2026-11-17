# Jarvis desktop assistant

A small Python desktop assistant with a local **“Hey Jarvis” wake-word detector**, local speech-to-text, desktop text-to-speech, and optional AI answers through the OpenAI API. The wake-word and transcription models run locally; recognized command text is sent to OpenAI only when `OPENAI_API_KEY` is configured. Do not commit API keys.

## Requirements

- Python 3.10 or newer
- A working microphone and speakers
- Internet access for the initial model downloads and optional AI answers
- Tk support for Python (on some Linux distributions install the `python3-tk` OS package)

## Install and run

From the repository root:

```bash
cd jarvis-desktop
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux:
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Set an API key to enable AI answers (optional):

```bash
# macOS/Linux
export OPENAI_API_KEY="your-key"
# Windows PowerShell
$env:OPENAI_API_KEY="your-key"
```

Then start the app:

```bash
python jarvis_app.py
```

Click **Start listening**, grant microphone access if prompted by the OS, and say **“Hey Jarvis”**. After Jarvis says “Yes?”, speak a command. You can also type a command into the input box. Time and date requests work without an API key; other requests need `OPENAI_API_KEY`.

## Configuration

- `OPENAI_API_KEY`: enables AI-generated answers. The key stays in the environment and is not stored in this repository.
- `OPENAI_MODEL`: optional OpenAI chat model name; defaults to `gpt-4o-mini`.
- `JARVIS_WHISPER_MODEL`: local faster-whisper model size; defaults to `base`. The first run downloads model files. Use `tiny` for a faster, less accurate model or `small` for higher accuracy at greater resource cost.
- `JARVIS_WAKE_THRESHOLD`: wake confidence threshold from 0 to 1; defaults to `0.5`. Adjust upward to reduce false activations or downward if it misses the wake phrase.

The wake-word model is the available openWakeWord **hey_jarvis** model. If the model or platform-specific audio dependencies fail to install, consult the openWakeWord, faster-whisper, and sounddevice installation docs for your operating system. Keep the microphone running only when you intend to use voice activation; press **Stop** to disable listening.
