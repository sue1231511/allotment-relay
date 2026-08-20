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
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || '失败');
    const origin = location.origin;
    result.innerHTML = `
      <p><strong>Relay 凭证（只显示一次）：</strong></p>
      <pre>${data.api_key}</pre>
      <p>MCP URL：</p>
      <pre>${origin}/mcp/?api_key=${data.api_key}</pre>
      <p>Header: Authorization: Bearer ${data.api_key}</p>
    `;
  } catch (err) {
    result.textContent = err.message;
  }
});
