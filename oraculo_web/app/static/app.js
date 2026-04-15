const state = {
  currentUser: null,
  threadId: window.localStorage.getItem("oraculo_web.thread_id") || "",
  messages: [],
  statusTimer: null,
};

const SAMPLE_MESSAGES = {
  hello: "Hola",
  skills: "Que sabes hacer?",
  prediction: "Quiero una prediccion de ingresos en un solo prompt. Tengo 39 anos, mi tipo de trabajo es Private, mi fnlwgt es 77516, estudie Bachelors, mi education.num es 13, mi estado civil es Never-married, trabajo como Adm-clerical, mi relacion es Not-in-family, mi raza es White, soy hombre, mi capital.gain es 2174, mi capital.loss es 0, trabajo 40 horas por semana y naci en United-States.",
  rag: "Explicame que hace el proyecto, que endpoint usa el agente para conversar y como protege sus endpoints.",
};

const ROUTE_EXPLANATIONS = {
  chat: "AdultBot respondio en modo conversacional usando su cerebro LLM.",
  prediction: "El agente detecto un caso de prediccion y esta reuniendo datos o consultando tu modelo.",
  rag: "El agente respondio usando su base documental con respaldo de citas.",
  hybrid: "El agente combino prediccion del modelo con contexto documental del RAG.",
  clarification: "El agente necesita mas contexto antes de ejecutar la siguiente accion.",
  unsafe: "El agente bloqueo la solicitud por una politica de seguridad.",
};

const authButtons = document.querySelectorAll("[data-auth-view]");
const loginForm = document.getElementById("login-form");
const registerForm = document.getElementById("register-form");
const sessionBox = document.getElementById("session-box");
const logoutButton = document.getElementById("logout-button");
const chatForm = document.getElementById("chat-form");
const messageInput = document.getElementById("message-input");
const messageStream = document.getElementById("message-stream");
const routeHelper = document.getElementById("route-helper");
const composerNote = document.getElementById("composer-note");
const resetThreadButton = document.getElementById("reset-thread-button");
const quickActionButtons = document.querySelectorAll("[data-sample]");
const knowledgeUploadForm = document.getElementById("knowledge-upload-form");
const knowledgeFileInput = document.getElementById("knowledge-file-input");
const knowledgeSources = document.getElementById("knowledge-sources");

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function showStatus(message, tone = "neutral") {
  let toast = document.querySelector(".status-toast");
  if (!toast) {
    toast = document.createElement("div");
    toast.className = "status-toast";
    document.body.appendChild(toast);
  }

  toast.textContent = message;
  toast.style.background =
    tone === "error" ? "rgba(190, 24, 93, 0.95)"
      : tone === "success" ? "rgba(15, 118, 110, 0.94)"
        : "rgba(15, 23, 42, 0.94)";
  toast.classList.add("is-visible");

  window.clearTimeout(state.statusTimer);
  state.statusTimer = window.setTimeout(() => {
    toast.classList.remove("is-visible");
  }, 3200);
}

async function apiRequest(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  const isFormData = typeof FormData !== "undefined" && options.body instanceof FormData;

  if (!isFormData && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }

  const response = await fetch(path, {
    credentials: "include",
    ...options,
    headers,
  });

  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = payload.error || {};
    throw new Error(error.message || "La operacion no se pudo completar.");
  }

  return payload;
}

function setAuthView(view) {
  authButtons.forEach((button) => {
    button.classList.toggle("is-active", button.dataset.authView === view);
  });
  loginForm.classList.toggle("hidden", view !== "login");
  registerForm.classList.toggle("hidden", view !== "register");
}

function renderSession() {
  if (!state.currentUser) {
    sessionBox.innerHTML = '<p class="session-empty">Todavia no hay una sesion activa.</p>';
    logoutButton.classList.add("hidden");
    renderKnowledgeSources([]);
    return;
  }

  sessionBox.innerHTML = `
    <div class="session-pill">Sesion activa</div>
    <div class="session-meta">
      <strong>${escapeHtml(state.currentUser.full_name)}</strong>
      <span>${escapeHtml(state.currentUser.email)}</span>
      <span>Rol remoto: ${escapeHtml(state.currentUser.role)}</span>
    </div>
  `;
  logoutButton.classList.remove("hidden");
}

function renderKnowledgeSources(items) {
  if (!state.currentUser) {
    knowledgeSources.innerHTML = '<p class="session-empty">Inicia sesion para ver y cargar fuentes del RAG.</p>';
    return;
  }

  if (!items?.length) {
    knowledgeSources.innerHTML = '<p class="session-empty">Todavia no hay documentos cargados manualmente.</p>';
    return;
  }

  knowledgeSources.innerHTML = items.map((item) => `
    <article class="source-card">
      <strong>${escapeHtml(item.title || item.source_path || "Documento")}</strong>
      <small>${escapeHtml(item.source_path || "")}</small>
      <span>${escapeHtml(String(item.source_type || "").toUpperCase())} - ${escapeHtml(String(item.chunk_count ?? item.total_chunks ?? 0))} chunks</span>
    </article>
  `).join("");
}

async function loadKnowledgeSources() {
  if (!state.currentUser) {
    renderKnowledgeSources([]);
    return;
  }

  try {
    const payload = await apiRequest("/api/knowledge/sources", { method: "GET" });
    renderKnowledgeSources(payload.items || []);
  } catch (error) {
    renderKnowledgeSources([]);
    showStatus(error.message, "error");
  }
}

function routeBadge(route) {
  return route ? `<span class="route-badge route-${escapeHtml(route)}">${escapeHtml(route)}</span>` : "";
}

function renderPredictionCard(prediction) {
  if (!prediction) {
    return "";
  }

  return `
    <div class="prediction-card">
      <strong>Resultado del modelo:</strong> ${escapeHtml(prediction.label)}<br>
      <strong>Probabilidad:</strong> ${(prediction.probability * 100).toFixed(2)}%<br>
      <strong>Version:</strong> ${escapeHtml(prediction.model_version)}
    </div>
  `;
}

function renderCitations(citations) {
  if (!citations?.length) {
    return "";
  }

  return citations.map((citation) => `
    <div class="citation-card">
      <strong>${escapeHtml(citation.title || citation.source_id)}</strong><br>
      <small>${escapeHtml(citation.source_path || "")}</small>
      <p>${escapeHtml(citation.snippet || "")}</p>
    </div>
  `).join("");
}

function renderSafetyFlags(flags) {
  if (!flags?.length) {
    return "";
  }

  return flags.map((flag) => `
    <div class="flag-card">${escapeHtml(flag.message || flag.code || "Flag de seguridad")}</div>
  `).join("");
}

function renderMessages() {
  if (!state.messages.length) {
    messageStream.innerHTML = `
      <article class="empty-state">
        <p class="empty-badge">Inicio</p>
        <h3>Habla como lo harias con un LLM</h3>
        <p>
          Puedes escribir <strong>Hola</strong>, enviar un perfil completo para prediccion en un solo prompt o hacer preguntas documentales.
          AdultBot decidira internamente la mejor ruta.
        </p>
      </article>
    `;
    return;
  }

  messageStream.innerHTML = state.messages.map((message) => `
    <article class="message-card ${message.role}">
      <div class="message-head">
        <span class="message-role">${message.role === "user" ? "Tu" : "AdultBot"}</span>
        ${routeBadge(message.route)}
      </div>
      <div class="message-body">${escapeHtml(message.content)}</div>
      <div class="message-meta">
        ${renderPredictionCard(message.prediction)}
        ${renderCitations(message.citations)}
        ${renderSafetyFlags(message.safetyFlags)}
      </div>
    </article>
  `).join("");

  messageStream.scrollTop = messageStream.scrollHeight;
}

async function loadSession() {
  try {
    const payload = await apiRequest("/api/auth/me", { method: "GET" });
    state.currentUser = payload.user;
  } catch (_error) {
    state.currentUser = null;
  }

  renderSession();
  await loadKnowledgeSources();
}

async function handleLogin(event) {
  event.preventDefault();
  const formData = new FormData(loginForm);
  const payload = Object.fromEntries(formData.entries());

  try {
    const response = await apiRequest("/api/auth/login", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    state.currentUser = response.user;
    renderSession();
    await loadKnowledgeSources();
    showStatus("Sesion iniciada. Ya puedes conversar con AdultBot.", "success");
  } catch (error) {
    showStatus(error.message, "error");
  }
}

async function handleRegister(event) {
  event.preventDefault();
  const formData = new FormData(registerForm);
  const payload = Object.fromEntries(formData.entries());

  try {
    const response = await apiRequest("/api/auth/register", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    state.currentUser = response.user;
    renderSession();
    await loadKnowledgeSources();
    showStatus("Cuenta creada y sesion iniciada.", "success");
  } catch (error) {
    showStatus(error.message, "error");
  }
}

async function handleLogout() {
  try {
    await apiRequest("/api/auth/logout", {
      method: "POST",
      body: JSON.stringify({}),
    });
  } catch (_error) {
    // Local cleanup still makes sense even if the upstream logout fails.
  }

  state.currentUser = null;
  state.messages = [];
  state.threadId = "";
  window.localStorage.removeItem("oraculo_web.thread_id");
  routeHelper.textContent = "AdultBot decidira automaticamente si debe conversar, pedir una prediccion o consultar conocimiento.";
  composerNote.textContent = "El agente responde con lenguaje natural y decide la mejor ruta internamente.";
  renderSession();
  renderKnowledgeSources([]);
  renderMessages();
  showStatus("Sesion cerrada.", "success");
}

function setPendingAssistantMessage(message) {
  state.messages.push({
    role: "assistant",
    content: message,
    route: null,
    citations: [],
    prediction: null,
    safetyFlags: [],
  });
  renderMessages();
}

async function handleSendMessage(event) {
  event.preventDefault();
  const message = messageInput.value.trim();

  if (!message) {
    showStatus("Escribe un mensaje antes de enviar.", "error");
    return;
  }

  if (!state.currentUser) {
    showStatus("Primero inicia sesion o crea una cuenta.", "error");
    return;
  }

  state.messages.push({ role: "user", content: message });
  renderMessages();
  setPendingAssistantMessage("AdultBot esta pensando...");
  messageInput.value = "";

  try {
    const payload = await apiRequest("/api/chat/invoke", {
      method: "POST",
      body: JSON.stringify({
        thread_id: state.threadId || null,
        message,
        language: "es",
        metadata: { source: "oraculo_web" },
      }),
    });

    state.threadId = payload.thread_id;
    window.localStorage.setItem("oraculo_web.thread_id", state.threadId);
    routeHelper.textContent = ROUTE_EXPLANATIONS[payload.route] || "AdultBot proceso la solicitud.";
    composerNote.textContent = payload.missing_fields?.length
      ? payload.missing_fields.length === 1
        ? `Dato faltante: ${payload.missing_fields[0]}.`
        : `Completa estos datos en un solo mensaje: ${payload.missing_fields.join(", ")}.`
      : "Puedes seguir la conversacion, cambiar de tema o pedir una nueva tarea.";
    state.messages[state.messages.length - 1] = {
      role: "assistant",
      content: payload.answer,
      route: payload.route,
      citations: payload.citations || [],
      prediction: payload.prediction_result || null,
      safetyFlags: payload.safety_flags || [],
    };
    renderMessages();
  } catch (error) {
    state.messages[state.messages.length - 1] = {
      role: "assistant",
      content: error.message,
      route: "clarification",
      citations: [],
      prediction: null,
      safetyFlags: [{ code: "frontend_error", message: error.message }],
    };
    renderMessages();
    showStatus(error.message, "error");
  }
}

async function handleKnowledgeUpload(event) {
  event.preventDefault();

  if (!state.currentUser) {
    showStatus("Primero inicia sesion para cargar documentos al RAG.", "error");
    return;
  }

  const file = knowledgeFileInput.files?.[0];
  if (!file) {
    showStatus("Selecciona un documento antes de cargarlo.", "error");
    return;
  }

  const formData = new FormData();
  formData.append("file", file);

  try {
    const payload = await apiRequest("/api/knowledge/upload", {
      method: "POST",
      body: formData,
    });
    knowledgeUploadForm.reset();
    await loadKnowledgeSources();
    showStatus(`Documento cargado: ${payload.file_name}`, "success");
  } catch (error) {
    showStatus(error.message || "No se pudo cargar el documento al RAG.", "error");
  }
}

function loadSampleMessage(kind) {
  const message = SAMPLE_MESSAGES[kind];
  if (!message) {
    return;
  }

  messageInput.value = message;
  messageInput.focus();
}

function resetThread() {
  state.threadId = "";
  state.messages = [];
  window.localStorage.removeItem("oraculo_web.thread_id");
  routeHelper.textContent = "AdultBot decidira automaticamente si debe conversar, pedir una prediccion o consultar conocimiento.";
  composerNote.textContent = "El agente responde con lenguaje natural y decide la mejor ruta internamente.";
  renderMessages();
  showStatus("Hilo reiniciado.", "success");
}

authButtons.forEach((button) => {
  button.addEventListener("click", () => setAuthView(button.dataset.authView));
});

quickActionButtons.forEach((button) => {
  button.addEventListener("click", () => loadSampleMessage(button.dataset.sample));
});

loginForm.addEventListener("submit", handleLogin);
registerForm.addEventListener("submit", handleRegister);
logoutButton.addEventListener("click", handleLogout);
chatForm.addEventListener("submit", handleSendMessage);
resetThreadButton.addEventListener("click", resetThread);
knowledgeUploadForm.addEventListener("submit", handleKnowledgeUpload);

setAuthView("login");
renderMessages();
loadSession();
