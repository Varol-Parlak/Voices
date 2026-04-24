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
    sendBtn.disabled = !msgInput.value.trim() && !selectedImageFile;
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

  // ── Image Upload Logic ────────────────────────────────────────────────────
  const imageUpload = document.getElementById('imageUpload');
  const uploadBtn = document.getElementById('uploadBtn');
  const imagePreviewContainer = document.getElementById('imagePreviewContainer');
  const imagePreview = document.getElementById('imagePreview');
  const removeImageBtn = document.getElementById('removeImageBtn');

  let selectedImageFile = null;

  if (uploadBtn && imageUpload) {
    uploadBtn.addEventListener('click', () => {
      imageUpload.click();
    });

    imageUpload.addEventListener('change', (e) => {
      if (e.target.files && e.target.files[0]) {
        selectedImageFile = e.target.files[0];
        imagePreview.src = URL.createObjectURL(selectedImageFile);
        imagePreviewContainer.style.display = 'block';      
        sendBtn.disabled = false;
        
        // Warm up the vision model
        fetch('http://localhost:5500/warmup_vision', { method: 'POST' })
          .catch(err => console.error("Vision warmup failed:", err));
      }
    });
  }

  if (removeImageBtn) {
    removeImageBtn.addEventListener('click', () => {
      selectedImageFile = null;
      imagePreview.src = '';
      imagePreviewContainer.style.display = 'none';
      imageUpload.value = '';
      sendBtn.disabled = !msgInput.value.trim();
    });
  }

  // ── Send message (Now with Real AI Streaming!) ────────────────────────────
async function sendMessage() {
  const text = msgInput.value.trim();
  if (!text && !selectedImageFile) return;

  // Trigger transition to active state
  const mainLayout = document.querySelector('.main');
  if (mainLayout && mainLayout.classList.contains('is-empty')) {
    mainLayout.classList.remove('is-empty');
    mainLayout.classList.add('is-active');
  }

  let imgUrlForChat = null;
  if (selectedImageFile) {
    imgUrlForChat = URL.createObjectURL(selectedImageFile);
  }
  appendUserMsg(text, imgUrlForChat);

  msgInput.value = '';
  msgInput.style.height = 'auto';
  sendBtn.disabled = true;
  isTyping = true;

  const currentImageFile = selectedImageFile;
  if (selectedImageFile) {
    selectedImageFile = null;
    imagePreview.src = '';
    imagePreviewContainer.style.display = 'none';
    imageUpload.value = '';
  }

  const typingEl = showTyping();

  try {
    let response;
    if (currentImageFile) {
      const formData = new FormData();
      formData.append('file', currentImageFile);
      formData.append('prompt', text);

      response = await fetch('http://localhost:5500/upload_image', {
          method: 'POST',
          body: formData
      });
    } else {
      response = await fetch('http://localhost:5500/stream', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ prompt: text })
      }); 
    }

    typingEl.remove();

    const wrap = document.createElement('div');
    wrap.className = 'msg-group';
    wrap.innerHTML = `
      <div class="msg-ai-wrap">
        <div class="msg msg-ai"></div>
      </div>`;
    chatInner.appendChild(wrap);
    const messageBubble = wrap.querySelector('.msg-ai'); 

    if (!response.ok) {
        let errorMsg = response.statusText;
        try {
            const data = await response.json();
            if (data.error) errorMsg = data.error;
        } catch (e) {}
        messageBubble.innerHTML = renderMarkdown(`Error: ${errorMsg}`);
        return;
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let fullRawText = "";

    while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        fullRawText += chunk;
        
        messageBubble.innerHTML = renderMarkdown(fullRawText);
    }
  } catch (error) {
    console.error("Error communicating with backend:", error);
    typingEl.remove();
  }

  isTyping = false;
  // Re-enable send button only if user typed something while it was generating
  sendBtn.disabled = !msgInput.value.trim() && !selectedImageFile; 
}

  // ── Append user message ───────────────────────────────────────────────────
  function appendUserMsg(text, imgUrl = null) {
    const wrap = document.createElement('div');
    wrap.className = 'msg-group';
    
    let contentHtml = '';
    if (imgUrl) {
      contentHtml += `<img src="${imgUrl}" style="max-width: 100%; max-height: 200px; object-fit: contain; border-radius: 8px; margin-bottom: 8px; display: block; align-self: flex-end;">`;
    }
    if (text) {
      contentHtml += `<div>${escHtml(text)}</div>`;
    }

    wrap.innerHTML = `
      <div class="msg-user-wrap">
        <div class="msg msg-user" style="display: flex; flex-direction: column;">
          ${contentHtml}
        </div>
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
  if (text.trim().startsWith('<div')) return text;

  // Use marked.js if it's available (added in index.html)
  if (typeof marked !== 'undefined') {
    return marked.parse(text);
  }

  let html = text;

  // Code blocks first (before anything else touches them)
  html = html.replace(/```(\w+)?\n?([\s\S]*?)```/g, (_, lang, code) => {
    return `<pre><code class="lang-${lang || 'plaintext'}">${escHtml(code.trim())}</code></pre>`;
  });

  // Inline code
  html = html.replace(/`([^`]+)`/g, (_, code) => `<code>${escHtml(code)}</code>`);

  // Bold and italic
  html = html.replace(/\*\*\*(.*?)\*\*\*/g, '<strong><em>$1</em></strong>');
  html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/\*(.*?)\*/g, '<em>$1</em>');

  // Headings (allow optional leading spaces and multiple spaces after #)
  html = html.replace(/^ *###### +(.+)$/gm, '<h6>$1</h6>');
  html = html.replace(/^ *##### +(.+)$/gm,  '<h5>$1</h5>');
  html = html.replace(/^ *#### +(.+)$/gm,   '<h4>$1</h4>');
  html = html.replace(/^ *### +(.+)$/gm,    '<h3>$1</h3>');
  html = html.replace(/^ *## +(.+)$/gm,     '<h2>$1</h2>');
  html = html.replace(/^ *# +(.+)$/gm,      '<h1>$1</h1>');

  // Unordered lists
  html = html.replace(/(^[-*] .+(\n[-*] .+)*)/gm, (block) => {
    const items = block.split('\n')
      .filter(l => l.trim())
      .map(l => `<li>${l.replace(/^[-*] /, '')}</li>`)
      .join('');
    return `<ul>${items}</ul>`;
  });

  // Ordered lists
  html = html.replace(/(^\d+\. .+(\n\d+\. .+)*)/gm, (block) => {
    const items = block.split('\n')
      .filter(l => l.trim())
      .map(l => `<li>${l.replace(/^\d+\. /, '')}</li>`)
      .join('');
    return `<ol>${items}</ol>`;
  });

  // Horizontal rule
  html = html.replace(/^---$/gm, '<hr>');

  // Tables - add this before the paragraph section
html = html.replace(/^\|(.+)\|\s*\n\|[-| :]+\|\s*\n((?:\|.+\|\s*\n?)*)/gm, (_, header, body) => {
  const headers = header.split('|').map(h => h.trim()).filter(Boolean);
  const rows = body.trim().split('\n').map(row =>
    row.split('|').map(c => c.trim()).filter(Boolean)
  );

  const thead = headers.map(h => `<th>${h}</th>`).join('');
  const tbody = rows.map(row =>
    `<tr>${row.map(c => `<td>${c}</td>`).join('')}</tr>`
  ).join('');

  return `<table><thead><tr>${thead}</tr></thead><tbody>${tbody}</tbody></table>`;
  });

  // Paragraphs — skip lines that are already HTML tags
  html = html.split('\n\n').map(block => {
    block = block.trim();
    if (!block) return '';
    if (/^<(h[1-6]|ul|ol|pre|hr)/.test(block)) return block;
    return `<p>${block.replace(/\n/g, '<br>')}</p>`;
  }).join('');
  
  return html;
}

  // ── Modal Logic ───────────────────────────────────────────────────────────
  const settingsBtn = document.getElementById('settingsBtn');
  const commandsModal = document.getElementById('commandsModal');
  const modalCloseBtn = document.getElementById('modalCloseBtn');

  if (settingsBtn && commandsModal && modalCloseBtn) {
    settingsBtn.addEventListener('click', () => {
      commandsModal.classList.add('is-open');
    });

    modalCloseBtn.addEventListener('click', () => {
      commandsModal.classList.remove('is-open');
    });

    commandsModal.addEventListener('click', (e) => {
      if (e.target === commandsModal) {
        commandsModal.classList.remove('is-open');
      }
    });
  }

window.sendCommand = function(cmd) {
    const msgInput = document.getElementById('msgInput');
    const sendBtn = document.getElementById('sendBtn');
    
    msgInput.value = cmd;
    sendBtn.disabled = false;
    sendMessage(); 
};