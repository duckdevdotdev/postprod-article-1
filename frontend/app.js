import {
  CallEvent,
  Communicator,
  RegistrationEvent,
} from "@exolve/web-voice-sdk";

const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000";
const TOUR_ID = "tour_101";

let sessionId = null;
let communicator = null;
let callClient = null;
let sdkInitialized = false;
let isRegistered = false;
let callRequested = false;
let currentCallConfig = null;

const chatBox = document.getElementById("chat");
const callBtn = document.getElementById("call-btn");
const statusDiv = document.getElementById("call-status");
const inputArea = document.getElementById("input-area");
const userInput = document.getElementById("user-msg");
const sendBtn = document.getElementById("send-btn");

function appendMessage(sender, text, className) {
  const message = document.createElement("div");
  message.className = `msg ${className}`;

  const name = document.createElement("strong");
  name.textContent = `${sender}: `;

  const body = document.createElement("span");
  body.textContent = text;

  message.append(name, body);
  chatBox.appendChild(message);
  chatBox.scrollTop = chatBox.scrollHeight;
}

function setChatBusy(isBusy) {
  userInput.disabled = isBusy;
  sendBtn.disabled = isBusy;
}

function resetCallUi(showCallButton = false) {
  inputArea.style.display = "flex";
  callBtn.style.display = showCallButton ? "block" : "none";
}

async function apiRequest(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, options);
  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const body = await response.json();
      detail = body.detail || detail;
    } catch {
      // Ответ не обязан быть JSON.
    }
    throw new Error(detail);
  }
  return response.json();
}

async function initChat() {
  setChatBusy(true);
  try {
    const data = await apiRequest("/api/chat/init", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tour_id: TOUR_ID }),
    });
    sessionId = data.session_id;
    appendMessage("Бот", data.reply, "bot");
  } catch (error) {
    console.error(error);
    appendMessage("Система", "Ошибка загрузки чата.", "bot");
  } finally {
    setChatBusy(false);
    userInput.focus();
  }
}

async function sendMessage() {
  const text = userInput.value.trim();
  if (!text || !sessionId || sendBtn.disabled) return;

  appendMessage("Вы", text, "user");
  userInput.value = "";
  setChatBusy(true);

  try {
    const data = await apiRequest("/api/chat/message", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, message: text }),
    });
    appendMessage("Бот", data.reply, "bot");
    callBtn.style.display = data.show_call_button ? "block" : "none";
  } catch (error) {
    console.error(error);
    appendMessage("Система", "Ошибка отправки сообщения.", "bot");
  } finally {
    setChatBusy(false);
    userInput.focus();
  }
}

async function updateCallStatus(status) {
  if (!sessionId) return;
  try {
    await apiRequest("/api/chat/call_status", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, status }),
    });
  } catch (error) {
    console.error("Сбой обновления статуса звонка", error);
  }
}

async function initSdk() {
  communicator = new Communicator();
  await communicator.initialize({
    debug: true,
    enableSecureConnection: true,
    maxLines: 1,
    ringtoneEnabled: true,
  });
  callClient = communicator.client;

  callClient.on(RegistrationEvent.Registered, () => {
    isRegistered = true;
    if (!callRequested || !currentCallConfig) return;
    callRequested = false;
    statusDiv.textContent = "Установка соединения...";
    callClient.makeCall(currentCallConfig.MANAGER_NUMBER);
  });

  callClient.on(RegistrationEvent.NotRegistered, () => {
    isRegistered = false;
    callRequested = false;
    statusDiv.textContent = "SIP-аккаунт деавторизован сервером.";
    void updateCallStatus("failed");
    resetCallUi(true);
  });

  callClient.on(RegistrationEvent.Error, () => {
    isRegistered = false;
    callRequested = false;
    statusDiv.textContent = "Ошибка регистрации на SIP-сервере.";
    void updateCallStatus("failed");
    resetCallUi(true);
  });

  callClient.on(CallEvent.New, () => void updateCallStatus("started"));
  callClient.on(CallEvent.Connected, () => {
    statusDiv.textContent = "Разговор с менеджером установлен.";
    void updateCallStatus("connected");
  });
  callClient.on(CallEvent.Disconnected, () => {
    statusDiv.textContent = "Звонок завершён.";
    void updateCallStatus("ended");
    resetCallUi(false);
  });
  callClient.on(CallEvent.Error, () => {
    statusDiv.textContent = "Ошибка вызова.";
    void updateCallStatus("failed");
    resetCallUi(true);
  });

  sdkInitialized = true;
}

async function startCall() {
  callBtn.style.display = "none";
  inputArea.style.display = "none";
  await updateCallStatus("clicked");
  statusDiv.textContent = "Инициализация телефонии...";

  try {
    currentCallConfig = await apiRequest("/api/demo-web-call-config");
    if (!sdkInitialized) await initSdk();

    if (isRegistered) {
      callRequested = false;
      statusDiv.textContent = "Установка соединения...";
      callClient.makeCall(currentCallConfig.MANAGER_NUMBER);
    } else {
      callRequested = true;
      callClient.registerAccount(
        currentCallConfig.LOGIN,
        currentCallConfig.PASSWORD,
      );
    }
  } catch (error) {
    console.error("Сбой Web Voice SDK", error);
    statusDiv.textContent = `Техническая ошибка вызова: ${error.message}`;
    await updateCallStatus("failed");
    resetCallUi(true);
  }
}

window.addEventListener("beforeunload", () => {
  if (callClient) callClient.unregisterAccount();
});

sendBtn.addEventListener("click", sendMessage);
userInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") void sendMessage();
});
callBtn.addEventListener("click", startCall);
window.addEventListener("DOMContentLoaded", initChat);

