document.querySelector('#chat-form')?.addEventListener('submit', async (event) => {
  event.preventDefault();
  const result = document.querySelector('#chat-reply');
  result.textContent = 'Thinking…';
  try {
    const response = await fetch('/chatbot', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content}, body: JSON.stringify({message: document.querySelector('#message').value})});
    const data = await response.json();
    result.textContent = data.reply || data.error || 'Please try again.';
  } catch (_) { result.textContent = 'Could not reach Docify. Please try again.'; }
});
