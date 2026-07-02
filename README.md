# AI Focus Tutor (Warden)

An autonomous, multimodal AI tutor designed to monitor your desktop activity, enforce Pomodoro pacing, and ruthlessly (but occasionally gently) keep you focused on your goals using local AI models.

## Architecture

The project consists of two main components: a Python backend and a Firefox browser extension. They communicate seamlessly via a secure, local WebSocket.

### 1. The Python Backend (The "Warden")
The backend acts as the central brain of the operation, orchestrating state, AI evaluations, and UI rendering.
- **`main.py`**: The central async orchestrator. Runs the WebSocket server (`localhost:8765`), desktop monitoring loops, Pomodoro pacing loops, and emotional analysis loops.
- **`warden.py`**: The AI interface. Manages communication with the local Ollama LLM (`gemma4:e4b`) and the local TTS engine (running on port `5050`). It handles a multi-tiered evaluation pipeline:
  - **Tier 1 (Instant):** Fast string/keyword matching against approved/distracted terms.
  - **Tier 1.5 (Fast):** Semantic text evaluation of browser DOM payloads (`FAT_PAYLOAD`) to catch off-topic reading without needing a screenshot.
  - **Tier 2 (Heavy):** Multimodal Vision evaluation using desktop screenshots and webcam feeds to catch visual distractions.
- **`state_manager.py`**: Manages both volatile session state (like praise timers and grace periods) and persistent settings using `pydantic`.
- **`desktop_sensor.py` & `webcam_sensor.py`**: Hardware interfaces for capturing screen state (via `pyscreenshot` for Wayland/X11 compatibility) and facial snapshots (via `cv2`).
- **`ui.py`**: A lightweight, unobtrusive setup interface built with `customtkinter`. It cleanly minimizes to your system taskbar during active focus sessions.

### 2. The Browser Extension
A lightweight Manifest V3 Firefox extension designed to operate silently across multiple profiles.
- **Passive Monitoring (`THIN_PAYLOAD`)**: Automatically broadcasts the active tab's URL and title to the backend whenever you switch tabs or windows.
- **Active Scraping (`FAT_PAYLOAD`)**: If the backend detects an "ambiguous" website, it triggers a `SCRAPE_DOM` WebSocket command. The extension instantly responds with up to 3,000 characters of the page's text for semantic analysis.
- *Note:* The extension drops connections cleanly and gracefully reconnects, allowing you to run it simultaneously across dozens of isolated Firefox profiles.

## Features

- **Multi-Tiered Distraction Pipeline**: Optimized to save GPU VRAM. It relies on instantaneous text/DOM evaluation first, only falling back to heavy multimodal Vision scans when absolutely necessary.
- **Grace Period**: If you are caught slipping, a 15-second grace period timer starts. If you return to work before the timer expires, no intervention occurs.
- **Snarky Interventions**: If you fail the grace period, the AI looks at what you are doing and generates a highly contextual, sarcastic spoken intervention to shame you back to work.
- **Proactive Emotional Support**: The webcam polls your facial expression via `deepface` every 3 minutes. If you look highly frustrated (angry, sad, fearful) while staring at a valid task, the AI will proactively offer a gentle, encouraging spoken nudge.
- **Autonomous Praise**: Every 10 minutes of uninterrupted focus, the LLM generates and speaks a highly contextual compliment based on your specific task to provide positive reinforcement.
- **Pomodoro Mode**: Optional 25/5 pacing. The AI handles the timers, autonomously pausing distraction scanners during breaks and verbally announcing when breaks begin and end.

## Setup & Installation

### Prerequisites
- Python 3.11+ (using `uv`)
- Firefox Developer Edition (if installing the extension persistently without signing)
- `ollama` installed locally with the `gemma4:e4b` multimodal vision model.
- A local OpenAI-compatible TTS server running on `http://localhost:5050`.

### 1. Backend Installation & TLS Setup
The WebSocket server requires an SSL/TLS certificate to communicate securely with the browser extension. Since this is local, we will generate a self-signed certificate.

1. Clone the repository and navigate to the project directory.
2. Generate the SSL certificates:
```bash
openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -sha256 -days 365 -nodes -subj "/CN=localhost"
```
3. Ensure you have the necessary system dependencies (e.g.,`sqlite3`, `scrot` or Wayland equivalent for `pyscreenshot`, and proper webcam drivers).
4. Run the backend using `uv`:
```bash
uv run main.py
```

### 2. Firefox Certificate Trust
Because the certificate you just generated is self-signed, Firefox will block the WebSocket connection by default. You must explicitly tell Firefox to trust it:
1. Start the Python backend so the server is running on port 8765.
2. Open Firefox and navigate to `https://localhost:8765`.
3. Firefox will show a security warning ("Potential Security Risk Ahead").
4. Click **Advanced**, then click **Accept the Risk and Continue**. (You will see a blank page or a protocol error—this is perfectly fine and means the certificate is now trusted).

### 3. Extension Installation
1. Open Firefox and navigate to `about:debugging#/runtime/this-firefox`.
2. Click **Load Temporary Add-on...**
3. Select the `manifest.json` file inside the `extension/` directory.
*(To install permanently across multiple profiles, zip the contents of the extension directory and submit it to the [Mozilla Add-on Developer Hub](https://addons.mozilla.org/developers/addon/submit/distribution) for automated unlisted signing).*

## Usage
1. Launch the backend `main.py`.
2. The setup UI will appear. Define your goal (e.g., "I am working on a TryHackMe passive reconnaissance room using Firefox and QEMU virtual machines").
3. Select your pacing style (Continuous Focus or Pomodoro 25/5).
4. Click **Start Focus Session**. The UI will minimize to your taskbar, and the Warden will begin monitoring.
