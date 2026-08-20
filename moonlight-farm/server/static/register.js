document.getElementById('key-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const email = document.getElementById('email').value.trim();
  const result = document.getElementById('result');
  result.classList.remove('hidden');
  result.innerHTML = '生成中…';
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
      <p><strong>钥匙（只显示一次，请保存）：</strong></p>
      <pre>${data.api_key}</pre>
      <p>MCP URL（可直接粘贴到客户端）：</p>
      <pre>${origin}/mcp/?api_key=${data.api_key}</pre>
      <p>或 Header：<code>Authorization: Bearer ${data.api_key}</code></p>
    `;
  } catch (err) {
    result.textContent = err.message;
  }
});
