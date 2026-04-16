  const chatInner  = document.getElementById('chatInner');
  const chatArea   = document.getElementById('chatArea');
  const msgInput   = document.getElementById('msgInput');
  const sendBtn    = document.getElementById('sendBtn');
  const emptyState = document.getElementById('emptyState');
  const newChatBtn = document.getElementById('newChatBtn');

  let isTyping = false;

  // ── Auto-resize textarea ──────────────────────────────────────────────────
  msgInput.addEventListener('input', () => {
    msgInput.style.height = 'auto';
    msgInput.style.height = Math.min(msgInput.scrollHeight, 180) + 'px';
    sendBtn.disabled = !msgInput.value.trim();
  });

  msgInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (!sendBtn.disabled && !isTyping) sendMessage();
    }
  });

  sendBtn.addEventListener('click', () => {
    if (!isTyping) sendMessage();
  });

  if (newChatBtn) {
    newChatBtn.addEventListener('click', () => {
      chatInner.innerHTML = '';
      const mainLayout = document.querySelector('.main');
      if (mainLayout) {
        mainLayout.classList.remove('is-active');
        mainLayout.classList.add('is-empty');
      }
      msgInput.value = '';
      msgInput.style.height = 'auto';
      sendBtn.disabled = true;
    });
  }

  // ── Fill input from suggestion chips ─────────────────────────────────────
  function fillInput(el) {
    msgInput.value = el.textContent;
    msgInput.dispatchEvent(new Event('input'));
    msgInput.focus();
  }

  // ── Send message (Now with Real AI Streaming!) ────────────────────────────
async function sendMessage() {
  const text = msgInput.value.trim();
  if (!text) return;

  // Trigger transition to active state
  const mainLayout = document.querySelector('.main');
  if (mainLayout && mainLayout.classList.contains('is-empty')) {
    mainLayout.classList.remove('is-empty');
    mainLayout.classList.add('is-active');
  }

  appendUserMsg(text);

  msgInput.value = '';
  msgInput.style.height = 'auto';
  sendBtn.disabled = true;
  isTyping = true;

  const typingEl = showTyping();

  try {
    // 1. Hit your Flask backend
    const response = await fetch('http://localhost:5500/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: text })
    }); 

    // 2. Remove the loading dots the second the AI starts thinking
    typingEl.remove();

    // 3. Create an empty bubble for the AI's incoming response
    const wrap = document.createElement('div');
    wrap.className = 'msg-group';
    wrap.innerHTML = `
      <div class="msg-ai-wrap">
        <div class="msg msg-ai"></div>
      </div>`;
    chatInner.appendChild(wrap);
    
    // Grab the actual bubble where the text goes
    const messageBubble = wrap.querySelector('.msg-ai'); 

    // 4. Set up the stream reader
    const reader = response.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let fullRawText = "";

    // 5. Read the chunks in a loop
    while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        // Decode the binary chunk into text
        const chunk = decoder.decode(value, { stream: true });
        fullRawText += chunk;
        
        // Render the markdown using your existing function!
        messageBubble.innerHTML = renderMarkdown(fullRawText);
        
        // Keep auto-scrolling as the text grows
        scrollBottom();
    }
  } catch (error) {
    console.error("Error communicating with backend:", error);
    typingEl.remove();
  }

  isTyping = false;
  // Re-enable send button only if user typed something while it was generating
  sendBtn.disabled = !msgInput.value.trim(); 
}

  // ── Append user message ───────────────────────────────────────────────────
  function appendUserMsg(text) {
    const wrap = document.createElement('div');
    wrap.className = 'msg-group';
    wrap.innerHTML = `
      <div class="msg-user-wrap">
        <div class="msg msg-user">${escHtml(text)}</div>
      </div>`;
    chatInner.appendChild(wrap);
    scrollBottom();
  }

  // ── Typing indicator ──────────────────────────────────────────────────────
  function showTyping() {
    const el = document.createElement('div');
    el.className = 'typing-indicator';
    el.innerHTML = `
      <div class="typing-dots">
        <span></span><span></span><span></span>
      </div>`;
    chatInner.appendChild(el);
    scrollBottom();
    return el;
  }

  // ── Scroll to bottom ──────────────────────────────────────────────────────
  function scrollBottom() {
    chatArea.scrollTo({ top: chatArea.scrollHeight, behavior: 'smooth' });
  }

  // ── Escape HTML ───────────────────────────────────────────────────────────
  function escHtml(str) {
    return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }

  // ── Basic markdown renderer ───────────────────────────────────────────────
  function renderMarkdown(text) {
    return text
      .replace(/```([\s\S]*?)```/g, '<pre><code>$1</code></pre>')
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.*?)\*/g, '<em>$1</em>')
      .split('\n\n')
      .map(p => `<p>${p.replace(/\n/g, '<br>')}</p>`)
      .join('');
  }