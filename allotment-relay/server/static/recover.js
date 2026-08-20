document.getElementById('recover-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const email = document.getElementById('email').value.trim();
  const result = document.getElementById('result');
  result.classList.remove('hidden');
  try {
    const res = await fetch('/api/keys/recover', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || '失败');
    result.innerHTML = `<pre>${data.api_key}\n\n${location.origin}${data.mcp_url}</pre>`;
  } catch (err) {
    result.textContent = err.message;
  }
});
