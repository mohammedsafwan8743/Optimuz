# 🤖 OPTIMUZ — Real-Time AI Voice Companion

Always listening. Always talking. No buttons. Just speak.

Inspired by Optimus Prime — powerful, wise, and always on your side.

## Stack
- 🧠 Claude (Anthropic) — intelligent, emotionally aware responses
- 🎙️ OpenAI Whisper (local) — speech-to-text in any language  
- 🔊 ElevenLabs — deep, powerful autobot-style voice
- ⚡ Streamlit — simple Python UI, one command to run

---

## Setup

### Step 1 — Install dependencies
```bash
pip install -r requirements.txt
```

> **Windows users:** Make sure ffmpeg is installed and in PATH
> Download from: https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip
> Extract to C:\ffmpeg and add C:\ffmpeg\bin to system PATH

### Step 2 — Add API keys
```bash
copy .env.example .env
```
Edit `.env` with your keys:
- `ANTHROPIC_API_KEY` → https://console.anthropic.com
- `ELEVENLABS_API_KEY` → https://elevenlabs.io

### Step 3 — Run!
```bash
streamlit run app.py
```

Open **http://localhost:8501** in Chrome.

---

## How it works

1. **Just speak** — microphone activates automatically
2. **2 seconds of silence** → OPTIMUZ starts processing
3. **Whisper** transcribes your voice locally
4. **Claude** generates a powerful, emotionally-aware reply
5. **ElevenLabs** speaks back in a deep autobot voice
6. **Repeat** — seamless real-time conversation

## Features
- 🔁 Fully automatic — no tap to talk, no buttons
- 🌍 Any language — auto-detected
- 🧠 Persistent memory across sessions
- ❤️ Emotion detection — adapts tone to your mood
- 📋 Transmission log — see the conversation history
- 💾 History saved to `data/history.jsonl`

## Recommended ElevenLabs Voices (Autobot-style)
| Voice | ID |
|-------|-----|
| Adam (default) | `pNInz6obpgDQGcFmaJgB` |
| Arnold | `VR6AewLTigWG4xSOukaG` |
| Liam | `TX3LPaxmHKxFdv7VOQHJ` |

Change in `.env` → `ELEVENLABS_VOICE_ID=your_choice`
