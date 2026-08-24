function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function formatApiError(data, fallback) {
  const detail = data?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((d) => d.msg || String(d)).join("；");
  }
  return fallback;
}

async function copyText(text, btn) {
  const value = String(text || "");
  let ok = false;
  try {
    await navigator.clipboard.writeText(value);
    ok = true;
  } catch {
    const ta = document.createElement("textarea");
    ta.value = value;
    ta.setAttribute("readonly", "");
    ta.style.position = "fixed";
    ta.style.left = "-9999px";
    document.body.appendChild(ta);
    ta.select();
    try {
      ok = document.execCommand("copy");
    } catch {
      ok = false;
    }
    ta.remove();
  }
  if (!btn) return;
  const prev = btn.textContent;
  btn.textContent = ok ? "已复制" : "复制失败，请长按全选";
  btn.disabled = true;
  setTimeout(() => {
    btn.textContent = prev;
    btn.disabled = false;
  }, 1600);
}

function secretBlock(label, value) {
  return `
    <div class="secret-block">
      <div class="secret-head">
        <span>${escapeHtml(label)}</span>
        <button type="button" class="btn secret-copy" data-copy="${escapeHtml(value)}">复制</button>
      </div>
      <pre class="secret-value" tabindex="0">${escapeHtml(value)}</pre>
    </div>
  `;
}

function renderKeyResult(el, { apiKey, mcpUrl, once = false }) {
  const header = `Authorization: Bearer ${apiKey}`;
  const mcpPath = `${location.origin.replace(/\/$/, "")}/mcp/`;
  el.classList.remove("hidden");
  el.innerHTML = `
    ${secretBlock(once ? "潮汐岛凭证（只显示一次，先存好）" : "潮汐岛凭证", apiKey)}
    ${secretBlock("MCP 地址（Cursor 直接粘贴这一条）", mcpUrl)}
    ${secretBlock("Authorization 请求头（分开填时用）", header)}
    <p class="muted secret-note">
      类型选 Streamable HTTP / HTTP。MCP URL 末尾必须有 /。
      分开填时 URL 用 <code class="secret-inline">${escapeHtml(mcpPath)}</code>
    </p>
    <p class="muted secret-note">
      人要自己玩：先把凭证存好，打开 <a href="/play">上手</a>。和 AI 同一个号。
    </p>
  `;
  el.querySelectorAll(".secret-copy").forEach((btn) => {
    btn.addEventListener("click", () => copyText(btn.getAttribute("data-copy") || "", btn));
  });
}
