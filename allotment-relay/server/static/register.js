function formatApiError(data, fallback) {
  const detail = data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail.map((d) => d.msg || String(d)).join('；');
  }
  return fallback;
}

document.getElementById('key-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const email = document.getElementById('email').value.trim();
  const result = document.getElementById('result');
  result.classList.remove('hidden');
  result.innerHTML = '签发中…';
  try {
    const res = await fetch('/api/keys/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email }),
    });
    const text = await res.text();
    let data;
    try {
      data = JSON.parse(text);
    } catch {
      throw new Error(text.includes('Internal Server Error')
        ? '服务暂时异常，请刷新页面重试（若刚部署，等 1 分钟再试）'
        : text || '签发失败');
    }
    if (!res.ok) throw new Error(formatApiError(data, '签发失败'));
    mcpUrl = data.mcp_url || `${location.origin}/mcp/?api_key=${data.api_key}`;
    result.innerHTML = `
      <p><strong>潮汐岛凭证（只显示一次）：</strong></p>
      <pre>${data.api_key}</pre>
      <p><strong>推荐</strong> — 一条 URL 搞定（Cursor 直接粘贴）：</p>
      <pre>${mcpUrl}</pre>
      <p>或分开填（URL <strong>末尾必须有 /</strong>）：</p>
      <pre>URL: ${location.origin}/mcp/
Header: Authorization: Bearer ${data.api_key}</pre>
      <p class="muted">类型选 Streamable HTTP / HTTP。勿填无尾斜杠的 /mcp，也勿用 http://。</p>
    `;
  } catch (err) {
    result.textContent = err.message;
  }
});
