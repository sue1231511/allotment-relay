function formatApiError(data, fallback) {
  const detail = data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail.map((d) => d.msg || String(d)).join('；');
  }
  return fallback;
}

document.getElementById('recover-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const email = document.getElementById('email').value.trim();
  const result = document.getElementById('result');
  result.classList.remove('hidden');
  result.innerHTML = '查询中…';
  try {
    const res = await fetch('/api/keys/recover', {
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
        ? '服务暂时异常，请刷新页面重试'
        : text || '找回失败');
    }
    if (!res.ok) throw new Error(formatApiError(data, '找回失败'));
    const mcpUrl = data.mcp_url || `${location.origin}/mcp/?api_key=${data.api_key}`;
    result.innerHTML = `
      <p><strong>凭证：</strong></p>
      <pre>${data.api_key}</pre>
      <p>MCP URL：</p>
      <pre>${mcpUrl}</pre>
    `;
  } catch (err) {
    result.textContent = err.message;
  }
});
