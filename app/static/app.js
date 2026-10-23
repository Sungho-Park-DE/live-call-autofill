const $ = (id) => document.getElementById(id);
const api = async (method, path, body) => {
  const res = await fetch(path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw Object.assign(new Error(res.statusText), { status: res.status, data });
  return data;
};

let meta = null;
let call = null;
let view = null;
let poller = null;
let mic = null;

async function init() {
  meta = await api("GET", "/api/meta");
  $("engines").textContent = `speech: ${meta.stt} · decisions: ${meta.decider}`;
  $("demo").innerHTML = meta.demos.map((d) => `<option value="${d.id}">${d.title}</option>`).join("");
  $("fields").innerHTML = meta.fields.map((f) => `
    <div class="field" data-key="${f.key}">
      <label for="f-${f.key}">${f.label}${f.required ? " *" : ""}</label>
      <select id="f-${f.key}" disabled>
        <option value="">—</option>
        ${f.options.map((o) => `<option>${o}</option>`).join("")}
      </select>
      <span class="badge"></span>
    </div>`).join("");
  for (const f of meta.fields) {
    $(`f-${f.key}`).addEventListener("change", (e) => setField(f.key, e.target.value));
  }
  $("start").onclick = startCall;
  $("play").onclick = () => api("POST", `/api/calls/${call}/demo/${$("demo").value}`);
  $("say").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && e.target.value.trim()) {
      api("POST", `/api/calls/${call}/say`, { text: e.target.value }).then(render);
      e.target.value = "";
    }
  });
  $("mic").onclick = toggleMic;
  $("confirm").onclick = confirmQuote;
}

async function startCall() {
  await stopMic();
  call = (await api("POST", "/api/calls", { caller: "Demo caller" })).id;
  $("result").textContent = "";
  $("result").className = "";
  setCallControls(true);
  clearInterval(poller);
  poller = setInterval(refresh, 300);
  refresh();
}

function setCallControls(on) {
  $("play").disabled = !on;
  $("say").disabled = !on;
  $("mic").disabled = !on || meta.stt === "fake";
  for (const f of meta.fields) $(`f-${f.key}`).disabled = !on;
}

async function refresh() {
  if (!call) return;
  render(await api("GET", `/api/calls/${call}`));
}

function render(v) {
  view = v;
  const t = $("transcript");
  const atBottom = t.scrollTop + t.clientHeight >= t.scrollHeight - 4;
  t.innerHTML = v.call.finals.map((x) => `<p>${esc(x)}</p>`).join("") +
    (v.call.partial ? `<p class="partial">${esc(v.call.partial)}…</p>` : "") ||
    `<p class="muted">Listening… play a demo call or type a line.</p>`;
  if (atBottom) t.scrollTop = t.scrollHeight;

  for (const f of meta.fields) {
    const entry = v.draft.fields[f.key];
    const row = document.querySelector(`.field[data-key="${f.key}"]`);
    const sel = $(`f-${f.key}`);
    row.classList.toggle("suggested", entry?.origin === "suggested");
    row.classList.toggle("human", entry?.origin === "human");
    if (document.activeElement !== sel) sel.value = entry?.value ?? "";
    const badge = row.querySelector(".badge");
    if (!entry) badge.innerHTML = "";
    else if (entry.origin === "suggested")
      badge.innerHTML = `<span class="tag suggested">${Math.round(entry.confidence * 100)}% · ${esc(entry.source)}</span>`;
    else {
      badge.innerHTML = `<span class="tag human">you</span>`;
      if (!v.draft.confirmed) {
        const b = document.createElement("button");
        b.type = "button";
        b.textContent = "↺";
        b.title = "Hand this field back to the machine";
        b.onclick = () => api("DELETE", `/api/calls/${call}/fields/${f.key}`).then(render);
        badge.append(b);
      }
    }
  }

  const lines = v.quote ? v.quote.lines : v.preview;
  $("lines").tBodies[0].innerHTML = lines.map((l) =>
    `<tr><td>${esc(l.number)}</td><td>${esc(l.name)}</td><td>${l.qty}</td></tr>`).join("");
  renderCompanions(v.quote ? [] : v.companions, v.draft.fields.car?.value);
  $("missing").textContent = v.missing.length ? `needs: ${v.missing.join(", ")}` : "";
  $("confirm").disabled = v.draft.confirmed || v.missing.length > 0;
  if (v.quote) {
    $("result").textContent = `✓ ${v.quote.id} confirmed`;
    setCallControls(false);
    clearInterval(poller);
    stopMic();
  }
}

function renderCompanions(list, car) {
  $("companions").hidden = !list.length;
  const key = JSON.stringify(list);
  if ($("companion-list").dataset.key === key) return;
  $("companion-list").dataset.key = key;
  $("companion-list").innerHTML = list.map((c) => `
    <label class="companion${c.included ? "" : " off"}">
      <input type="checkbox" data-zone="${esc(c.zone)}" ${c.included ? "checked" : ""}>
      <span class="zone">${esc(c.zone)}</span>
      <span class="tag share">${Math.round(c.share * 100)}%</span>
      <span class="muted">of ${c.n} past cases (${c.scope === "model" && car ? esc(car) : "all models"})</span>
      <span class="parts">${c.lines.map((l) => esc(`${l.number} ${l.name}`)).join(" · ") || "pick a car to see parts"}</span>
    </label>`).join("");
  for (const box of $("companion-list").querySelectorAll("input")) {
    box.onchange = () => api("PUT", `/api/calls/${call}/companions/${encodeURIComponent(box.dataset.zone)}`,
      { included: box.checked }).then(render);
  }
}

async function setField(key, value) {
  render(await api("PUT", `/api/calls/${call}/fields/${key}`, { value }));
}

async function confirmQuote() {
  try {
    render(await api("POST", `/api/calls/${call}/confirm`));
  } catch (e) {
    $("result").className = "error";
    $("result").textContent = e.data?.detail?.missing ? `missing: ${e.data.detail.missing.join(", ")}` : String(e.data?.detail ?? e);
  }
}

async function toggleMic() {
  if (mic) return stopMic();
  const stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true } });
  const ctx = new AudioContext({ sampleRate: 16000 });
  await ctx.audioWorklet.addModule("/static/pcm-worklet.js");
  const node = new AudioWorkletNode(ctx, "pcm-chunker");
  const ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/calls/${call}/audio`);
  ws.binaryType = "arraybuffer";
  node.port.onmessage = (e) => ws.readyState === WebSocket.OPEN && ws.send(e.data);
  ctx.createMediaStreamSource(stream).connect(node);
  mic = { stream, ctx, ws };
  $("mic").classList.add("recording");
}

async function stopMic() {
  if (!mic) return;
  const { stream, ctx, ws } = mic;
  mic = null;
  stream.getTracks().forEach((t) => t.stop());
  await ctx.close();
  if (ws.readyState === WebSocket.OPEN) ws.send("end");
  $("mic").classList.remove("recording");
}

const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

init();
