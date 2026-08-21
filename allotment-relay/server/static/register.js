document.getElementById("key-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const email = document.getElementById("email").value.trim();
  const result = document.getElementById("result");
  result.classList.remove("hidden");
  result.innerHTML = "签发中…";
  try {
    const res = await fetch("/api/keys/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email }),
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
    renderKeyResult(result, {
      apiKey: data.api_key,
      mcpUrl: data.mcp_url || `${location.origin}/mcp/?api_key=${data.api_key}`,
      once: true,
    });
  } catch (err) {
    result.textContent = err.message;
  }
});
