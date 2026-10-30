
# TONY // Personal AI Desktop Assistant

**TONY** is an intelligent, calm, and capable personal AI desktop assistant built to evolve into a full-fledged system assistant. 

> **Current Status:** **Stage 1 (Foundation & AI Chatbot)** is fully implemented and operational.

---

## 1. What TONY Is

TONY is designed to be your personal AI desktop companion. In its ultimate vision, TONY will talk with you naturally, understand voice commands, maintain long-term memory across sessions, generate images and videos, use developer and system tools, perform computer tasks with your authorization, and launch automatically with Windows.

To ensure stability and modularity, TONY is being engineered in iterative stages. Stage 1 delivers the architectural core, configuration system, provider abstraction, conversation persistence, and modern web interface.

---

## 2. Current Capabilities (Stage 1)

- **Futuristic HUD Web Interface:** Clean cybernetic UI with real-time telemetry, rotating reactor core animation, glassmorphism design, and responsive layout.
- **AI Provider Abstraction:** Decoupled model layer supporting Local LLMs (Ollama), Cloud LLMs (OpenAI-compatible), and built-in Mock mode.
- **Conversational Foundation:** Calm, intelligent, and helpful persona adhering to strictly implemented capabilities without over-promising.
- **Dialogue History Persistence:** Stores session turns (timestamps, user messages, assistant responses) in local JSON storage (`data/conversations/active_session.json`) with auto-archival upon clear.
- **RESTful Backend API:** Fully tested endpoints for chat, history retrieval, session reset, and system health checks.
- **Robust Error Handling:** Validates JSON structure, empty inputs, network timeouts, and model connectivity issues gracefully.
- **Logging Subsystem:** Centralized logging with file (`logs/tony.log`) and console output handlers.

---

## 3. Current Limitations

- **No Voice Input / Audio Output:** Voice recognition and text-to-speech are scheduled for Stage 2.
- **No System Automation / OS Control:** TONY cannot execute shell commands or control mouse/keyboard in this stage (planned for Stage 5).
- **No Image or Video Generation:** Scheduled for Stage 6 and Stage 7.
- **No Vector Long-Term Memory:** Dialogue history is file-based JSON; vector retrieval is planned for Stage 4.
- **No Windows Startup Daemon:** Startup integration is scheduled for Stage 8.

---

## 4. Architecture

TONY utilizes a modular client-server architecture:

```
[ Frontend: HTML5 / CSS3 / Vanilla JS ]
                   |
             HTTP REST / JSON
                   v
[ Backend: Flask Application (app.py) ]
    ├── Config System (config/settings.py)
    ├── Logging (logs/tony.log)
    ├── API Routes (routes/chat.py)
    ├── Conversation Service (services/conversation.py) -> [ data/conversations/*.json ]
    └── AI Provider Layer (ai/provider.py)
            ├── LocalProvider (ai/local_provider.py)  -> Local Ollama (http://localhost:11434)
            ├── APIProvider (ai/api_provider.py)      -> Cloud APIs (OpenAI/Groq/etc.)
            └── MockProvider (ai/mock_provider.py)    -> Offline / Standalone Testing
```

### Directory Structure

```
TONY_AI/
├── app.py                     # Flask entry point and application factory
├── requirements.txt           # Python project dependencies
├── .env.example               # Environment variables template
├── .env                       # Local active environment configuration
├── README.md                  # Comprehensive documentation
│
├── config/
│   ├── __init__.py
│   └── settings.py            # Centralized settings and directory loader
│
├── ai/
│   ├── __init__.py
│   ├── provider.py            # Abstract Base Class and Provider Factory
│   ├── local_provider.py      # Ollama local inference adapter
│   ├── api_provider.py        # OpenAI-compatible cloud API adapter
│   └── mock_provider.py       # Offline fallback and mock provider
│
├── routes/
│   ├── __init__.py
│   └── chat.py                # REST API routes (/api/chat, /history, /status)
│
├── services/
│   ├── __init__.py
│   └── conversation.py        # Local session persistence and archival
│
├── data/
│   └── conversations/         # Stored conversation JSON sessions
│
├── logs/                      # Log outputs (tony.log)
│
├── static/
│   ├── css/
│   │   └── style.css          # Futuristic dark theme stylesheet
│   └── js/
│       └── app.js             # Client UI logic and telemetry
│
├── templates/
│   └── index.html             # Futuristic HUD chat template
│
└── tests/
    ├── __init__.py
    └── test_api.py            # Automated test suite
```

---

## 5. Installation

### Prerequisites

- Windows 10 or 11
- Python 3.10+ (tested on Python 3.11.9)
- (Optional) [Ollama](https://ollama.com/) for running local models completely offline.

### Setup Instructions

1. **Open PowerShell in the project directory:**
   ```powershell
   cd C:\Users\GOKUL\Desktop\TONY_AI
   ```

2. **Create and activate a Python virtual environment:**
   ```powershell
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   ```

3. **Install dependencies:**
   ```powershell
   pip install -r requirements.txt
   ```

4. **Prepare environment configuration:**
   Copy `.env.example` to `.env` if not already present:
   ```powershell
   Copy-Item .env.example .env
   ```

---

## 6. How to Run TONY

1. **Activate the virtual environment:**
   ```powershell
   .\venv\Scripts\Activate.ps1
   ```

2. **Start the Flask server:**
   ```powershell
   python app.py
   ```

3. **Access the HUD Interface:**
   Open your browser and navigate to:
   [http://127.0.0.1:5000](http://127.0.0.1:5000)

---

## 7. How to Configure the AI Provider

TONY supports three provider configurations via the `.env` file:

### Mode A: Local LLM with Ollama (Default, Free, Offline)

1. Set `.env`:
   ```ini
   AI_PROVIDER=local
   AI_MODEL=llama3.2:1b
   OLLAMA_BASE_URL=http://localhost:11434
   ```
2. Install Ollama from [ollama.com](https://ollama.com/).
3. Pull the model in a terminal:
   ```bash
   ollama run llama3.2:1b
   ```
   *(Or alternative models like `ollama run mistral` or `ollama run qwen2.5:1.5b`)*

### Mode B: Cloud API (OpenAI, Groq, Together)

1. Set `.env`:
   ```ini
   AI_PROVIDER=api
   AI_MODEL=gpt-4o-mini
   API_KEY=your_actual_api_key_here
   API_BASE_URL=https://api.openai.com/v1
   ```

### Mode C: Mock / Standalone Offline Testing (Zero setup required)

1. Set `.env`:
   ```ini
   AI_PROVIDER=mock
   AI_MODEL=tony-mock-v1
   ```
*Instant out-of-the-box mode for testing TONY's persona, endpoints, and UI without running any background engines.*

---

## 8. Which Model is Currently Being Used

By default in `.env`:
- **Provider:** `local` (Ollama)
- **Model:** `llama3.2:1b` (A fast, lightweight 1-billion parameter model ideal for local desktop responsiveness).

If Ollama is not yet installed or running, the status badge on the UI will display `ATTENTION` with a notification explaining how to launch Ollama or switch to `mock`/`api` mode.

---

## 9. How to Switch Models Later

To switch models at any time:
1. Open the `.env` file in your editor.
2. Modify `AI_MODEL` to any model you prefer (e.g. `mistral`, `llama3.1:8b`, `deepseek-r1:1.5b`, or `gpt-4o-mini`).
3. If switching provider types, update `AI_PROVIDER` (to `local`, `api`, or `mock`).
4. Restart the Flask application (`python app.py`).

---

## 10. Running Automated Tests

To run the built-in unit and integration test suite:

```powershell
.\venv\Scripts\python.exe -m unittest tests/test_api.py
```

This verifies:
- Web homepage rendering
- POST `/api/chat` with valid messages
- Capability reasoning compliance
- Empty message rejection (HTTP 400)
- Missing payload validation (HTTP 400)
- Non-JSON payload handling (HTTP 400)
- Session history persistence & multi-turn retrieval
- Session clearing and auto-archival
- Telemetry diagnostic endpoint `/api/status`
- Offline Ollama error recovery




