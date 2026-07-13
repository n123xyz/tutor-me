<div align="center">
  <h1>AI Focus Tutor</h1>
  <p><em>An autonomous, multimodal AI tutor designed to monitor your desktop activity, enforce Pomodoro pacing, and ruthlessly (but occasionally gently) keep you focused on your goals.</em></p>
</div>

<hr/>

## What it Does

The AI Focus Tutor combines a Python backend and a lightweight Firefox extension to act as your personal productivity coach. 

It watches your screen and web activity, intervening when you get distracted, and praising you when you stay on track.

## Architecture Snapshot

| Component | Description | Tech |
| --- | --- | --- |
| **Backend** | The central brain. Orchestrates AI evaluation, state, and UI. | Python, CustomTkinter |
| **Firefox Extension** | Monitors active tabs seamlessly across multiple profiles. | Manifest V3 |
| **Local LLM & Vision** | Evaluates screen context and webcam feeds (Tiered). | Ollama (`gemma4:e4b`) |
| **Local TTS Engine** | Speaks out interventions or praises. | OpenAI-compatible TTS |

## Key Features

- **Multi-Tiered Evaluation:** Evaluates text/DOM first, saving GPU by only using Vision when absolutely necessary.
- **Grace Period:** Caught slipping? You get 15 seconds to return to work before the AI speaks up.
- **Snarky Interventions:** Highly contextual, sarcastic spoken nudges to shame you back to focus.
- **Physical Distraction Tracking:** Periodically checks webcam feeds to ensure you are physically present and focused on your goal.
- **Pomodoro Mode:** Optional 25/5 pacing. The AI handles the timers and announces breaks automatically.

## Setup & Installation

### 1. Prerequisites
- **Python 3.11+** (using `uv`)
- **Firefox Developer Edition** (recommended)
- Local **Ollama** installed with the `gemma4:e4b` model.
- Local **TTS server** running on `http://localhost:5050`.

### 2. Backend & TLS Setup
The tutor uses a secure local WebSocket. Generate a self-signed certificate first:

```bash
# Generate SSL certs
openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -sha256 -days 365 -nodes -subj "/CN=localhost"

# Run the backend
uv run main.py
```

### 3. Firefox Certificate Trust
To allow the secure connection:
1. Start the backend so it runs on port `8765`.
2. Navigate to `https://localhost:8765` in Firefox.
3. Click **Advanced** > **Accept the Risk and Continue** (Expect a blank page or error—this means it's working).

### 4. Extension Installation
1. Go to `about:debugging#/runtime/this-firefox`.
2. Click **Load Temporary Add-on...**
3. Select `manifest.json` inside the `extension/` folder.

## Usage

1. **Launch** the backend (`uv run main.py`).
2. **Define your goal** in the setup UI (e.g., "Working on a TryHackMe room using QEMU").
3. **Select your pacing** (Continuous Focus or Pomodoro).
4. **Click Start** and let the AI guide you to peak productivity.
