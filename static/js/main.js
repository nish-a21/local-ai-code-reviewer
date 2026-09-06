// ── STATE ────────────────────────────────────────────────────
let currentCode     = "";
let currentLanguage = "auto";
let chatHistory     = [];
let currentReview   = "";

// ── STATUS CHECK ─────────────────────────────────────────────
async function checkStatus() {
  try {
    const res  = await fetch("/api/status");
    const data = await res.json();
    const dot  = document.getElementById("statusDot");
    const txt  = document.getElementById("statusText");

    if (data.ollama === "connected") {
      dot.className = "status-dot connected";
      txt.textContent = data.model;
    } else {
      dot.className = "status-dot disconnected";
      txt.textContent = "Ollama not running";
    }
  } catch {
    document.getElementById("statusDot").className = "status-dot disconnected";
    document.getElementById("statusText").textContent = "Offline";
  }
}

// ── FILE UPLOAD ───────────────────────────────────────────────
document.getElementById("fileInput").addEventListener("change", (e) => {
  const file = e.target.files[0];
  if (!file) return;

  document.getElementById("fileName").textContent = file.name;

  const ext = file.name.split(".").pop().toLowerCase();
  const langMap = {
    py: "python", js: "javascript", ts: "typescript",
    java: "java", cpp: "cpp", c: "c", go: "go",
    rs: "rust", php: "php", rb: "ruby", sql: "sql"
  };
  const detected = langMap[ext];
  if (detected) document.getElementById("langSelect").value = detected;

  const reader = new FileReader();
  reader.onload = (ev) => {
    document.getElementById("codeInput").value = ev.target.result;
  };
  reader.readAsText(file);
});

// ── SUBMIT REVIEW ─────────────────────────────────────────────
async function submitReview() {
  const code = document.getElementById("codeInput").value.trim();
  const lang = document.getElementById("langSelect").value;

  if (!code) {
    showToast("Paste some code first");
    return;
  }

  currentCode     = code;
  currentLanguage = lang;
  chatHistory     = [];
  currentReview   = "";

  // Disable button
  const btn = document.getElementById("reviewBtn");
  btn.disabled = true;
  btn.textContent = "Reviewing...";

  // Show output panel immediately — no spinner
  document.getElementById("emptyState").style.display   = "none";
  document.getElementById("loadingState").style.display = "none";
  document.getElementById("reviewOutput").style.display = "block";
  document.getElementById("panelActions").style.display = "flex";
  document.getElementById("chatSection").style.display  = "flex";
  document.getElementById("chatMessages").innerHTML     = "";

  const output = document.getElementById("reviewOutput");
  output.innerHTML = "<p style='color:var(--text-muted);font-size:13px;'>Starting review...</p>";

  let fullText = "";

  try {
    const res = await fetch("/api/review", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code, language: lang })
    });

    if (!res.ok) {
      const err = await res.json();
      showError(err.error || "Server error");
      return;
    }

    output.innerHTML = "";

    const reader  = res.body.getReader();
    const decoder = new TextDecoder();

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      const chunk = decoder.decode(value, { stream: true });
      const lines = chunk.split("\n");

      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;

        const raw = line.slice(6).trim();

        if (raw === "[DONE]") {
          currentReview = fullText;
          chatHistory = [
            { role: "user", content: `Review this ${lang} code:\n\n\`\`\`${lang}\n${code}\n\`\`\`` },
            { role: "assistant", content: fullText }
          ];
          renderReview(fullText);
          break;
        }

        try {
          const parsed = JSON.parse(raw);
          if (parsed.error) {
            showError(parsed.error);
            break;
          }
          if (parsed.token) {
            fullText += parsed.token;
            output.innerHTML = `<pre style="white-space:pre-wrap;font-family:var(--mono);font-size:13px;line-height:1.6;margin:0;">${escapeHtml(fullText)}</pre>`;
            output.scrollTop = output.scrollHeight;
          }
        } catch {}
      }
    }

  } catch (err) {
    showError("Something went wrong. Is Ollama running?");
  } finally {
    btn.disabled = false;
    btn.innerHTML = `Review
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
           stroke="currentColor" stroke-width="2.5">
        <line x1="5" y1="12" x2="19" y2="12"/>
        <polyline points="12 5 19 12 12 19"/>
      </svg>`;
  }
}

// ── RENDER REVIEW ─────────────────────────────────────────────
function renderReview(markdown) {
  const output = document.getElementById("reviewOutput");

  let html = markdown
    .replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) =>
      `<pre><code>${escapeHtml(code.trim())}</code></pre>`
    )
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/### \[CRITICAL\] (.+)/g,
      '<h3><span class="badge badge-critical">CRITICAL</span> $1</h3>')
    .replace(/### \[MEDIUM\] (.+)/g,
      '<h3><span class="badge badge-medium">MEDIUM</span> $1</h3>')
    .replace(/### \[LOW\] (.+)/g,
      '<h3><span class="badge badge-low">LOW</span> $1</h3>')
    .replace(/## (.+)/g, '<h2>$1</h2>')
    .replace(/### (.+)/g, '<h3>$1</h3>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n\n/g, '</p><p>')
    .replace(/\n/g, '<br/>');

  html = '<p>' + html + '</p>';
  html = html.replace(/<p><\/p>/g, '').replace(/<p><br\/><\/p>/g, '');

  output.innerHTML = html;
  output.style.display = "block";
  document.getElementById("reviewTitle").textContent = "Review";
}

// ── CHAT ──────────────────────────────────────────────────────
async function sendChat() {
  const input    = document.getElementById("chatInput");
  const question = input.value.trim();
  if (!question) return;

  input.value = "";

  addChatMessage(question, "user");
  const thinkingEl = addChatMessage("...", "assistant");

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        code: currentCode,
        language: currentLanguage,
        question,
        history: chatHistory
      })
    });

    const data = await res.json();

    if (data.error) {
      thinkingEl.textContent = "Error: " + data.error;
      return;
    }

    chatHistory = data.history;
    thinkingEl.innerHTML = renderInlineMarkdown(data.reply);

    const msgs = document.getElementById("chatMessages");
    msgs.scrollTop = msgs.scrollHeight;

  } catch {
    thinkingEl.textContent = "Something went wrong.";
  }
}

function addChatMessage(text, role) {
  const msgs = document.getElementById("chatMessages");
  const el   = document.createElement("div");
  el.className = `chat-msg ${role}`;
  el.textContent = text;
  msgs.appendChild(el);
  msgs.scrollTop = msgs.scrollHeight;
  return el;
}

function renderInlineMarkdown(text) {
  return text
    .replace(/```[\s\S]*?```/g, m => {
      const code = m.replace(/```\w*\n?/, '').replace(/```$/, '');
      return `<pre><code>${escapeHtml(code.trim())}</code></pre>`;
    })
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n/g, '<br/>');
}

// ── UTILS ─────────────────────────────────────────────────────
function showError(msg) {
  const output = document.getElementById("reviewOutput");
  output.innerHTML = `<div style="
    background:#FFEBE9;border:1px solid #FF8182;border-radius:6px;
    padding:14px 16px;color:#CF222E;font-size:13px;line-height:1.5;">
    <strong>Error:</strong> ${escapeHtml(msg)}
  </div>`;
  output.style.display = "block";
}

function copyReview() {
  if (!currentReview) return;
  navigator.clipboard.writeText(currentReview);
  showToast("Copied to clipboard");
}

function clearAll() {
  document.getElementById("codeInput").value        = "";
  document.getElementById("fileName").textContent   = "";
  document.getElementById("fileInput").value        = "";
  document.getElementById("reviewOutput").style.display = "none";
  document.getElementById("chatSection").style.display  = "none";
  document.getElementById("emptyState").style.display   = "flex";
  document.getElementById("panelActions").style.display = "none";
  document.getElementById("chatMessages").innerHTML  = "";
  document.getElementById("reviewTitle").textContent = "Review";
  currentCode = ""; chatHistory = []; currentReview  = "";
}

function showToast(msg) {
  let toast = document.querySelector(".toast");
  if (!toast) {
    toast = document.createElement("div");
    toast.className = "toast";
    document.body.appendChild(toast);
  }
  toast.textContent = msg;
  toast.classList.add("show");
  setTimeout(() => toast.classList.remove("show"), 2000);
}

function escapeHtml(str) {
  return str.replace(/&/g,'&amp;').replace(/</g,'&lt;')
            .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ── INIT ──────────────────────────────────────────────────────
checkStatus();
setInterval(checkStatus, 15000);

document.getElementById("codeInput").addEventListener("keydown", (e) => {
  if (e.key === "Tab") {
    e.preventDefault();
    const el = e.target;
    const s  = el.selectionStart;
    el.value = el.value.substring(0, s) + "  " + el.value.substring(el.selectionEnd);
    el.selectionStart = el.selectionEnd = s + 2;
  }
});