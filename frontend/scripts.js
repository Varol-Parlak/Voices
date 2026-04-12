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

  // ── Send message ──────────────────────────────────────────────────────────
  function sendMessage() {
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

    // Simulate AI response (replace this with real API call later)
    const delay = 900 + Math.random() * 800;
    setTimeout(() => {
      typingEl.remove();
      const reply = getMockReply(text);
      appendAiMsg(reply);
      isTyping = false;
      sendBtn.disabled = !msgInput.value.trim();
    }, delay);
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

  // ── Append AI message ─────────────────────────────────────────────────────
  function appendAiMsg(text) {
    const voice = document.getElementById('voiceSelect').value;
    const wrap = document.createElement('div');
    wrap.className = 'msg-group';
    wrap.innerHTML = `
      <div class="msg-ai-wrap">
        <div class="ai-avatar">✦</div>
        <div class="msg msg-ai">${renderMarkdown(text)}</div>
      </div>`;
    chatInner.appendChild(wrap);
    scrollBottom();
  }

  // ── Typing indicator ──────────────────────────────────────────────────────
  function showTyping() {
    const el = document.createElement('div');
    el.className = 'typing-indicator';
    el.innerHTML = `
      <div class="ai-avatar">✦</div>
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

  // ── Mock replies (remove when wiring real backend) ────────────────────────
  function getMockReply(input) {
    const lower = input.toLowerCase();
    if (lower.includes('hello') || lower.includes('hi'))
      return "Hey! What's up?";
    if (lower.includes('python'))
      return "Sure. What do you need — a snippet, a full script, or an explanation of something specific?";
    if (lower.includes('backprop'))
      return "Backpropagation is just the chain rule from calculus applied backwards through a neural network.\n\nYou compute the loss, then work backwards layer by layer — each weight gets nudged by how much it contributed to the error. That's your gradient. Then you use it to update weights via gradient descent.\n\nWant the math or a code walkthrough?";
    return "Got it. Hook this up to `control.py` and I'll give you a real answer.";
  }