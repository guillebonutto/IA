/**
 * AURA CORE - Cliente Frontend Moderno
 * Modo Híbrido: Debate Multi-Agente (Groq 70B vs Gemini Flash) + Agente Local (Qwen llama.cpp).
 * Destilación Continua & Aprendizaje RAG.
 */

document.addEventListener("DOMContentLoaded", () => {
    // Referencias DOM principales
    const messagesStream = document.getElementById("messages-stream");
    const welcomeHero = document.getElementById("welcome-hero");
    const chatForm = document.getElementById("chat-form");
    const userPrompt = document.getElementById("user-prompt");
    const btnSubmit = document.getElementById("btn-submit");
    const btnResetChat = document.getElementById("btn-reset-chat");
    const btnNewChat = document.getElementById("btn-new-chat");

    // Telemetría & Sidebar
    const badgeEngine = document.getElementById("badge-engine");
    const valDisk = document.getElementById("val-disk");
    const badgeGroq = document.getElementById("badge-groq");
    const badgeGemini = document.getElementById("badge-gemini");
    const valDistillCount = document.getElementById("val-distill-count");
    const badgeWatchdogBot = document.getElementById("badge-watchdog-bot");
    const valWatchdogProcs = document.getElementById("val-watchdog-procs");
    const valWatchdogAlerts = document.getElementById("val-watchdog-alerts");

    // Barra de Navegación & Modos
    const navModeTitle = document.getElementById("nav-mode-title");
    const navModeSubtitle = document.getElementById("nav-mode-subtitle");
    const btnModeDebate = document.getElementById("btn-mode-debate");
    const btnModeLocal = document.getElementById("btn-mode-local");
    const btnModeAuto = document.getElementById("btn-mode-auto");
    const modeButtons = [btnModeDebate, btnModeLocal, btnModeAuto];

    // Modal RAG
    const btnAddDoc = document.getElementById("btn-add-doc");
    const modalRag = document.getElementById("modal-rag");
    const btnCloseModal = document.getElementById("btn-close-modal");
    const btnCancelRag = document.getElementById("btn-cancel-rag");
    const btnSaveRag = document.getElementById("btn-save-rag");
    const ragTitle = document.getElementById("rag-title");
    const ragContent = document.getElementById("rag-content");

    // Modal Claves Cloud (Groq & Gemini)
    const btnOpenKeys = document.getElementById("btn-open-keys");
    const modalKeys = document.getElementById("modal-keys");
    const btnCloseKeysModal = document.getElementById("btn-close-keys-modal");
    const btnCancelKeys = document.getElementById("btn-cancel-keys");
    const btnSaveKeys = document.getElementById("btn-save-keys");
    const groqKeyInput = document.getElementById("groq-key-input");
    const geminiKeyInput = document.getElementById("gemini-key-input");
    const groqStatusText = document.getElementById("groq-status-text");
    const geminiStatusText = document.getElementById("gemini-status-text");

    // Estado activo (por defecto Local Offline para inferencia directa)
    let currentMode = localStorage.getItem("aura_mode") || "local";
    let chatHistory = [];

    // -------------------------------------------------------------
    // GESTIÓN DE MODOS (DEBATE DUAL VS LOCAL OFFLINE)
    // -------------------------------------------------------------
    function setMode(mode) {
        currentMode = mode;
        localStorage.setItem("aura_mode", mode);

        modeButtons.forEach(btn => {
            if (!btn) return;
            if (btn.getAttribute("data-mode") === mode) {
                btn.classList.add("active");
            } else {
                btn.classList.remove("active");
            }
        });

        if (mode === "debate") {
            navModeTitle.textContent = "⚔️ Cerebro Dual: Groq & Gemini";
            navModeSubtitle.textContent = "Debate adversarial de frontera con destilación para auto-entrenamiento local";
        } else if (mode === "local") {
            navModeTitle.textContent = "⚡ Asistente Local Offline";
            navModeSubtitle.textContent = "Inferencia 100% privada en tu PC con llama.cpp (AVX2/Vulkan)";
        } else {
            navModeTitle.textContent = "🔄 Modo Inteligente Híbrido";
            navModeSubtitle.textContent = "Debate en la nube para análisis complejo, local para tareas directas";
        }
    }

    modeButtons.forEach(btn => {
        if (!btn) return;
        btn.addEventListener("click", () => {
            setMode(btn.getAttribute("data-mode"));
        });
    });

    setMode(currentMode);

    // Auto-ajuste de altura de textarea
    userPrompt.addEventListener("input", () => {
        userPrompt.style.height = "auto";
        userPrompt.style.height = Math.min(userPrompt.scrollHeight, 180) + "px";
    });

    // Enviar con Enter (Shift+Enter para salto de línea)
    userPrompt.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            chatForm.dispatchEvent(new Event("submit"));
        }
    });

    // Botón para reiniciar historial de chat
    const handleResetChat = () => {
        chatHistory = [];
        messagesStream.innerHTML = "";
        if (welcomeHero) {
            welcomeHero.style.display = "block";
            messagesStream.appendChild(welcomeHero);
        }
        appendMessage("ai", "🧹 **Historial reiniciado.** Puedes comenzar una nueva consulta limpia.");
    };

    if (btnResetChat) {
        btnResetChat.addEventListener("click", handleResetChat);
    }
    if (btnNewChat) {
        btnNewChat.addEventListener("click", handleResetChat);
    }

    // -------------------------------------------------------------
    // TELEMETRÍA Y POLLING
    // -------------------------------------------------------------
    async function updateTelemetry() {
        try {
            const res = await fetch("/api/status");
            if (!res.ok) throw new Error("Offline");
            const data = await res.json();

            // Estado motor local
            if (data.server_online) {
                badgeEngine.className = "stat-val status-pill online";
                badgeEngine.textContent = "Activo (llama.cpp)";
            } else {
                badgeEngine.className = "stat-val status-pill offline";
                badgeEngine.textContent = "Iniciando motor...";
            }

            // Espacio en disco
            if (data.system && data.system.disk_free_gb !== undefined) {
                valDisk.textContent = `${data.system.disk_free_gb} GB`;
            }

            // Muestras destiladas
            if (valDistillCount && data.distilled_samples !== undefined) {
                valDistillCount.textContent = `${data.distilled_samples} pares`;
            }

            // Proveedores de debate
            if (data.debate) {
                updateProviderBadges(data.debate);
            }

            // Consultar estado del Watchdog & Supervisor de Trading
            try {
                const wdRes = await fetch("/api/watchdog/status");
                if (wdRes.ok) {
                    const wd = await wdRes.json();
                    if (badgeWatchdogBot) {
                        const hasProcs = wd.process_count > 0;
                        badgeWatchdogBot.className = hasProcs ? "stat-val status-pill online" : "stat-val status-pill";
                        badgeWatchdogBot.textContent = hasProcs ? "Activo (Operando)" : "En Espera";
                    }
                    if (valWatchdogProcs) {
                        valWatchdogProcs.textContent = `${wd.process_count} scripts`;
                    }
                    if (valWatchdogAlerts) {
                        const alertCount = (wd.recent_alerts || []).length;
                        valWatchdogAlerts.textContent = `${alertCount} alertas`;
                        valWatchdogAlerts.className = alertCount > 0 ? "stat-val accent-amber" : "stat-val accent-green";
                    }
                }
            } catch (wdErr) {}
        } catch (err) {
            badgeEngine.className = "stat-val status-pill offline";
            badgeEngine.textContent = "Desconectado";
        }
    }

    function updateProviderBadges(debate) {
        if (badgeGroq) {
            if (debate.groq_ready) {
                badgeGroq.className = "status-pill online";
                badgeGroq.textContent = "Conectado";
            } else {
                badgeGroq.className = "status-pill offline";
                badgeGroq.textContent = "Sin Clave";
            }
        }

        if (badgeGemini) {
            if (debate.gemini_ready) {
                badgeGemini.className = "status-pill online";
                badgeGemini.textContent = "Conectado";
            } else {
                badgeGemini.className = "status-pill offline";
                badgeGemini.textContent = "Sin Clave";
            }
        }
    }

    updateTelemetry();
    setInterval(updateTelemetry, 4000);

    // Sugerencias rápidas (Chips)
    document.querySelectorAll(".suggestion-chip").forEach(chip => {
        chip.addEventListener("click", () => {
            const text = chip.getAttribute("data-prompt");
            userPrompt.value = text;
            userPrompt.style.height = "auto";
            userPrompt.style.height = userPrompt.scrollHeight + "px";
            userPrompt.focus();
        });
    });

    // -------------------------------------------------------------
    // ENVÍO DE MENSAJES Y CHAT AGÉNTICO
    // -------------------------------------------------------------
    chatForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const text = userPrompt.value.trim();
        if (!text) return;

        if (welcomeHero) {
            welcomeHero.style.display = "none";
        }

        appendMessage("user", text);
        const priorHistory = chatHistory.slice(-8);
        chatHistory.push({ role: "user", content: text });
        userPrompt.value = "";
        userPrompt.style.height = "auto";
        btnSubmit.disabled = true;

        const loadingMsg = currentMode === "debate"
            ? "⚔️ Orquestando debate: Groq (Llama 70B) vs Gemini (1.5 Flash)..."
            : "⚡ Procesando y ejecutando en tu PC...";
        const loadingId = appendLoadingBubble(loadingMsg);

        try {
            const res = await fetch("/api/chat", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    message: text,
                    mode: currentMode,
                    history: priorHistory
                })
            });

            const rawText = await res.text();
            let data;
            try {
                data = JSON.parse(rawText);
            } catch (jsonErr) {
                const match = rawText.match(/^\s*(\{[\s\S]*?\})\s*(?:\{.*)?$/);
                if (match) {
                    data = JSON.parse(match[1]);
                } else {
                    throw new Error(`Respuesta inválida del servidor: ${jsonErr.message}`);
                }
            }
            removeLoadingBubble(loadingId);

            if (data.need_keys) {
                appendMessage("ai", `🔑 **Configuración requerida:** ${data.error}`, [], [], "need_keys");
            } else if (data.success) {
                chatHistory.push({ role: "assistant", content: data.response });
                if (chatHistory.length > 12) chatHistory = chatHistory.slice(-12);
                appendMessage("ai", data.response, data.tool_events, data.debate_rounds, data.mode_used);
                updateTelemetry();
            } else {
                appendMessage("ai", `❌ **Error:** ${data.error || "No se pudo obtener respuesta."}`);
            }
        } catch (err) {
            removeLoadingBubble(loadingId);
            appendMessage("ai", `⚠️ **Error de conexión con el agente:** ${err.message}`);
        } finally {
            btnSubmit.disabled = false;
            userPrompt.focus();
            scrollToBottom();
        }
    });

    // -------------------------------------------------------------
    // RENDERIZADO DE BURBUJAS Y ACORDEÓN DE DEBATE
    // -------------------------------------------------------------
    function appendMessage(role, text, toolEvents = [], debateRounds = [], modeUsed = "") {
        const row = document.createElement("div");
        row.className = `msg-row ${role}`;

        const avatar = document.createElement("div");
        avatar.className = `msg-avatar ${role === "user" ? "user-av" : "ai"}`;
        avatar.textContent = role === "user" ? "TÚ" : (modeUsed === "debate_cloud" ? "⚔️" : "IA");

        const bubble = document.createElement("div");
        bubble.className = "msg-bubble";

        // Si la IA ejecutó herramientas del sistema
        const executedTools = (toolEvents || []).filter(e => e.type === "tool_start");
        if (role === "ai" && executedTools.length > 0) {
            const toolsBox = document.createElement("div");
            toolsBox.className = "tools-executed-box";

            const toolsHeader = document.createElement("div");
            toolsHeader.className = "tools-executed-header";
            toolsHeader.innerHTML = `
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline>
                </svg>
                Herramientas del Sistema Ejecutadas (${executedTools.length})
            `;
            toolsBox.appendChild(toolsHeader);

            const toolsBody = document.createElement("div");
            toolsBody.className = "tools-executed-body";

            toolEvents.forEach(evt => {
                if (evt.type === "tool_start") {
                    const item = document.createElement("div");
                    item.className = "tool-run-item";
                    let detail = "";
                    if (evt.tool === "run_command") detail = `$ ${evt.args.command || ""}`;
                    else if (evt.tool === "list_directory") detail = `Explorar: ${evt.args.dir_path || ""}`;
                    else if (evt.tool === "read_file") detail = `Leer: ${evt.args.file_path || ""}`;
                    else if (evt.tool === "write_file") detail = `Escribir: ${evt.args.file_path || ""}`;
                    else detail = JSON.stringify(evt.args);

                    item.innerHTML = `<span class="tool-run-badge">▶ [${evt.tool}]</span> <span>${escapeHtml(detail)}</span>`;
                    toolsBody.appendChild(item);
                }
            });

            toolsBox.appendChild(toolsBody);
            bubble.appendChild(toolsBox);
        }

        // Si hubo debate multi-agente (Groq vs Gemini)
        if (role === "ai" && debateRounds && debateRounds.length > 1) {
            const debateBox = document.createElement("div");
            debateBox.className = "debate-timeline-box";

            const debateHeader = document.createElement("div");
            debateHeader.className = "debate-timeline-header";
            debateHeader.innerHTML = `
                <div class="debate-timeline-title">
                    <span>⚔️</span>
                    <span>Debate Adversarial de Frontera (${debateRounds.length} Rondas)</span>
                </div>
                <span class="agent-badge consensus">Consenso Alcanzado</span>
            `;
            debateBox.appendChild(debateHeader);

            const roundsList = document.createElement("div");
            roundsList.className = "debate-rounds-list";

            debateRounds.forEach((rnd, idx) => {
                // Solo mostrar rondas previas en el acordeón (la final va abajo en el cuerpo principal)
                if (idx < debateRounds.length - 1) {
                    const roundItem = document.createElement("div");
                    roundItem.className = "debate-round-item";

                    let badgeClass = "groq";
                    if (rnd.agent && rnd.agent.toLowerCase().includes("gemini")) badgeClass = "gemini";
                    else if (rnd.agent && rnd.agent.toLowerCase().includes("consenso")) badgeClass = "consensus";

                    roundItem.innerHTML = `
                        <button type="button" class="debate-round-toggle">
                            <div class="debate-round-left">
                                <span class="agent-badge ${badgeClass}">${escapeHtml(rnd.agent || "Agente")}</span>
                                <span class="debate-round-title">${escapeHtml(rnd.role || `Ronda ${idx + 1}`)}</span>
                            </div>
                            <span class="debate-round-chevron">▼</span>
                        </button>
                        <div class="debate-round-content">
                            ${formatMarkdown(rnd.content || "")}
                        </div>
                    `;

                    const toggleBtn = roundItem.querySelector(".debate-round-toggle");
                    toggleBtn.addEventListener("click", () => {
                        roundItem.classList.toggle("open");
                    });

                    roundsList.appendChild(roundItem);
                }
            });

            debateBox.appendChild(roundsList);
            bubble.appendChild(debateBox);

            // Cinta de consenso definitivo
            // Cinta de consenso definitivo dinámico
            const hasGemini = debateRounds.some(r => r.agent && r.agent.toLowerCase().includes("gemini"));
            const consensusTitle = hasGemini ? "Solución Final Consensuada (Groq 120B + Google Gemini)" : "Solución Final Consensuada (Groq 120B + Groq 20B)";
            const consensusRibbon = document.createElement("div");
            consensusRibbon.className = "consensus-ribbon";
            consensusRibbon.innerHTML = `
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                    <polyline points="20 6 9 17 4 12"></polyline>
                </svg>
                ${escapeHtml(consensusTitle)}
            `;
            bubble.appendChild(consensusRibbon);
        }

        // Si se necesitan claves, agregar botón de acceso directo al modal
        if (modeUsed === "need_keys") {
            const btnOpen = document.createElement("button");
            btnOpen.className = "btn-primary-action";
            btnOpen.style.marginTop = "12px";
            btnOpen.innerHTML = "⚙️ Abrir Configuración de Claves Cloud";
            btnOpen.addEventListener("click", openKeysModal);
            bubble.appendChild(btnOpen);
        }

        // Contenido del mensaje formateado (Markdown simple)
        const textContainer = document.createElement("div");
        textContainer.innerHTML = formatMarkdown(text);
        bubble.appendChild(textContainer);

        // Si fue una respuesta sintetizada por debate, mostrar badge de destilación
        if (role === "ai" && modeUsed === "debate_cloud") {
            const distillBadge = document.createElement("div");
            distillBadge.className = "distill-badge-bubble";
            distillBadge.innerHTML = `
                <span>💾</span>
                <span>Par de razonamiento registrado para auto-entrenamiento (distillation dataset)</span>
            `;
            bubble.appendChild(distillBadge);
        }

        // Barra de Feedback y Corrección del Usuario
        if (role === "ai" && !text.startsWith("❌") && !text.startsWith("🧹") && !text.startsWith("⚠️")) {
            const feedbackBar = document.createElement("div");
            feedbackBar.className = "msg-feedback-bar";
            feedbackBar.innerHTML = `
                <button type="button" class="feedback-btn btn-thumb-up" title="Respuesta precisa y útil">
                    <span>👍</span>
                    <span>Correcto</span>
                </button>
                <button type="button" class="feedback-btn btn-thumb-down" title="Respuesta errónea o incompleta">
                    <span>👎</span>
                </button>
                <button type="button" class="feedback-btn btn-correction" title="Corregir a AURA y guardar en su memoria">
                    <span>✏️ Corregir</span>
                </button>
                <span class="feedback-status"></span>
            `;

            const btnUp = feedbackBar.querySelector(".btn-thumb-up");
            const btnDown = feedbackBar.querySelector(".btn-thumb-down");
            const btnCorrect = feedbackBar.querySelector(".btn-correction");
            const statusSpan = feedbackBar.querySelector(".feedback-status");

            const lastUserMsg = chatHistory.slice().reverse().find(m => m.role === "user");
            const queryText = lastUserMsg ? lastUserMsg.content : "";

            btnUp.addEventListener("click", async () => {
                btnUp.classList.add("active");
                btnDown.classList.remove("active");
                statusSpan.textContent = "¡Registrado!";
                try {
                    await fetch("/api/feedback", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({
                            query: queryText,
                            correction: "CORRECTO: El usuario validó la respuesta como adecuada y precisa.",
                            agent_output: text
                        })
                    });
                } catch(e) {}
            });

            btnDown.addEventListener("click", () => {
                btnDown.classList.add("active");
                btnUp.classList.remove("active");
                openCorrectionBox();
            });

            btnCorrect.addEventListener("click", () => {
                openCorrectionBox();
            });

            function openCorrectionBox() {
                if (bubble.querySelector(".inline-correction-box")) return;
                const corrBox = document.createElement("div");
                corrBox.className = "inline-correction-box";
                corrBox.innerHTML = `
                    <div class="correction-header">
                        <span>💡 ¿Qué debió responder o hacer AURA?</span>
                        <button type="button" class="btn-close-corr" title="Cerrar">✕</button>
                    </div>
                    <textarea class="correction-input" placeholder="Escribe la respuesta esperada o lo que faltó..."></textarea>
                    <div class="correction-actions">
                        <button type="button" class="btn-save-corr">Guardar en Base de Aprendizaje</button>
                    </div>
                `;
                const txtArea = corrBox.querySelector(".correction-input");
                const btnSave = corrBox.querySelector(".btn-save-corr");
                const btnClose = corrBox.querySelector(".btn-close-corr");

                btnClose.addEventListener("click", () => corrBox.remove());
                btnSave.addEventListener("click", async () => {
                    const correctionVal = txtArea.value.trim();
                    if (!correctionVal) return;
                    btnSave.disabled = true;
                    btnSave.textContent = "Guardando...";
                    try {
                        const res = await fetch("/api/feedback", {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({
                                query: queryText,
                                correction: correctionVal,
                                agent_output: text
                            })
                        });
                        corrBox.innerHTML = `<div class="correction-success">✅ ¡Corrección registrada en feedback/ para reentrenamiento!</div>`;
                        statusSpan.textContent = "Corrección guardada";
                        setTimeout(() => corrBox.remove(), 4000);
                    } catch(err) {
                        btnSave.disabled = false;
                        btnSave.textContent = "Error al guardar";
                    }
                });
                bubble.appendChild(corrBox);
                txtArea.focus();
            }

            bubble.appendChild(feedbackBar);
        }

        if (role === "user") {
            row.appendChild(bubble);
            row.appendChild(avatar);
        } else {
            row.appendChild(avatar);
            row.appendChild(bubble);
        }

        messagesStream.appendChild(row);
        scrollToBottom();
    }

    function appendLoadingBubble(statusText = "Pensando...") {
        const id = "loading-" + Date.now();
        const row = document.createElement("div");
        row.className = "msg-row ai";
        row.id = id;

        const avatar = document.createElement("div");
        avatar.className = "msg-avatar ai";
        avatar.textContent = currentMode === "debate" ? "⚔️" : "IA";

        const bubble = document.createElement("div");
        bubble.className = "msg-bubble";

        const textDiv = document.createElement("div");
        textDiv.style.fontSize = "0.85rem";
        textDiv.style.color = "var(--text-secondary)";
        textDiv.style.marginBottom = "8px";
        textDiv.textContent = statusText;

        const dots = document.createElement("div");
        dots.className = "typing-dots";
        dots.innerHTML = `<span></span><span></span><span></span>`;

        bubble.appendChild(textDiv);
        bubble.appendChild(dots);
        row.appendChild(avatar);
        row.appendChild(bubble);
        messagesStream.appendChild(row);
        scrollToBottom();
        return id;
    }

    function removeLoadingBubble(id) {
        const elem = document.getElementById(id);
        if (elem) elem.remove();
    }

    function scrollToBottom() {
        messagesStream.scrollTop = messagesStream.scrollHeight;
    }

    // -------------------------------------------------------------
    // REINICIAR CONVERSACIÓN
    // -------------------------------------------------------------
    async function resetChat() {
        if (!confirm("¿Deseas reiniciar la sesión actual de conversación?")) return;
        try {
            await fetch("/api/reset", { method: "POST" });
            messagesStream.innerHTML = "";
            if (welcomeHero) {
                welcomeHero.style.display = "flex";
                messagesStream.appendChild(welcomeHero);
            }
        } catch (e) {
            console.error("Error al reiniciar chat", e);
        }
    }

    btnResetChat.addEventListener("click", resetChat);
    btnNewChat.addEventListener("click", resetChat);

    // -------------------------------------------------------------
    // MODAL DE CLAVES API (GROQ & GEMINI)
    // -------------------------------------------------------------
    async function openKeysModal() {
        modalKeys.classList.remove("hidden");
        try {
            const res = await fetch("/api/debate/status");
            const data = await res.json();
            if (data.groq_masked) {
                groqKeyInput.placeholder = `Clave actual: ${data.groq_masked}`;
                groqStatusText.textContent = `🟢 Clave guardada (${data.groq_masked})`;
                groqStatusText.className = "field-hint configured";
            } else {
                groqStatusText.textContent = "⚪ No configurada";
                groqStatusText.className = "field-hint";
            }

            if (data.gemini_masked) {
                geminiKeyInput.placeholder = `Clave actual: ${data.gemini_masked}`;
                geminiStatusText.textContent = `🟢 Clave guardada (${data.gemini_masked})`;
                geminiStatusText.className = "field-hint configured";
            } else {
                geminiStatusText.textContent = "⚪ No configurada";
                geminiStatusText.className = "field-hint";
            }
        } catch (e) {
            console.error("Error al cargar estado de claves", e);
        }
    }

    const closeKeysModal = () => {
        modalKeys.classList.add("hidden");
        groqKeyInput.value = "";
        geminiKeyInput.value = "";
    };

    btnOpenKeys.addEventListener("click", openKeysModal);
    btnCloseKeysModal.addEventListener("click", closeKeysModal);
    btnCancelKeys.addEventListener("click", closeKeysModal);

    // Botones de mostrar/ocultar contraseñas
    document.querySelectorAll(".btn-toggle-eye").forEach(btn => {
        btn.addEventListener("click", () => {
            const targetId = btn.getAttribute("data-target");
            const input = document.getElementById(targetId);
            if (input) {
                input.type = input.type === "password" ? "text" : "password";
            }
        });
    });

    btnSaveKeys.addEventListener("click", async () => {
        const groqVal = groqKeyInput.value.trim();
        const geminiVal = geminiKeyInput.value.trim();

        btnSaveKeys.disabled = true;
        btnSaveKeys.textContent = "Guardando...";

        try {
            const payload = {};
            if (groqVal) payload.groq_key = groqVal;
            if (geminiVal) payload.gemini_key = geminiVal;

            const res = await fetch("/api/debate/keys", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });
            const data = await res.json();

            if (data.success) {
                closeKeysModal();
                updateTelemetry();
                appendMessage("ai", `⚔️ **Cerebro Dual Configurado con Éxito.**\n\nGroq y Gemini debatirán automáticamente para cada consulta en modo **Debate Dual**, generando respuestas con auditoría cruzada y alimentando el dataset de destilación local.`);
            } else {
                alert("Error al guardar claves: " + (data.error || "Desconocido"));
            }
        } catch (e) {
            alert("Error al conectar con el servidor: " + e.message);
        } finally {
            btnSaveKeys.disabled = false;
            btnSaveKeys.textContent = "Guardar y Activar Debate";
        }
    });

    // -------------------------------------------------------------
    // MODAL RAG (INDEXAR MEMORIA)
    // -------------------------------------------------------------
    btnAddDoc.addEventListener("click", () => {
        modalRag.classList.remove("hidden");
        ragTitle.focus();
    });

    const closeModalRag = () => {
        modalRag.classList.add("hidden");
        ragTitle.value = "";
        ragContent.value = "";
    };

    btnCloseModal.addEventListener("click", closeModalRag);
    btnCancelRag.addEventListener("click", closeModalRag);

    btnSaveRag.addEventListener("click", async () => {
        const title = ragTitle.value.trim();
        const content = ragContent.value.trim();
        if (!content) {
            alert("Ingresa contenido para indexar.");
            return;
        }

        try {
            const res = await fetch("/api/memory/add", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    source: "manual_" + Date.now(),
                    title: title || "Nota personal",
                    content: content
                })
            });
            const data = await res.json();
            if (data.success) {
                closeModalRag();
                appendMessage("ai", `✅ **Documento indexado con éxito.** "${title || 'Nota'}" ya forma parte de mi memoria local permanente.`);
            }
        } catch (e) {
            alert("Error al guardar en memoria: " + e.message);
        }
    });

    // -------------------------------------------------------------
    // FORMATEADOR MARKDOWN NATIVO LIGERO
    // -------------------------------------------------------------
    function formatMarkdown(text) {
        if (!text) return "";
        let html = escapeHtml(text);

        // Bloques de código ```lenguaje ... ```
        html = html.replace(/```([a-zA-Z0-9_-]*)\n([\s\S]*?)```/g, (match, lang, code) => {
            return `<pre><code class="language-${lang}">${code}</code></pre>`;
        });

        // Encabezados ### Título
        html = html.replace(/^### (.*$)/gim, '<h4 style="margin: 8px 0 4px; color: var(--accent-cyan); font-weight:700;">$1</h4>');
        html = html.replace(/^## (.*$)/gim, '<h3 style="margin: 10px 0 6px; color: #fff; font-weight:700;">$1</h3>');
        html = html.replace(/^# (.*$)/gim, '<h2 style="margin: 12px 0 8px; color: #fff; font-weight:800;">$1</h2>');

        // Código inline `código`
        html = html.replace(/`([^`]+)`/g, '<code>$1</code>');

        // Negrita **texto**
        html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');

        // Cursiva *texto*
        html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>');

        // Listas con viñetas
        html = html.replace(/^\s*-\s+(.*)$/gm, '<li>$1</li>');
        html = html.replace(/(<li>.*<\/li>)/s, '<ul style="margin: 6px 0 6px 18px;">$1</ul>');

        // Saltos de línea a <br>
        html = html.replace(/\n/g, '<br>');

        return html;
    }

    function escapeHtml(str) {
        return str
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }
});
