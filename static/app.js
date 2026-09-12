const els = {
  talk: document.getElementById("talk"),
  mode: document.getElementById("mode"),
  dot: document.querySelector(".dot"),
  rows: document.getElementById("rows"),
  totals: document.getElementById("totals"),
  log: document.getElementById("log"),
  exportLink: document.getElementById("export"),
  typed: document.getElementById("typed"),
  typedInput: document.getElementById("typedInput"),
};

let ws = null;
let audioCtx = null;
let micNode = null;
let playerNode = null;
let stream = null;
let mock = false;
let sessionId = null;
let live = false;

function addLine(kind, html) {
  const div = document.createElement("div");
  div.className = `line ${kind}`;
  div.innerHTML = html;
  els.log.appendChild(div);
  els.log.scrollTop = els.log.scrollHeight;
  return div;
}

function escapeHtml(text) {
  return String(text ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

// Partial transcripts render as one ghost line that is replaced by the final text.
const partials = { user: null, agent: null };

function partialLine(kind) {
  if (!partials[kind]) {
    partials[kind] = addLine(`${kind} partial`, "");
    partials[kind].style.opacity = "0.55";
  }
  return partials[kind];
}

function showPartial(kind, text) {
  partialLine(kind).textContent = text || "";
  els.log.scrollTop = els.log.scrollHeight;
}

function appendPartial(kind, text) {
  const line = partialLine(kind);
  line.textContent += text || "";
  els.log.scrollTop = els.log.scrollHeight;
}

function clearPartial(kind) {
  if (partials[kind]) {
    partials[kind].remove();
    partials[kind] = null;
  }
}

function renderSheet(sheet) {
  const entries = sheet.entries || [];
  if (!entries.length) {
    els.rows.innerHTML = '<tr class="empty"><td colspan="4">Nothing logged yet.</td></tr>';
  } else {
    els.rows.innerHTML = entries.map((e) => `
      <tr class="${e.status === "pending" ? "pending" : ""}">
        <td>${escapeHtml(e.worker)}${e.note ? ` <span class="muted">${escapeHtml(e.note)}</span>` : ""}</td>
        <td>${e.status === "absent" ? "&mdash;" : `${e.hours}`}</td>
        <td><span class="status ${e.status}">${e.status}</span></td>
        <td class="muted" title="${escapeHtml(e.heard)}">${escapeHtml(e.heard_name)}</td>
      </tr>`).join("");
  }
  const confirmed = entries.filter((e) => e.status === "confirmed").length;
  const pending = entries.filter((e) => e.status === "pending").length;
  els.totals.textContent =
    `${sheet.total_confirmed_hours ?? 0} h confirmed · ${confirmed} row(s) exportable` +
    (pending ? ` · ${pending} awaiting a yes` : "");
  els.exportLink.hidden = !confirmed;
}

function handleEvent(msg) {
  switch (msg.type) {
    case "session":
      sessionId = msg.session_id;
      mock = msg.mock;
      els.exportLink.href = `/export.csv?session=${sessionId}`;
      els.typed.hidden = !mock;
      els.mode.textContent = mock ? "scripted agent (no API key)" : "AssemblyAI Voice Agent";
      break;
    case "ready":
      els.dot.classList.add("live");
      break;
    case "sheet":
      renderSheet(msg.sheet);
      break;
    case "user_partial":
      showPartial("user", msg.text);
      break;
    case "user":
      clearPartial("user");
      if (msg.text) addLine("user", escapeHtml(msg.text));
      break;
    case "agent_delta":
      appendPartial("agent", msg.text);
      break;
    case "agent":
      clearPartial("agent");
      if (msg.text) addLine("agent", escapeHtml(msg.text));
      break;
    case "tool": {
      const ok = msg.result && msg.result.ok;
      const args = Object.entries(msg.arguments || {})
        .map(([k, v]) => `${k}=${escapeHtml(v)}`).join(" ");
      addLine(
        `tool${ok ? "" : " rejected"}`,
        `<b>${escapeHtml(msg.name)}</b> ${escapeHtml(args)} → ${ok ? escapeHtml(msg.result.status || "ok") : `refused: ${escapeHtml(msg.result.reason)}`}`
      );
      break;
    }
    case "audio":
      playChunk(msg.data);
      break;
    case "interrupted":
      if (playerNode) playerNode.port.postMessage("flush");
      break;
    case "error":
      addLine("tool rejected", escapeHtml(msg.message));
      break;
    default:
      break;
  }
}

function playChunk(base64) {
  if (!playerNode || !base64) return;
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  playerNode.port.postMessage(bytes.buffer, [bytes.buffer]);
}

function connect() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws`);
  ws.onmessage = (event) => handleEvent(JSON.parse(event.data));
  ws.onopen = () => { els.talk.disabled = false; };
  ws.onclose = () => {
    els.dot.classList.remove("live");
    els.mode.textContent = "disconnected";
    els.talk.disabled = true;
    stopAudio();
  };
}

async function startAudio() {
  stream = await navigator.mediaDevices.getUserMedia({
    audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
  });
  audioCtx = new AudioContext({ sampleRate: 24000 });
  await audioCtx.audioWorklet.addModule("/static/pcm-worklets.js");

  micNode = new AudioWorkletNode(audioCtx, "mic-processor");
  micNode.port.onmessage = (event) => {
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    const bytes = new Uint8Array(event.data);
    let binary = "";
    for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
    ws.send(JSON.stringify({ type: "audio", data: btoa(binary) }));
  };

  playerNode = new AudioWorkletNode(audioCtx, "player-processor");
  playerNode.connect(audioCtx.destination);

  audioCtx.createMediaStreamSource(stream).connect(micNode);
  micNode.connect(audioCtx.destination); // keep the graph alive; processor emits silence
}

function stopAudio() {
  if (stream) stream.getTracks().forEach((t) => t.stop());
  if (audioCtx) audioCtx.close();
  stream = null; audioCtx = null; micNode = null; playerNode = null;
  live = false;
  els.talk.textContent = "Start talking";
  els.talk.classList.remove("stop");
}

els.talk.addEventListener("click", async () => {
  if (live) {
    ws.send(JSON.stringify({ type: "stop" }));
    stopAudio();
    return;
  }
  try {
    await startAudio();
    live = true;
    els.talk.textContent = "Stop";
    els.talk.classList.add("stop");
  } catch (err) {
    addLine("tool rejected", `microphone unavailable: ${escapeHtml(err.message)}`);
  }
});

els.typed.addEventListener("submit", (event) => {
  event.preventDefault();
  const text = els.typedInput.value.trim();
  if (!text || !ws || ws.readyState !== WebSocket.OPEN) return;
  ws.send(JSON.stringify({ type: "text", text }));
  els.typedInput.value = "";
});

connect();
