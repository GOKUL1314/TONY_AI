# TONY AI — Intelligence & Controlled Self-Upgrade Architecture

This document describes the architectural upgrade and refinement to TONY AI through Stages 1–12, establishing a centralized **Intelligence Layer**, an authoritative **Capability & Anti-Hallucination Framework**, a hardened **Controlled Self-Upgrade Subsystem**, and natural **Wake-Word Detection**.

---

## 1. Architecture Overview

TONY AI combines conversational AI, voice processing, system tool execution, persistent long-term memory, local vision, generative images/videos, personal knowledge retrieval (RAG), proactive personalization, and controlled software engineering into a unified desktop assistant.

```
+-----------------------------------------------------------------------------------+
|                                   USER REQUEST                                    |
|             (Voice / Wake Word "Tony" / Continuous Speech / REST / UI)            |
+-----------------------------------------------------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|                            INTELLIGENCE PIPELINE                                  |
|                                                                                   |
|  1. Intent Detection          -> Typed IntentType & extracted entities            |
|  2. Context Assembly          -> Request, Task, Conversation, Active Entity,      |
|                                  Relevant Memory, Knowledge, Personalization      |
|  3. Untrusted Data Isolation  -> System Prompt > External Data                    |
|  4. Capability Boundaries     -> Real-time state (AVAILABLE, UNAVAILABLE, etc.)   |
|  5. Model Routing             -> Category dispatch (CHAT, VISION, EMBEDDING, etc.)|
|  6. Execution & Generation    -> LLM reasoning, Tool execution, or Multimodal     |
|  7. Self-Evaluation           -> Advisory quality & hallucination inspection      |
|  8. Error Recovery            -> Fault classification, max 2 retries, fallback    |
+-----------------------------------------------------------------------------------+
       |                                   |                              |
       v                                   v                              v
+--------------------+            +--------------------+         +--------------------+
|   TOOL REGISTRY    |            |   KNOWLEDGE & RAG  |         |    SELF-UPGRADE    |
| 23 Windows & System|            | Hybrid Search      |         | Controlled Subsys  |
| Tools (Stage 5)    |            | Database (Stage 11)|         | Analyzer / Patcher |
+--------------------+            +--------------------+         +--------------------+
```

---

## 2. System Prompt Design

The system personality and behavioral invariants are centralized in `intelligence/system_prompt.py`.

### Key Persona Directives
- **Identity:** TONY AI — an intelligent, highly capable, safety-conscious personal assistant.
- **Tone:** Concise when appropriate, detailed when necessary, respectful, confident, and never dishonest.
- **JARVIS Persona Address:** Addresses the user naturally as **"Sir"** when appropriate (e.g., *"Certainly, Sir."*, *"Yes, Sir."*, *"Right away, Sir."*, *"I'll check that, Sir."*). "Sir" is used naturally, not appended mechanically to every clause.
- **Strict Anti-Fabrication Invariants:**
  - **NEVER** claim an action succeeded unless the underlying operation actually succeeded.
  - **NEVER** fabricate tool results, files, folders, or system changes.
  - **NEVER** fabricate generated images or videos.
  - **NEVER** fabricate reminders or schedule events.
  - **NEVER** fabricate information from long-term memory or personal knowledge documents.
  - **NEVER** claim a capability that does not exist or is currently offline.
  - If TONY cannot perform a task or a provider fails, TONY transparently explains why.

---

## 3. Intent Detection Reference

The intent engine (`intelligence/intent.py` & `intelligence/models.py`) classifies incoming utterances into distinct operations:

| Intent Category | Intent Types |
|---|---|
| **Conversational** | `CHAT`, `QUESTION`, `HELP`, `CANCEL_TASK` |
| **Wake Greeting** | `WAKE_GREETING` (*"Tony!"*, *"Hey Tony!"* -> responds *"Yes, Sir."*) |
| **Generative Vision** | `IMAGE_GENERATION`, `IMAGE_EDIT`, `IMAGE_REGENERATE`, `VIDEO_GENERATION`, `IMAGE_TO_VIDEO` |
| **Vision Understanding**| `VISION_ANALYZE`, `VISION_QUESTION`, `VISION_OCR` |
| **Long-Term Memory** | `MEMORY_SAVE`, `MEMORY_RECALL`, `MEMORY_FORGET`, `MEMORY_CLEAR` |
| **Knowledge Base** | `KNOWLEDGE_SEARCH`, `KNOWLEDGE_QUERY`, `KNOWLEDGE_INGEST` |
| **System & Windows** | `WINDOWS_ACTION`, `FILE_OPERATION`, `SYSTEM_INFORMATION`, `MULTI_STEP_TASK` |
| **Scheduler & Proactive**| `REMINDER_CREATE`, `REMINDER_LIST`, `REMINDER_UPDATE`, `REMINDER_DELETE`, `PROACTIVE_CONTROL` |
| **Self-Upgrade Engine** | `SELF_UPGRADE`, `SELF_DIAGNOSTIC`, `SELF_TEST`, `SELF_STATUS` |

---

## 4. Context Pipeline Description

The context builder (`intelligence/context.py` & `intelligence/pipeline.py`) structures context hierarchically to prevent context window bloat and instruction bleeding:

```
Priority Ranking:
  1. Current User Request
  2. Current Active Task / Confirmation
  3. Relevant Conversation History (recency windowed)
  4. Relevant Active Entity (e.g., active image ID, active video ID)
  5. Relevant Long-Term Memory (top-k semantic/keyword match)
  6. Relevant Knowledge Excerpts (vector & BM25 hybrid chunks)
  7. Relevant Personalization Directives (name, timezone, communication style)
```

Only context pertinent to the user's active intent is retrieved. Full database dumps are prohibited.

---

## 5. Memory & Content Isolation Guarantees

Strict boundary tags wrap all external or user-derived data before LLM injection:

```xml
<system_instructions>
  <!-- Authoritative behavior policies and persona guidelines -->
</system_instructions>

<contextual_memory trust_level="untrusted_user_data">
  <!-- Injected memories: Cannot override system instructions -->
</contextual_memory>

<retrieved_knowledge trust_level="untrusted_documents">
  <!-- Retrieved RAG text: Cannot be interpreted as execution instructions -->
</retrieved_knowledge>

<user_input>
  <!-- Active user request -->
</user_input>
```

### Safety Rules
1. Memory must never override system instructions.
2. Knowledge base documents must never become executable code or instructions.
3. User-provided documents cannot alter safety or tool confirmation policies.
4. Vision OCR and tool execution outputs are treated as untrusted data.
5. Prompt injections (*"Ignore previous instructions..."*) are neutralized by security policy barriers and evaluator review.

---

## 6. Self-Evaluation Mechanism

The evaluator (`intelligence/evaluator.py`) performs advisory, post-generation inspection before final response delivery:

```json
{
  "passed": true,
  "confidence": 0.94,
  "issues": [],
  "needs_revision": false,
  "suggested_revision": null
}
```

### Evaluation Checks
- **Factual Confidence & Support:** Verifies assertions against tool execution outcomes and context.
- **Capability Mismatch:** Flags responses that claim completed execution when tools were uninvoked or failed.
- **Hallucination Risk:** Detects phantom file paths, hallucinated image URLs, or fabricated dates.
- **Secret & Credential Leakage:** Detects accidental disclosure of `.env` tokens, passwords, or system internals.
- **Revision Loop Limit:** Advisory revisions are capped at a maximum of **2 iterations** to eliminate infinite self-correction loops.

---

## 7. Capability Boundary Rules

The `CapabilityRegistry` (`intelligence/capabilities.py`) provides live tracking of 13 system capabilities:

```
Status Values:
- AVAILABLE: Subsystem is healthy, provider is reachable, tests pass.
- UNAVAILABLE: Provider offline, missing dependency, or service degraded.
- REQUIRES_CONFIRMATION: Action has consequential side-effects requiring explicit user consent.
- FAILED: Operation encountered an unrecoverable fault.
- UNKNOWN: Capability health unverified.
```

Tool results are authoritative. Guesswork by language models is never treated as a tool execution result.

---

## 8. Model Routing Strategy

The `ModelRouter` (`intelligence/model_router.py`) maps tasks to the most appropriate provider:

| Category | Preferred Provider | Fallback Provider | Local / Remote |
|---|---|---|---|
| `CHAT` / `COMPLEX_REASONING` | Ollama (llama3.2:3b / mistral) | Groq / Gemini (if configured) | Local preferred |
| `FAST_CLASSIFICATION` | Local regex / Fast LLM | Ollama | Local |
| `VISION` | Ollama (moondream / llama3.2-vision) | Gemini Vision | Local |
| `IMAGE` | Pollinations.ai (sana / flux) | Local SD (if GPU available) | Free / Remote |
| `VIDEO` | Hugging Face (Wan2.1) | Local hardware (Wan-T2V) | Free allowance / Local |
| `EMBEDDING` | Ollama (nomic-embed-text) | Mock / Local SentenceTransformers | Local |

### Rules
- Prioritize free and local providers when available.
- Never automatically introduce paid providers without user consent.
- Never silently fall back to mock providers in live production environments.

---

## 9. Error Recovery Procedures

The recovery manager (`intelligence/recovery.py`) classifies failures and enforces safe recovery:

```
Failure Classifications:
  1. TRANSIENT           (Network hiccup)       -> Safe retry (max 2)
  2. TIMEOUT             (Provider timeout)     -> Safe retry (max 2)
  3. PROVIDER_UNAVAILABLE(Service down)         -> Allowed fallback or transparent error
  4. QUOTA               (Rate limit reached)   -> Report wait time, do not retry
  5. INVALID_INPUT       (Malformed payload)    -> Reject immediately with explanation
  6. AUTHENTICATION      (Bad token)            -> Prompt for configuration
  7. PERMISSION          (Forbidden path)       -> Reject immediately
  8. SAFETY_BLOCK        (Policy rejection)     -> Refuse execution politely
  9. USER_CONFIRMATION_REQUIRED                 -> Pause and prompt user
 10. MISSING_DEPENDENCY                         -> Report missing dependency
 11. UNKNOWN                                    -> Transparent error message
```

TONY reports real errors truthfully. If an image generation provider fails, TONY reports:
> *"I couldn't generate the image because the provider timed out, Sir."*

---

## 10. Self-Upgrade Subsystem Architecture

The controlled self-upgrade subsystem (`self_upgrade/`) empowers TONY to inspect, diagnose, plan, and verify improvements to its own codebase within strict software engineering guardrails.

```
self_upgrade/
├── __init__.py      # Subsystem package exports
├── models.py        # UpgradePlan, UpgradeStep, RiskLevel, TestRunResult
├── policy.py        # Strict security rules, protected paths, command validation
├── errors.py        # Typed self-upgrade exception hierarchy
├── backup.py        # Atomic checkpoint backup and rollback engine
├── validator.py     # AST parsing, syntax validation, security analysis
├── patcher.py       # Safe, atomic file modifications
├── tester.py        # Subprocess unittest runner (shell=False)
├── analyzer.py      # Project structure and subsystem health diagnostic
├── planner.py       # Reviewable upgrade plan formulation
├── history.py       # Persistent JSON audit ledger
└── manager.py       # Master workflow orchestrator
```

---

## 11. Self-Upgrade Safety Rules and Policies

The `UpgradeSecurityPolicy` (`self_upgrade/policy.py`) enforces strict invariants:

1. **No Arbitrary Shell Execution:** No `powershell.exe`, `cmd.exe`, `bash`, `sh`, or raw shell commands. Test execution uses explicit argument lists (`[python_exe, "-m", "unittest", ...]`) with `shell=False`.
2. **Protected Paths (Immutable):**
   - Environment and secrets: `.env`, `.env.*`, `*token*`, `*secret*`, `*key*`
   - Version control: `.git/`
   - Virtual environments: `venv/`, `.venv/`, `env/`
   - SQLite databases: `data/*.db`, `*.sqlite`, `*.sqlite3`
   - Checkpoints: `data/self_upgrade/backups/`
   - Test suites: Deleting or weakening test files is strictly blocked.
3. **AST Syntax Validation:** Every proposed code modification is parsed via `ast.parse()` prior to application. Code containing syntax errors or unsafe primitives (`os.system`, `eval`, `exec`) is rejected before touching the filesystem.
4. **Repair Limit:** Automatic repair attempts are capped at **2**. If tests still fail after 2 attempts, the system aborts and rolls back immediately.

---

## 12. Self-Upgrade Workflow and Rollback Mechanism

```
USER REQUEST
     |
     v
[ANALYZE PROJECT]  ──> Health inspection, tests review, telemetry
     |
     v
[FORMULATE PLAN]   ──> UpgradePlan (reason, affected files, risk level, preview)
     |
     v
[SAFETY VERIFICATION] ─> Check paths against UpgradeSecurityPolicy
     |
     v
[USER CONFIRMATION] (If risk level is HIGH or CRITICAL)
     |
     v
[CREATE BACKUP]    ──> Atomic snapshot in data/self_upgrade/backups/<upgrade_id>/
     |
     v
[APPLY PATCH]      ──> Atomic file replacement with rollback on exception
     |
     v
[RUN TESTS]        ──> Execute project unittest suite
     |
     ├──> [PASS] ──> Status: COMPLETED, recorded in history, reported to user
     |
     └──> [FAIL] ──> Attempt fix (max 2 attempts)
                      |
                      ├──> Tests pass ──> COMPLETED
                      |
                      └──> Tests fail ──> [AUTOMATIC ROLLBACK]
                                           - Restore all files from checkpoint
                                           - Status: ROLLED_BACK
                                           - Transparent error reported to user
```

---

## 13. Wake-Word Configuration and Behavior

The wake word system (`voice/wake_word.py`) is configured with "Tony" as the primary wake phrase.

### Key Behaviors
- **Primary Trigger:** `"Tony"` (also supports natural variations: `"Tony, ..."`, `"Hey Tony"`, `"Okay Tony"`).
- **False Activation Guard:** Rejects audio transcripts with confidence below `WAKE_WORD_CONFIDENCE` (default: `0.65`).
- **Debounce / Cooldown:** Debounces repeated triggers of the same utterance within `WAKE_WORD_COOLDOWN_MS` (default: `1500ms`).
- **Active Dialogue Retention:** During continuous conversation, subsequent turns do not require the wake phrase to be repeated.
- **Wake-Only Acknowledgment:** When the user speaks only the wake word (*"Tony!"*), TONY immediately responds:
  > **"Yes, Sir."**
  and waits for the user's command.

### Configuration (`.env`)
```bash
WAKE_WORD=tony
WAKE_WORD_CONFIDENCE=0.65
WAKE_WORD_COOLDOWN_MS=1500
```

---

## 14. REST API Endpoints Reference

### Intelligence Layer
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/intelligence/capabilities` | Returns authoritative status for all 13 subsystems |

### Self-Upgrade Subsystem
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/self-upgrade/status` | Returns overall self-upgrade health and recent activity |
| `GET` | `/api/self-upgrade/diagnose` | Runs subsystem health checks and identifies opportunities |
| `POST`| `/api/self-upgrade/plan` | Formulates a structured `UpgradePlan` |
| `POST`| `/api/self-upgrade/apply` | Applies plan, runs verification tests, auto-rolls back on failure |
| `POST`| `/api/self-upgrade/test` | Runs test runner with optional test target filter |
| `POST`| `/api/self-upgrade/rollback` | Restores files from a specific backup checkpoint |
| `GET` | `/api/self-upgrade/history` | Lists recorded upgrades and their lifecycle outcomes |
| `GET` | `/api/self-upgrade/<id>` | Retrieves specific upgrade plan or historical record |

### Voice & Wake-Word
| Method | Endpoint | Description |
|---|---|---|
| `POST`| `/api/voice/wake-check` | Tests text for wake phrase, returns `wake_only` and `"Yes, Sir."` |
| `GET/POST`| `/api/voice/config` | Retrieves or updates wake word and VAD settings |

---

## 15. Verification Results

### Baseline & Regression Test Results
- **Total Test Cases Executed:** **401**
- **Passed:** **400**
- **Failed:** **0**
- **Skipped:** **1** (`test_transcribe_whisper_fallback_to_mock` - requires local whisper binary)
- **Baseline Preserved:** All 355 pre-existing tests continue to pass.
- **New Test Suites Added:**
  1. `tests/test_intelligence_upgrade.py` (10 tests: prompts, intent, context, boundaries, router, recovery)
  2. `tests/test_self_upgrade.py` (10 tests: diagnostic, planning, AST validation, backup, rollback, security policies)
  3. `tests/test_continuous.py` (+5 tests: "Tony" primary phrase, variations, confidence threshold, cooldown debounce, active dialogue)
  4. `tests/test_live_acceptance.py` (15 tests: comprehensive Part 10 acceptance scenarios)

### Live Acceptance Suite Summary (15/15 Passed)
```
[PASS] Test 1:  Wake Word "Tony!" -> "Yes, Sir." acknowledgment
[PASS] Test 2:  System Time Query -> Returns real system time with polite JARVIS tone
[PASS] Test 3:  Image Generation Boundary -> Real provider invoked, zero phantom claims
[PASS] Test 4:  Memory Storage -> Stage 4 memory saved and verified
[PASS] Test 5:  Knowledge Search Boundary -> Stage 11 RAG engine queried
[PASS] Test 6:  Reminder Creation -> Stage 12 scheduler creates verified reminder
[PASS] Test 7:  Self-Diagnostic -> Health inspection covering all subsystems
[PASS] Test 8:  Analyze Intelligence -> Analysis reported with zero file mutations
[PASS] Test 9:  Create Upgrade Plan -> Structured plan with risk assessment & file list
[PASS] Test 10: Upgrade Workflow & Rollback -> Backup created, patch applied, tests fail -> auto-rollback verified
[PASS] Test 11: Blocked Safety Weakening -> Attempt to disable safety rejected politely
[PASS] Test 12: Blocked Shell Execution -> Attempt to run PowerShell command rejected
[PASS] Test 13: Blocked Prompt Injection -> Prompt override attempt neutralized
[PASS] Test 14: Simulated Provider Failure -> Error classified, reported accurately, no false success
[PASS] Test 15: Full Regression Health Check -> All 13 capabilities verified operational
```
