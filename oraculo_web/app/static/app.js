const state = {
  currentUser: null,
  threadId: window.localStorage.getItem("oraculo_web.thread_id") || "",
  messages: [],
  statusTimer: null,
};

const SAMPLE_PREDICTION_MESSAGE = "Quiero una prediccion de ingresos. Soy hombre, tengo 39 anos, mi workclass es Private, mi fnlwgt es 77516, estudie Bachelors, mi education.num es 13, mi estado civil es Never-married, trabajo como Adm-clerical, mi relacion es Not-in-family, mi raza es White, tuve una ganancia de capital de 2174, una perdida de capital de 0, trabajo 40 horas por semana y naci en United-States.";
const SAMPLE_RAG_MESSAGE = "Explicame que hace el proyecto, como protege los endpoints y que ruta usa el agente para conversar sin streaming.";

const ROUTE_EXPLANATIONS = {
  prediction: "El agente detecto un caso de prediccion y consulto tu API del modelo.",
  rag: "El agente contesto con su base de conocimiento RAG y devolvio citas.",
  hybrid: "El agente combino prediccion del modelo con contexto documental del RAG.",
  clarification: "El agente necesita mas datos antes de llamar a la API de prediccion.",
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
const samplePredictionButton = document.getElementById("sample-prediction-button");
const sampleRagButton = document.getElementById("sample-rag-button");
const resetThreadButton = document.getElementById("reset-thread-button");

function escapeHtml(value) {
  return value
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
    tone === "error" ? "rgba(159, 18, 57, 0.92)" :
    tone === "success" ? "rgba(15, 118, 110, 0.92)" :
    "rgba(29, 19, 13, 0.9)";
  toast.classList.add("is-visible");
  window.clearTimeout(state.statusTimer);
  state.statusTimer = window.setTimeout(() => toast.classList.remove("is-visible"), 3200);
}

async function apiRequest(path, options = {}) {
  const response = await fetch(path, {
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
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

function renderMessages() {
  if (!state.messages.length) {
    messageStream.innerHTML = `
      <article class="empty-state">
        <h3>Listo para hablar natural</h3>
        <p>
          Puedes pedir una prediccion con una descripcion natural del perfil Adult Income, o preguntar por la
          arquitectura, endpoints, seguridad y funcionamiento del proyecto para activar el RAG.
        </p>
      </article>
    `;
    return;
  }

  messageStream.innerHTML = state.messages.map((message) => {
    const routeBadge = message.route
      ? `<span class="badge badge-${escapeHtml(message.route)}">${escapeHtml(message.route)}</span>`
      : "";
    const predictionCard = message.prediction
      ? `
        <div class="prediction-card">
          Segun el modelo ${escapeHtml(message.prediction.model_version)}, este perfil se acerca mas a la clase
          <strong>${escapeHtml(message.prediction.label)}</strong> con una probabilidad aproximada de
          <strong>${(message.prediction.probability * 100).toFixed(2)}%</strong>.
        </div>
      `
      : "";
    const citations = message.citations?.length
      ? message.citations.map((citation) => `
          <div class="citation-card">
            <strong>${escapeHtml(citation.title || citation.source_id)}</strong><br>
            <small>${escapeHtml(citation.source_path || "")}</small>
            <p>${escapeHtml(citation.snippet || "")}</p>
          </div>
        `).join("")
      : "";
    const flags = message.safetyFlags?.length
      ? message.safetyFlags.map((flag) => `
          <div class="flag-card">${escapeHtml(flag.message || flag.code || "Flag de seguridad")}</div>
        `).join("")
      : "";

    return `
      <article class="message-card ${message.role}">
        <div class="message-head">
          <span class="message-role">${message.role === "user" ? "Tu" : "Oraculo Agente IA"}</span>
          ${routeBadge}
        </div>
        <div class="message-body">${escapeHtml(message.content)}</div>
        <div class="message-meta">
          ${predictionCard}
          ${citations}
          ${flags}
        </div>
      </article>
    `;
  }).join("");

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
    showStatus("Sesion iniciada. Ya puedes hablar con el agente.", "success");
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
    showStatus("Cuenta creada y sesion iniciada.", "success");
  } catch (error) {
    showStatus(error.message, "error");
  }
}

async function handleLogout() {
  try {
    await apiRequest("/api/auth/logout", { method: "POST", body: JSON.stringify({}) });
  } catch (_error) {
    // Clearing local state is still safe.
  }
  state.currentUser = null;
  state.messages = [];
  state.threadId = "";
  window.localStorage.removeItem("oraculo_web.thread_id");
  renderSession();
  renderMessages();
  showStatus("Sesion cerrada.", "success");
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
  state.messages.push({ role: "assistant", content: "Pensando...", route: null, citations: [], safetyFlags: [] });
  renderMessages();
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
    routeHelper.textContent = ROUTE_EXPLANATIONS[payload.route] || "El agente proceso la solicitud.";
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
      safetyFlags: [{ code: "frontend_error", message: error.message }],
    };
    renderMessages();
    showStatus(error.message, "error");
  }
}

function loadSampleMessage(message) {
  messageInput.value = message;
  messageInput.focus();
}

function resetThread() {
  state.threadId = "";
  state.messages = [];
  window.localStorage.removeItem("oraculo_web.thread_id");
  routeHelper.textContent = "El agente decide automaticamente si debe ir a prediction, rag o hybrid.";
  renderMessages();
  showStatus("Conversacion reiniciada.", "success");
}

authButtons.forEach((button) => {
  button.addEventListener("click", () => setAuthView(button.dataset.authView));
});

loginForm.addEventListener("submit", handleLogin);
registerForm.addEventListener("submit", handleRegister);
logoutButton.addEventListener("click", handleLogout);
chatForm.addEventListener("submit", handleSendMessage);
samplePredictionButton.addEventListener("click", () => loadSampleMessage(SAMPLE_PREDICTION_MESSAGE));
sampleRagButton.addEventListener("click", () => loadSampleMessage(SAMPLE_RAG_MESSAGE));
resetThreadButton.addEventListener("click", resetThread);

setAuthView("login");
renderMessages();
loadSession();
