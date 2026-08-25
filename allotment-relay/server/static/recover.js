document.getElementById("recover-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const email = document.getElementById("email").value.trim();
  const result = document.getElementById("result");
  result.classList.remove("hidden");
  result.innerHTML = "查询中…";
  try {
    const res = await fetch("/api/keys/recover", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, device_id: (typeof getOrCreateDeviceId === 'function' ? getOrCreateDeviceId() : '') }),
    });
    const text = await res.text();
    let data;
    try {
      data = JSON.parse(text);
    } catch {
      throw new Error(text.includes("Internal Server Error")
        ? "服务暂时异常，请刷新页面重试"
        : text || "找回失败");
    }
    if (!res.ok) throw new Error(formatApiError(data, "找回失败"));
    renderKeyResult(result, {
      apiKey: data.api_key,
      mcpUrl: data.mcp_url || `${location.origin}/mcp/?api_key=${data.api_key}`,
      once: false,
    });
  } catch (err) {
    result.textContent = err.message;
  }
});
