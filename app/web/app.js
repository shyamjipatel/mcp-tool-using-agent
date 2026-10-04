const $ = (selector) => document.querySelector(selector);
const state = { sessions: [], currentId: null, messages: [], busy: false, search: "", menuId: null, actionId: null };
const shell = $("#app-shell");
const thread = $("#thread");
const welcome = $("#welcome");
const contentArea = $("#content-area");
const input = $("#message-input");
const sendButton = $("#send-button");
let toastTimer;

function icon(name) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
  use.setAttribute("href", `#i-${name}`);
  svg.append(use);
  return svg;
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  const payload = response.status === 204 ? null : await response.json();
  if (!response.ok) {
    const detail = payload?.detail;
    throw new Error(typeof detail === "string" ? detail : detail?.error || `Request failed (${response.status}).`);
  }
  return payload;
}

function toast(message) {
  const node = $("#toast");
  node.textContent = message;
  node.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => node.classList.remove("show"), 4200);
}

function closeSidebar() { shell.classList.remove("sidebar-open"); }
function updateComposer() {
  sendButton.disabled = state.busy || !input.value.trim();
  input.disabled = state.busy;
  input.style.height = "auto";
  input.style.height = `${Math.min(input.scrollHeight, 170)}px`;
}

function renderSessions() {
  const list = $("#session-list");
  list.replaceChildren();
  $("#session-count").textContent = String(state.sessions.length);
  const filtered = state.sessions.filter((session) => session.title.toLowerCase().includes(state.search));
  if (!filtered.length) {
    list.append(el("p", "sidebar-empty", state.search ? "No conversations match your search." : "Your conversations will appear here."));
    return;
  }
  for (const session of filtered) {
    const row = el("div", `session-row${session.id === state.currentId ? " active" : ""}`);
    const select = el("button", "session-select");
    select.type = "button";
    select.title = session.title;
    select.setAttribute("aria-label", `Open ${session.title}`);
    if (session.id === state.currentId) select.setAttribute("aria-current", "page");
    select.append(icon("chat"), el("span", "", session.title));
    select.addEventListener("click", () => openSession(session.id));

    const actions = el("div", "session-actions");
    const more = el("button", "session-menu-button");
    more.type = "button";
    more.setAttribute("aria-label", `Options for ${session.title}`);
    more.setAttribute("aria-expanded", String(state.menuId === session.id));
    more.append(icon("more"));
    more.addEventListener("click", (event) => {
      event.stopPropagation();
      state.menuId = state.menuId === session.id ? null : session.id;
      renderSessions();
    });
    actions.append(more);
    if (state.menuId === session.id) {
      const menu = el("div", "session-menu");
      const rename = el("button", "", "Rename");
      rename.type = "button";
      rename.addEventListener("click", () => openRename(session));
      const remove = el("button", "delete-action", "Delete");
      remove.type = "button";
      remove.addEventListener("click", () => openDelete(session));
      menu.append(rename, remove);
      actions.append(menu);
    }
    row.append(select, actions);
    list.append(row);
  }
}

function renderTrace(calls) {
  const details = el("details", "trace");
  const summary = el("summary");
  summary.append(icon("spark"), el("span", "", `${calls.length} tool ${calls.length === 1 ? "call" : "calls"} · View steps`));
  details.append(summary);
  const items = el("div", "trace-items");
  for (const call of calls) {
    const item = el("div", "trace-item");
    const meta = el("div", "trace-meta");
    meta.append(el("strong", "", call.name));
    if (call.is_error) meta.append(el("span", "error", "Failed"));
    const duration = el("time", "", `${Math.round(call.duration_ms || 0)} ms`);
    meta.append(duration);
    const content = el("pre", "", JSON.stringify({ arguments: call.arguments, result: call.result, error: call.error }, null, 2));
    item.append(meta, content);
    items.append(item);
  }
  details.append(items);
  return details;
}

function renderMessages() {
  thread.replaceChildren();
  const hasMessages = state.messages.length > 0;
  welcome.hidden = hasMessages;
  thread.hidden = !hasMessages;
  $("#conversation-title").textContent = state.sessions.find((session) => session.id === state.currentId)?.title || "New conversation";
  for (const message of state.messages) {
    const wrapper = el("article", `message ${message.role}`);
    const body = el("div", "message-body");
    if (message.role === "assistant") {
      wrapper.append(el("span", "assistant-avatar", "R"));
      body.append(el("div", "message-label", "Relay"));
    }
    body.append(el("div", "message-content", message.content));
    if (message.role === "assistant") {
      if (message.tool_calls?.length) body.append(renderTrace(message.tool_calls));
      const actions = el("div", "message-actions");
      const copy = el("button", "copy-button", "Copy response");
      copy.type = "button";
      copy.prepend(icon("copy"));
      copy.addEventListener("click", async () => {
        try { await navigator.clipboard.writeText(message.content); toast("Response copied."); }
        catch { toast("Copy is unavailable in this browser."); }
      });
      actions.append(copy);
      body.append(actions);
    }
    wrapper.append(body);
    thread.append(wrapper);
  }
  $("#thinking").hidden = !state.busy;
  requestAnimationFrame(() => { contentArea.scrollTop = contentArea.scrollHeight; });
}

async function loadSessions() {
  state.sessions = await api("/api/sessions");
  renderSessions();
  $("#conversation-title").textContent = state.sessions.find((session) => session.id === state.currentId)?.title || "New conversation";
}

async function openSession(id) {
  if (state.busy) return;
  try {
    const data = await api(`/api/sessions/${encodeURIComponent(id)}`);
    state.currentId = id;
    state.messages = data.messages;
    state.menuId = null;
    localStorage.setItem("relay:last-session", id);
    renderSessions();
    renderMessages();
    closeSidebar();
  } catch (error) { toast(error.message); }
}

async function newSession() {
  if (state.busy) return;
  try {
    const session = await api("/api/sessions", { method: "POST", body: JSON.stringify({}) });
    state.currentId = session.id;
    state.messages = [];
    state.menuId = null;
    localStorage.setItem("relay:last-session", session.id);
    await loadSessions();
    renderMessages();
    closeSidebar();
    input.focus();
  } catch (error) { toast(error.message); }
}

async function sendMessage(text) {
  if (state.busy || !text.trim()) return;
  const question = text.trim();
  if (!state.currentId) await newSession();
  if (!state.currentId) return;
  input.value = "";
  state.busy = true;
  updateComposer();
  state.messages.push({ id: `pending-${Date.now()}`, role: "user", content: question, tool_calls: [] });
  renderMessages();
  try {
    const turn = await api(`/api/sessions/${encodeURIComponent(state.currentId)}/messages`, {
      method: "POST", body: JSON.stringify({ question }),
    });
    state.messages.splice(-1, 1, turn.user_message, turn.assistant_message);
    await loadSessions();
  } catch (error) {
    toast(error.message);
    try { state.messages = (await api(`/api/sessions/${encodeURIComponent(state.currentId)}`)).messages; }
    catch { state.messages.pop(); }
  } finally {
    state.busy = false;
    updateComposer();
    renderMessages();
    input.focus();
  }
}

function openRename(session) {
  state.actionId = session.id;
  state.menuId = null;
  renderSessions();
  $("#rename-input").value = session.title;
  $("#rename-dialog").showModal();
  $("#rename-input").focus();
}

function openDelete(session) {
  state.actionId = session.id;
  state.menuId = null;
  renderSessions();
  $("#delete-dialog").showModal();
}

function setTheme(theme) {
  document.documentElement.dataset.theme = theme;
  localStorage.setItem("relay:theme", theme);
  $("#theme-toggle use").setAttribute("href", theme === "dark" ? "#i-sun" : "#i-moon");
  $("#theme-toggle").setAttribute("aria-label", theme === "dark" ? "Use light theme" : "Use dark theme");
}

async function loadStatus() {
  try {
    const status = await api("/api/status");
    $("#provider-name").textContent = status.provider === "huggingface" ? "Hugging Face" : status.provider === "openai" ? "OpenAI" : status.provider === "local" ? "Local model" : "Offline demo";
    $("#provider-detail").textContent = status.provider === "demo" ? "Deterministic tool demo" : status.configured ? "Ready for conversations" : "Set token or use demo mode";
    $("#provider-dot").classList.toggle("online", status.configured);
    $("#model-badge").textContent = status.model === "provider default" ? "MCP Agent" : status.model.split("/").pop().split(":")[0];
  } catch { $("#provider-detail").textContent = "Provider status unavailable"; }
  try {
    const tools = await api("/tools");
    $("#tool-count").textContent = `${tools.length} tools connected`;
    $(".tool-status-dot").classList.add("online");
  } catch { $("#tool-count").textContent = "Tools unavailable"; }
}

$("#new-chat").addEventListener("click", newSession);
$("#open-sidebar").addEventListener("click", () => shell.classList.add("sidebar-open"));
$("#close-sidebar").addEventListener("click", closeSidebar);
$("#sidebar-scrim").addEventListener("click", closeSidebar);
$("#session-search").addEventListener("input", (event) => { state.search = event.target.value.trim().toLowerCase(); renderSessions(); });
$("#theme-toggle").addEventListener("click", () => setTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark"));
$("#suggestions").addEventListener("click", (event) => {
  const suggestion = event.target.closest("[data-prompt]");
  if (!suggestion) return;
  input.value = suggestion.dataset.prompt;
  updateComposer();
  input.focus();
});
$("#composer-form").addEventListener("submit", (event) => { event.preventDefault(); sendMessage(input.value); });
input.addEventListener("input", updateComposer);
input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    sendMessage(input.value);
  }
});
document.addEventListener("keydown", (event) => {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
    event.preventDefault(); newSession();
  }
  if (event.key === "Escape") { state.menuId = null; renderSessions(); closeSidebar(); }
});
document.addEventListener("click", (event) => {
  if (!event.target.closest(".session-actions") && state.menuId) { state.menuId = null; renderSessions(); }
});
$("#cancel-rename").addEventListener("click", () => $("#rename-dialog").close());
$("#rename-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const title = $("#rename-input").value.trim();
  if (!title) return;
  try {
    await api(`/api/sessions/${encodeURIComponent(state.actionId)}`, { method: "PATCH", body: JSON.stringify({ title }) });
    $("#rename-dialog").close();
    await loadSessions();
  } catch (error) { toast(error.message); }
});
$("#cancel-delete").addEventListener("click", () => $("#delete-dialog").close());
$("#confirm-delete").addEventListener("click", async () => {
  try {
    await api(`/api/sessions/${encodeURIComponent(state.actionId)}`, { method: "DELETE" });
    if (state.actionId === state.currentId) {
      state.currentId = null;
      state.messages = [];
      localStorage.removeItem("relay:last-session");
    }
    $("#delete-dialog").close();
    await loadSessions();
    renderMessages();
    toast("Conversation deleted.");
  } catch (error) { toast(error.message); }
});

setTheme(localStorage.getItem("relay:theme") || "light");
updateComposer();
Promise.allSettled([loadSessions(), loadStatus()]).then(async (results) => {
  if (results[0].status === "rejected") { toast("Could not load conversations."); return; }
  const remembered = localStorage.getItem("relay:last-session");
  if (remembered && state.sessions.some((session) => session.id === remembered)) await openSession(remembered);
  else renderMessages();
});
