/**
 * TONY AI Assistant - Stage 3 Continuous Conversation System
 * Manages hands-free turn-taking, local wake-word ("Hey Tony"), real-time Web Audio VAD,
 * silence detection timeout, speech interruption, audio ducking, and hardware safety controls.
 */

document.addEventListener("DOMContentLoaded", () => {
    // Stage 3 HUD Controls
    const toggleContinuousBtn = document.getElementById("toggleContinuousBtn");
    const toggleWakeBtn = document.getElementById("toggleWakeBtn");
    const toggleMuteBtn = document.getElementById("toggleMuteBtn");
    const muteBtnLabel = document.getElementById("muteBtnLabel");
    const micSafetyBtn = document.getElementById("micSafetyBtn");
    const micSafetyLabel = document.getElementById("micSafetyLabel");
    const stopSpeakBtn = document.getElementById("stopSpeakBtn");
    const micBtn = document.getElementById("micBtn");

    // Telemetry & Status Badges
    const hudContinuousVal = document.getElementById("hudContinuousVal");
    const voiceStatusPill = document.getElementById("voiceStatusPill");
    const voiceStatusText = document.getElementById("voiceStatusText");
    const audioWaveform = document.getElementById("audioWaveform");
    const vadMeterBar = document.getElementById("vadMeterBar");
    const tonyAudioPlayer = document.getElementById("tonyAudioPlayer");

    // Chat UI Elements from Stage 1
    const messageStream = document.getElementById("messageStream");
    const welcomeHero = document.getElementById("welcomeHero");
    const typingIndicator = document.getElementById("typingIndicator");
    const errorBanner = document.getElementById("errorBanner");
    const errorMessage = document.getElementById("errorMessage");
    const chatViewport = document.getElementById("chatViewport");

    // System Configuration States
    let continuousMode = true;
    let wakeWordEnabled = true;
    let isMuted = false;
    let micHardwareEnabled = true;
    let silenceTimeoutSec = 1.2; // 1.2s silence commits turn
    const speechThreshold = 0.022; // RMS amplitude for speech detection

    // Conversation States:
    // 'IDLE' | 'WAKE_LISTENING' | 'LISTENING' | 'PROCESSING' | 'SPEAKING' | 'INTERRUPTED' | 'ERROR' | 'MIC_OFF'
    let currentState = "IDLE";

    // Media & Audio Context
    let mediaStream = null;
    let mediaRecorder = null;
    let audioChunks = [];
    let audioContext = null;
    let analyserNode = null;
    let vadIntervalId = null;
    let currentAudioUrl = null;

    // Turn Timing & Silence Trackers
    let speechStartTime = 0;
    let lastSpeechTime = 0;
    let silenceStartTime = 0;
    let hasDetectedVocalSpeech = false;
    let wakeSpeechBuffer = "";

    // Speech Recognition for ultra-low latency wake-phrase spotting
    let wakeRecognizer = null;

    // =========================================================================
    // HUD & State Management
    // =========================================================================
    function setVoiceState(state, customMessage = "") {
        if (!micHardwareEnabled && state !== "MIC_OFF") {
            state = "MIC_OFF";
        }

        currentState = state;
        voiceStatusPill.className = `voice-status-pill ${state.toLowerCase()}`;

        // Reset Waveform & Mic animations
        audioWaveform.className = "audio-waveform";
        micBtn.classList.remove("recording");
        stopSpeakBtn.style.display = "none";

        switch (state) {
            case "IDLE":
                voiceStatusText.textContent = customMessage || (wakeWordEnabled ? "Say 'Hey Tony' or click microphone" : "Click microphone to speak");
                if (window.tonySetOrbState) window.tonySetOrbState("idle");
                break;
            case "WAKE_LISTENING":
                voiceStatusText.textContent = customMessage || "Listening for wake word ('Hey Tony')...";
                audioWaveform.classList.add("wake");
                if (window.tonySetOrbState) window.tonySetOrbState("idle");
                break;
            case "LISTENING":
                voiceStatusText.textContent = customMessage || "Listening...";
                audioWaveform.classList.add("active");
                micBtn.classList.add("recording");
                if (window.tonySetOrbState) window.tonySetOrbState("listening");
                break;
            case "PROCESSING":
                voiceStatusText.textContent = customMessage || "Thinking...";
                if (window.tonySetOrbState) window.tonySetOrbState("thinking");
                break;
            case "SPEAKING":
                voiceStatusText.textContent = customMessage || "Speaking...";
                audioWaveform.classList.add("speaking");
                stopSpeakBtn.style.display = "flex";
                if (window.tonySetOrbState) window.tonySetOrbState("speaking");
                break;
            case "INTERRUPTED":
                voiceStatusText.textContent = customMessage || "Interrupted. Listening...";
                audioWaveform.classList.add("active");
                micBtn.classList.add("recording");
                if (window.tonySetOrbState) window.tonySetOrbState("listening");
                break;
            case "ERROR":
                voiceStatusText.textContent = customMessage || "Voice system alert";
                if (window.tonySetOrbState) window.tonySetOrbState("error");
                break;
            case "MIC_OFF":
                voiceStatusText.textContent = "MICROPHONE OFF (Hardware disabled)";
                if (window.tonySetOrbState) window.tonySetOrbState("idle");
                break;
        }
    }

    function showVoiceError(msg) {
        setVoiceState("ERROR", msg);
        if (errorMessage && errorBanner) {
            errorMessage.textContent = msg;
            errorBanner.classList.add("active");
        }
    }

    function scrollToBottom() {
        requestAnimationFrame(() => {
            chatViewport.scrollTop = chatViewport.scrollHeight;
        });
    }

    function formatTime(isoString) {
        if (!isoString) return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        try {
            return new Date(isoString).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        } catch {
            return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        }
    }

    function escapeHtml(text) {
        const div = document.createElement("div");
        div.textContent = text;
        return div.innerHTML;
    }

    function appendChatMessage(role, text, timestamp, metadata = {}) {
        if (welcomeHero) welcomeHero.style.display = "none";

        const isUser = role === "user";
        const row = document.createElement("div");
        row.className = `message-row ${isUser ? "user" : "assistant"}`;

        const avatar = document.createElement("div");
        avatar.className = "message-avatar";
        avatar.textContent = isUser ? "U" : "T";

        const bubbleWrapper = document.createElement("div");
        bubbleWrapper.className = "message-bubble-wrapper";

        const meta = document.createElement("div");
        meta.className = "message-meta";
        const timeFormatted = formatTime(timestamp);

        if (isUser) {
            const wakeTag = metadata.isWakeWord ? '<span class="wake-tag">WAKE</span>' : '';
            const voiceTag = metadata.isVoice ? '<span class="voice-tag">VOICE</span>' : '';
            meta.innerHTML = `<span>${timeFormatted}</span> &bull; <span>OPERATOR</span> ${wakeTag} ${voiceTag}`;
        } else {
            const modelTag = metadata.model ? `[${metadata.model}]` : "";
            meta.innerHTML = `<span>TONY CORE</span> ${modelTag ? `<span>${modelTag}</span>` : ""} &bull; <span>${timeFormatted}</span>`;
        }

        const bubble = document.createElement("div");
        bubble.className = "message-bubble";
        bubble.innerHTML = escapeHtml(text).replace(/\n/g, "<br>");

        bubbleWrapper.appendChild(meta);
        bubbleWrapper.appendChild(bubble);

        // Render inline Image Generation Card if present (Stage 6)
        if (metadata.image_result) {
            const imgData = metadata.image_result;
            const imgCard = document.createElement("div");
            imgCard.className = "inline-image-card";

            const isMock = imgData.provider === "mock";
            const badgeClass = isMock ? "caption-label mock-badge" : "caption-label";
            const badgeText = isMock ? "SIMULATED TEST ASSET (OFFLINE MOCK)" : `GENERATED VISUAL ASSET (${escapeHtml((imgData.provider || "").toUpperCase())} • ${escapeHtml(imgData.model || "")})`;
            const mockNotice = isMock ? `<div class="caption-mock-notice">ℹ️ Offline mock engine active (blue cybernetic grid). Configure IMAGE_API_KEY in .env for real AI generation.</div>` : "";

            imgCard.innerHTML = `
                <div class="inline-image-thumb-box" title="Click to view full image">
                    <img src="${escapeHtml(imgData.url)}" alt="${escapeHtml(imgData.prompt)}" class="inline-image-thumb">
                    <div class="inline-image-overlay">
                        <span>🔍 Full View</span>
                    </div>
                </div>
                <div class="inline-image-caption">
                    <div class="${badgeClass}">${badgeText}</div>
                    <div class="caption-prompt">"${escapeHtml(imgData.prompt)}"</div>
                    ${mockNotice}
                    <div class="inline-image-actions">
                        <button type="button" class="btn-img-action btn-img-view">View Full</button>
                        <a href="${escapeHtml(imgData.url)}" download="${escapeHtml(imgData.filename)}" class="btn-img-action btn-img-download">Download</a>
                    </div>
                </div>
            `;

            imgCard.querySelector(".inline-image-thumb-box").addEventListener("click", () => {
                if (window.tonyOpenImageLightbox) window.tonyOpenImageLightbox(imgData);
            });
            imgCard.querySelector(".btn-img-view").addEventListener("click", () => {
                if (window.tonyOpenImageLightbox) window.tonyOpenImageLightbox(imgData);
            });

            bubbleWrapper.appendChild(imgCard);
        }

        // Render inline Task Plan Card if present (Stage 8)
        if (metadata.task_plan && window.tonyRenderTaskCard) {
            window.tonyRenderTaskCard(metadata.task_plan, bubbleWrapper);
        }

        row.appendChild(avatar);
        row.appendChild(bubbleWrapper);

        messageStream.appendChild(row);
        scrollToBottom();
    }

    // =========================================================================
    // Web Audio API VAD (Voice Activity Detection) Engine
    // =========================================================================
    async function initAudioEngine() {
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            showVoiceError("Audio input not supported in this browser.");
            return false;
        }

        try {
            if (!mediaStream) {
                mediaStream = await navigator.mediaDevices.getUserMedia({
                    audio: {
                        echoCancellation: true,
                        noiseSuppression: true,
                        autoGainControl: true
                    }
                });
            }

            if (!audioContext) {
                const AudioCtx = window.AudioContext || window.webkitAudioContext;
                audioContext = new AudioCtx();
            }

            if (audioContext.state === "suspended") {
                await audioContext.resume();
            }

            const source = audioContext.createMediaStreamSource(mediaStream);
            analyserNode = audioContext.createAnalyser();
            analyserNode.fftSize = 512;
            analyserNode.smoothingTimeConstant = 0.3;
            source.connect(analyserNode);

            startVADMonitoring();
            initWakeRecognizer();
            return true;

        } catch (err) {
            console.error("Audio engine initialization failure:", err);
            if (err.name === "NotAllowedError") {
                showVoiceError("Microphone access denied. Please grant permission in your browser.");
            } else {
                showVoiceError(`Microphone setup error: ${err.message}`);
            }
            return false;
        }
    }

    function calculateRMS(dataArray) {
        let sum = 0;
        for (let i = 0; i < dataArray.length; i++) {
            const val = (dataArray[i] - 128) / 128.0;
            sum += val * val;
        }
        return Math.sqrt(sum / dataArray.length);
    }

    function startVADMonitoring() {
        if (vadIntervalId) clearInterval(vadIntervalId);

        const dataArray = new Uint8Array(analyserNode.frequencyBinCount);

        vadIntervalId = setInterval(() => {
            if (!micHardwareEnabled || !analyserNode) {
                if (vadMeterBar) vadMeterBar.style.width = "0%";
                return;
            }

            analyserNode.getByteTimeDomainData(dataArray);
            const rms = calculateRMS(dataArray);

            // Update live VAD level meter bar
            if (vadMeterBar) {
                const meterPercent = Math.min(100, Math.round((rms / 0.15) * 100));
                vadMeterBar.style.width = `${meterPercent}%`;
            }

            const now = Date.now();
            const isSpeakingNow = rms >= speechThreshold;

            // -----------------------------------------------------------------
            // INTERCEPTION & AUDIO DUCKING (If TONY is currently speaking)
            // -----------------------------------------------------------------
            if (currentState === "SPEAKING") {
                if (isSpeakingNow) {
                    console.log("User voice activity detected while TONY is speaking! Triggering interruption...");
                    stopSpeaking();
                    setVoiceState("INTERRUPTED");
                    beginSpeechRecording();
                    return;
                }
            }

            // -----------------------------------------------------------------
            // ACTIVE SPEECH RECORDING (VAD Turn Taking)
            // -----------------------------------------------------------------
            if (currentState === "LISTENING" || currentState === "INTERRUPTED") {
                if (isSpeakingNow) {
                    hasDetectedVocalSpeech = true;
                    lastSpeechTime = now;
                    silenceStartTime = 0;
                } else if (hasDetectedVocalSpeech) {
                    // Speech was active, now silent
                    if (silenceStartTime === 0) {
                        silenceStartTime = now;
                    }

                    const silenceElapsedSec = (now - silenceStartTime) / 1000.0;
                    if (silenceElapsedSec >= silenceTimeoutSec) {
                        console.log(`VAD silence threshold reached (${silenceElapsedSec.toFixed(2)}s). Committing turn.`);
                        commitTurnSpeech();
                    }
                }
            }
        }, 50); // Analyze every 50ms
    }

    // =========================================================================
    // Local Wake-Word Engine ("Hey Tony" / "Tony")
    // =========================================================================
    function initWakeRecognizer() {
        const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (!SpeechRec) {
            console.log("Browser SpeechRecognition unavailable for wake spotting; falling back to backend pattern spotting.");
            return;
        }

        try {
            wakeRecognizer = new SpeechRec();
            wakeRecognizer.continuous = true;
            wakeRecognizer.interimResults = true;
            wakeRecognizer.lang = "en-US";

            wakeRecognizer.onresult = (event) => {
                if (!micHardwareEnabled) return;

                for (let i = event.resultIndex; i < event.results.length; i++) {
                    const transcript = event.results[i][0].transcript.toLowerCase().trim();
                    console.debug("Wake recognizer stream:", transcript);

                    // Check for wake word trigger
                    if (currentState === "WAKE_LISTENING" || currentState === "IDLE") {
                        if (transcript.includes("hey tony") || transcript.includes("hi tony") || transcript.includes("tony")) {
                            console.log("Wake phrase matched in audio stream:", transcript);
                            handleWakeWordTriggered(transcript);
                            break;
                        }
                    } else if (currentState === "SPEAKING") {
                        if (transcript.includes("stop") || transcript.includes("tony stop") || transcript.includes("quiet")) {
                            console.log("Stop command recognized during speech!");
                            stopSpeaking();
                            setVoiceState("IDLE", "Speech stopped.");
                            break;
                        }
                    }
                }
            };

            wakeRecognizer.onerror = (e) => {
                if (e.error !== "no-speech") {
                    console.debug("Wake recognizer notice:", e.error);
                }
            };

            wakeRecognizer.onend = () => {
                // Keep wake recognizer active if in continuous/wake mode and mic is live
                if (micHardwareEnabled && (currentState === "WAKE_LISTENING" || (continuousMode && wakeWordEnabled))) {
                    try {
                        wakeRecognizer.start();
                    } catch (e) {
                        // Ignore already started
                    }
                }
            };

            if (wakeWordEnabled && micHardwareEnabled) {
                try {
                    wakeRecognizer.start();
                } catch (e) {}
            }

        } catch (e) {
            console.warn("Could not start local wake recognizer:", e);
        }
    }

    function handleWakeWordTriggered(fullTranscript = "") {
        console.log("Waking up TONY...");
        setVoiceState("LISTENING", "Yes? I am listening...");

        // Extract any immediate query spoken in the same breath (e.g., "Hey Tony what is Python")
        let cleanedQuery = fullTranscript
            .replace(/^.*?(hey tony|hi tony|tony)[,!?:;.]*/i, "")
            .trim();

        beginSpeechRecording();

        if (cleanedQuery.length > 5) {
            // User already included the query with the wake word!
            wakeSpeechBuffer = cleanedQuery;
        }
    }

    // =========================================================================
    // Audio Recording Pipeline
    // =========================================================================
    function beginSpeechRecording() {
        if (!mediaStream) return;

        try {
            audioChunks = [];
            hasDetectedVocalSpeech = false;
            silenceStartTime = 0;
            speechStartTime = Date.now();
            lastSpeechTime = Date.now();

            const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
                ? "audio/webm;codecs=opus"
                : MediaRecorder.isTypeSupported("audio/webm")
                    ? "audio/webm"
                    : "";

            mediaRecorder = mimeType ? new MediaRecorder(mediaStream, { mimeType }) : new MediaRecorder(mediaStream);

            mediaRecorder.ondataavailable = (e) => {
                if (e.data && e.data.size > 0) {
                    audioChunks.push(e.data);
                }
            };

            mediaRecorder.onstop = async () => {
                const totalDuration = (Date.now() - speechStartTime) / 1000.0;
                if (audioChunks.length === 0 || totalDuration < 0.3) {
                    returnToListeningOrIdle();
                    return;
                }

                const audioBlob = new Blob(audioChunks, { type: mediaRecorder.mimeType || "audio/webm" });
                if (audioBlob.size < 250) {
                    returnToListeningOrIdle();
                    return;
                }

                await processTurnAudio(audioBlob);
            };

            mediaRecorder.start(100);
            if (currentState !== "INTERRUPTED") {
                setVoiceState("LISTENING");
            }

        } catch (err) {
            console.error("Failed to start MediaRecorder:", err);
            showVoiceError(`Recording error: ${err.message}`);
        }
    }

    function commitTurnSpeech() {
        if (mediaRecorder && mediaRecorder.state === "recording") {
            setVoiceState("PROCESSING", "Transcribing speech...");
            mediaRecorder.stop();
        }
    }

    // =========================================================================
    // Turn Processing: STT -> AI -> TTS -> Return to Listen
    // =========================================================================
    async function processTurnAudio(audioBlob) {
        setVoiceState("PROCESSING", "Thinking...");
        if (typingIndicator) typingIndicator.classList.add("active");

        try {
            // STEP A: Transcribe spoken audio via STT endpoint
            const formData = new FormData();
            formData.append("audio", audioBlob, "user_speech.webm");

            const sttRes = await fetch("/api/voice/transcribe", {
                method: "POST",
                body: formData
            });

            const sttData = await sttRes.json();
            if (!sttRes.ok) {
                showVoiceError(sttData.error || `STT Error (HTTP ${sttRes.status})`);
                if (typingIndicator) typingIndicator.classList.remove("active");
                returnToListeningOrIdle();
                return;
            }

            let transcribedText = (sttData.text || "").trim();

            // If prompt was captured in wake buffer, supplement it
            if (!transcribedText && wakeSpeechBuffer) {
                transcribedText = wakeSpeechBuffer;
            }
            wakeSpeechBuffer = "";

            if (!transcribedText) {
                console.log("No intelligible speech detected in audio turn.");
                if (typingIndicator) typingIndicator.classList.remove("active");
                returnToListeningOrIdle();
                return;
            }

            // STEP B: Check for wake word prefix and strip if necessary
            let isWakeWordTurn = false;
            try {
                const wakeCheckRes = await fetch("/api/voice/wake-check", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ text: transcribedText })
                });
                if (wakeCheckRes.ok) {
                    const wakeCheckData = await wakeCheckRes.json();
                    if (wakeCheckData.detected) {
                        isWakeWordTurn = true;
                        if (wakeCheckData.trailing_prompt) {
                            transcribedText = wakeCheckData.trailing_prompt;
                        } else if (wakeCheckData.wake_only) {
                            // User said ONLY "Tony!" or "Tony"
                            const wakePhrase = wakeCheckData.wake_phrase ? (wakeCheckData.wake_phrase.charAt(0).toUpperCase() + wakeCheckData.wake_phrase.slice(1)) : "Tony!";
                            const wakeResp = wakeCheckData.wake_response || "Yes, Sir.";
                            appendChatMessage("user", wakePhrase, new Date().toISOString(), { isVoice: true, isWakeWord: true });
                            appendChatMessage("assistant", wakeResp, new Date().toISOString());
                            if (typingIndicator) typingIndicator.classList.remove("active");
                            await speakResponse(wakeResp);
                            return;
                        }
                    }
                }
            } catch (e) {
                console.warn("Wake check skipped:", e);
            }

            // STEP C: Render user query in chat
            appendChatMessage("user", transcribedText, new Date().toISOString(), {
                isVoice: true,
                isWakeWord: isWakeWordTurn
            });

            // STEP D: Dispatch to TONY AI Core (/api/chat)
            const chatRes = await fetch("/api/chat", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ message: transcribedText })
            });

            const chatData = await chatRes.json();
            if (!chatRes.ok) {
                showVoiceError(chatData.error || `AI Chat error (HTTP ${chatRes.status})`);
                if (typingIndicator) typingIndicator.classList.remove("active");
                returnToListeningOrIdle();
                return;
            }

            const replyText = chatData.response;
            appendChatMessage("assistant", replyText, chatData.timestamp, {
                model: chatData.model,
                provider: chatData.provider,
                image_result: chatData.image_result
            });
            window.dispatchEvent(new Event("tonyMessageCompleted"));

            if (typingIndicator) typingIndicator.classList.remove("active");

            // STEP E: Synthesize speech and play aloud (unless Muted)
            if (!isMuted) {
                await speakResponse(replyText);
            } else {
                returnToListeningOrIdle();
            }

        } catch (err) {
            console.error("Turn processing error:", err);
            showVoiceError(`Voice pipeline error: ${err.message}`);
            if (typingIndicator) typingIndicator.classList.remove("active");
            returnToListeningOrIdle();
        }
    }

    // =========================================================================
    // Speech Synthesis & Turn-Taking Loop
    // =========================================================================
    async function speakResponse(text) {
        if (!text || !text.trim() || isMuted) {
            returnToListeningOrIdle();
            return;
        }

        setVoiceState("SPEAKING", "Synthesizing voice...");

        try {
            const ttsRes = await fetch("/api/voice/speak", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ text })
            });

            if (!ttsRes.ok) {
                returnToListeningOrIdle();
                return;
            }

            const audioBlob = await ttsRes.blob();
            if (audioBlob.size === 0) {
                returnToListeningOrIdle();
                return;
            }

            if (currentAudioUrl) {
                URL.revokeObjectURL(currentAudioUrl);
            }

            currentAudioUrl = URL.createObjectURL(audioBlob);
            tonyAudioPlayer.src = currentAudioUrl;
            setVoiceState("SPEAKING", "TONY is speaking...");

            tonyAudioPlayer.onended = () => {
                if (currentAudioUrl) {
                    URL.revokeObjectURL(currentAudioUrl);
                    currentAudioUrl = null;
                }
                console.log("TONY finished speaking. Returning to continuous conversation loop.");
                returnToListeningOrIdle();
            };

            tonyAudioPlayer.onerror = () => {
                returnToListeningOrIdle();
            };

            await tonyAudioPlayer.play();

        } catch (err) {
            console.error("Speech playback error:", err);
            returnToListeningOrIdle();
        }
    }

    function stopSpeaking() {
        if (tonyAudioPlayer) {
            tonyAudioPlayer.pause();
            tonyAudioPlayer.currentTime = 0;
        }
        if (currentAudioUrl) {
            URL.revokeObjectURL(currentAudioUrl);
            currentAudioUrl = null;
        }
    }

    function returnToListeningOrIdle() {
        if (!micHardwareEnabled) {
            setVoiceState("MIC_OFF");
            return;
        }

        if (continuousMode) {
            if (wakeWordEnabled) {
                setVoiceState("WAKE_LISTENING", "Listening for wake word ('Hey Tony')...");
            } else {
                setVoiceState("LISTENING", "Listening...");
                beginSpeechRecording();
            }
        } else {
            setVoiceState("IDLE");
        }
    }

    // =========================================================================
    // User Control Handlers
    // =========================================================================

    // Continuous Mode Toggle
    toggleContinuousBtn.addEventListener("click", () => {
        continuousMode = !continuousMode;
        if (continuousMode) {
            toggleContinuousBtn.classList.add("active");
            toggleContinuousBtn.querySelector("span:last-child").textContent = "Continuous: ON";
            hudContinuousVal.textContent = "CONTINUOUS";
            hudContinuousVal.classList.add("active");
            initAudioEngine().then(ok => {
                if (ok) returnToListeningOrIdle();
            });
        } else {
            toggleContinuousBtn.classList.remove("active");
            toggleContinuousBtn.querySelector("span:last-child").textContent = "Continuous: OFF";
            hudContinuousVal.textContent = "MANUAL";
            hudContinuousVal.classList.remove("active");
            if (currentState === "WAKE_LISTENING" || currentState === "LISTENING") {
                setVoiceState("IDLE");
            }
        }
    });

    // Wake Word Toggle
    toggleWakeBtn.addEventListener("click", () => {
        wakeWordEnabled = !wakeWordEnabled;
        if (wakeWordEnabled) {
            toggleWakeBtn.classList.add("active");
            toggleWakeBtn.querySelector("span:last-child").textContent = "Wake Word: ON";
        } else {
            toggleWakeBtn.classList.remove("active");
            toggleWakeBtn.querySelector("span:last-child").textContent = "Wake Word: OFF";
        }
        returnToListeningOrIdle();
    });

    // Mute TONY Toggle
    toggleMuteBtn.addEventListener("click", () => {
        isMuted = !isMuted;
        if (isMuted) {
            stopSpeaking();
            muteBtnLabel.textContent = "Unmute";
            toggleMuteBtn.classList.add("hud-btn-stop");
        } else {
            muteBtnLabel.textContent = "Mute";
            toggleMuteBtn.classList.remove("hud-btn-stop");
        }
    });

    // Stop Speaking Button
    stopSpeakBtn.addEventListener("click", () => {
        stopSpeaking();
        returnToListeningOrIdle();
    });

    // Hardware Microphone Safety Switch (Safety Control)
    micSafetyBtn.addEventListener("click", () => {
        micHardwareEnabled = !micHardwareEnabled;

        if (micHardwareEnabled) {
            // Enable Microphone
            micSafetyBtn.className = "mic-safety-btn live";
            micSafetyLabel.textContent = "MIC ON";
            initAudioEngine().then(ok => {
                if (ok) returnToListeningOrIdle();
            });
        } else {
            // DISABLE MICROPHONE (Cutoff hardware access completely)
            stopSpeaking();
            if (mediaRecorder && mediaRecorder.state !== "inactive") {
                mediaRecorder.stop();
            }
            if (mediaStream) {
                mediaStream.getTracks().forEach(t => t.stop());
                mediaStream = null;
            }
            if (audioContext) {
                audioContext.suspend();
            }
            if (wakeRecognizer) {
                try { wakeRecognizer.stop(); } catch (e) {}
            }

            micSafetyBtn.className = "mic-safety-btn disabled";
            micSafetyLabel.textContent = "MIC OFF";
            setVoiceState("MIC_OFF");
        }
    });

    // Manual Mic Click
    micBtn.addEventListener("click", async () => {
        if (!micHardwareEnabled) {
            alert("Microphone is currently OFF. Click 'MIC OFF' to re-enable audio hardware first.");
            return;
        }

        const ok = await initAudioEngine();
        if (!ok) return;

        if (currentState === "LISTENING") {
            commitTurnSpeech();
        } else if (currentState === "SPEAKING") {
            stopSpeaking();
            setVoiceState("LISTENING");
            beginSpeechRecording();
        } else {
            setVoiceState("LISTENING");
            beginSpeechRecording();
        }
    });

    // Initial Engine Bootstrap
    initAudioEngine().then(ok => {
        if (ok && continuousMode) {
            returnToListeningOrIdle();
        }
    });
});
