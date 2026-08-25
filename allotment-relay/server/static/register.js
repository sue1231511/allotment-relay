document.getElementById("key-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const email = document.getElementById("email").value.trim();
  const inviteCode = (document.getElementById("invite-code")?.value || peekInviteCode() || "").trim();
  const result = document.getElementById("result");
  result.classList.remove("hidden");
  result.innerHTML = "签发中…";
  try {
    const res = await fetch("/api/keys/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email,
        invite_code: inviteCode,
        device_id: getOrCreateDeviceId(),
      }),
    });
    const text = await res.text();
    let data;
    try {
      data = JSON.parse(text);
    } catch {
      throw new Error(text.includes("Internal Server Error")
        ? "服务暂时异常，请刷新页面重试（若刚部署，等 1 分钟再试）"
        : text || "签发失败");
    }
    if (!res.ok) throw new Error(formatApiError(data, "签发失败"));
    if (data.invite_ok) clearStoredInvite();
    renderKeyResult(result, {
      apiKey: data.api_key,
      mcpUrl: data.mcp_url || `${location.origin}/mcp/?api_key=${data.api_key}`,
      once: true,
    });
    if (data.invite_note) {
      const p = document.createElement("p");
      p.className = "muted secret-note";
      p.textContent = data.invite_note;
      result.appendChild(p);
    }
  } catch (err) {
    result.textContent = err.message;
  }
});
