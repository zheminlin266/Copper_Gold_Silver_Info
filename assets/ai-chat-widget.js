/**
 * AI Chat Widget — 独立浮窗聊天组件
 *
 * 零依赖、纯 vanilla JS。通过 <script> 标签嵌入任意静态页面。
 * 后端: AI-RAG-site-chat (Python FastAPI)
 *
 * 使用:
 *   <script src="./assets/ai-chat-widget.js"></script>
 *   <script>
 *     AiChat.init({ apiBase: "http://localhost:8000" });
 *   </script>
 */
(function () {
  "use strict";

  // ── 状态 ──────────────────────────────────────────
  let _cfg = { apiBase: "", label: "AI 问答", placeholder: "问我关于矿业日报的问题..." };
  let _open = false;
  let _busy = false;
  let _messages = []; // { role, content }
  let _input = "";
  let _abort = null;
  let _followUps = [];

  // ── DOM 缓存 ──────────────────────────────────────
  let _root, _fab, _panel, _msgList, _inputEl, _sendBtn, _followUpRow;

  // ═══════════════════════════════════════════════════
  // 初始化
  // ═══════════════════════════════════════════════════

  function init(cfg) {
    if (cfg) Object.assign(_cfg, cfg);
    _cfg.apiBase = _cfg.apiBase.replace(/\/+$/, "");
    _injectStyles();
    _buildDOM();
    _bindEvents();
  }

  // ═══════════════════════════════════════════════════
  // 样式注入
  // ═══════════════════════════════════════════════════

  function _injectStyles() {
    if (document.getElementById("ai-chat-widget-css")) return;
    const style = document.createElement("style");
    style.id = "ai-chat-widget-css";
    style.textContent = `
.ai-chat-root{position:fixed;bottom:20px;right:20px;z-index:99999;font-family:Inter,-apple-system,sans-serif;font-size:13px;line-height:1.5;color:#0a0a0a;pointer-events:none}
.ai-chat-root>*{pointer-events:auto}
.ai-chat-fab{display:inline-flex;align-items:center;gap:6px;height:36px;padding:0 12px;background:#fff;border:0.5px solid #d4d4d4;border-radius:10px;cursor:pointer;font:inherit;font-weight:500;color:#0a0a0a;box-shadow:0 2px 8px rgba(0,0,0,.08);transition:background .15s,transform .15s}
.ai-chat-fab:hover{background:#f5f5f5}
.ai-chat-fab:active{transform:scale(.96)}
.ai-chat-fab svg{width:15px;height:15px;flex-shrink:0}
.ai-chat-panel{display:none;position:fixed;inset:0;z-index:100000;background:#fff;flex-direction:column}
.ai-chat-panel.is-open{display:flex}
@media(min-width:480px){.ai-chat-panel{inset:auto;bottom:20px;right:20px;width:380px;max-height:520px;border-radius:14px;box-shadow:0 8px 32px rgba(0,0,0,.12);border:0.5px solid #e0e0e0}}
.ai-chat-header{display:flex;align-items:center;height:44px;padding:0 12px;border-bottom:0.5px solid #e8e8e8;flex-shrink:0;gap:8px}
.ai-chat-header-title{flex:1;font-weight:500;font-size:13px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.ai-chat-header-btn{width:28px;height:28px;display:grid;place-items:center;border:0;background:none;border-radius:6px;cursor:pointer;color:#888;font-size:16px;transition:background .15s,color .15s}
.ai-chat-header-btn:hover{background:#f0f0f0;color:#333}
.ai-chat-msgs{flex:1;overflow-y:auto;padding:14px;display:flex;flex-direction:column;gap:10px;scroll-behavior:smooth}
.ai-chat-msg{max-width:88%;padding:8px 12px;border-radius:10px;font-size:13px;line-height:1.55;word-break:break-word}
.ai-chat-msg.user{align-self:flex-end;background:#f0f0f0;color:#1a1a1a;white-space:pre-wrap}
.ai-chat-msg.assistant{align-self:flex-start;color:#333;white-space:pre-wrap}
.ai-chat-msg.error{align-self:flex-start;color:#c0392b;font-size:12px}
.ai-chat-msg .cursor{display:inline-block;width:1ch;height:1em;background:#0a0a0a;animation:ai-blink .9s steps(1) infinite;vertical-align:text-bottom;margin-left:1px}
@keyframes ai-blink{0%,100%{opacity:1}50%{opacity:0}}
.ai-chat-empty{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:12px;color:#999;text-align:center;padding:20px}
.ai-chat-empty svg{width:36px;height:36px;color:#d0d0d0}
.ai-chat-suggestions{display:flex;flex-wrap:wrap;gap:6px;justify-content:center;margin-top:4px}
.ai-chat-suggestion{border:0.5px solid #d8d8d8;background:#fff;border-radius:20px;padding:6px 14px;font:inherit;font-size:12px;color:#555;cursor:pointer;transition:background .15s}
.ai-chat-suggestion:hover{background:#f5f5f5}
.ai-chat-input-row{border-top:0.5px solid #e8e8e8;padding:10px 12px;flex-shrink:0}
.ai-chat-input-wrap{display:flex;align-items:flex-end;gap:6px;background:#f8f8f8;border:0.5px solid #e0e0e0;border-radius:11px;padding:6px 6px 6px 12px;transition:border-color .15s}
.ai-chat-input-wrap:focus-within{border-color:#b0b0b0}
.ai-chat-input{flex:1;border:0;background:none;resize:none;font:inherit;font-size:13px;line-height:1.5;outline:none;max-height:80px}
.ai-chat-input::placeholder{color:#b0b0b0}
.ai-chat-send{width:30px;height:30px;border:0;border-radius:50%;background:#0a0a0a;color:#fff;cursor:pointer;display:grid;place-items:center;flex-shrink:0;transition:opacity .15s,transform .15s;font-size:14px}
.ai-chat-send:disabled{opacity:.3;cursor:default}
.ai-chat-send:not(:disabled):active{transform:scale(.9)}
.ai-chat-followup{border-top:0.5px solid #e8e8e8;padding:8px 12px;display:flex;gap:6px;flex-wrap:wrap;flex-shrink:0}
.ai-chat-followup button{border:0.5px solid #d8d8d8;background:#fff;border-radius:20px;padding:5px 12px;font:inherit;font-size:12px;color:#555;cursor:pointer;transition:background .15s}
.ai-chat-followup button:hover{background:#f5f5f5}
.ai-chat-typing{display:flex;gap:4px;padding:6px 0}
.ai-chat-typing span{width:5px;height:5px;background:#c0c0c0;border-radius:50%;animation:ai-dot 1.2s ease-in-out infinite}
.ai-chat-typing span:nth-child(2){animation-delay:.15s}
.ai-chat-typing span:nth-child(3){animation-delay:.3s}
@keyframes ai-dot{0%,60%,100%{opacity:.25;transform:translateY(0)}30%{opacity:1;transform:translateY(-4px)}}
    `.trim();
    document.head.appendChild(style);
  }

  // ═══════════════════════════════════════════════════
  // DOM 构建
  // ═══════════════════════════════════════════════════

  function _buildDOM() {
    _root = document.createElement("div");
    _root.className = "ai-chat-root";
    _root.innerHTML = `
      <button class="ai-chat-fab" aria-label="Open AI chat">
        <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M2.5 4.5a2 2 0 012-2h7a2 2 0 012 2v5a2 2 0 01-2 2h-4l-3 2.5v-2.5h-.5a2 2 0 01-1.5-3"/></svg>
        <span>${_cfg.label}</span>
      </button>
      <div class="ai-chat-panel" role="dialog" aria-label="AI Chat">
        <div class="ai-chat-header">
          <span class="ai-chat-header-title">${_cfg.label}</span>
          <button class="ai-chat-header-btn ai-chat-new" title="New chat" aria-label="New chat">+</button>
          <button class="ai-chat-header-btn ai-chat-close" title="Close" aria-label="Close">x</button>
        </div>
        <div class="ai-chat-msgs">
          <div class="ai-chat-empty">
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.3"><path d="M2.5 4.5a2 2 0 012-2h7a2 2 0 012 2v5a2 2 0 01-2 2h-4l-3 2.5v-2.5h-.5a2 2 0 01-1.5-3"/></svg>
            <span>${_cfg.placeholder}</span>
          </div>
        </div>
        <div class="ai-chat-followup" style="display:none"></div>
        <div class="ai-chat-input-row">
          <div class="ai-chat-input-wrap">
            <textarea class="ai-chat-input" rows="1" placeholder="输入问题..."></textarea>
            <button class="ai-chat-send" disabled aria-label="Send">
              <svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M8 13V3M4 6.5 8 3l4 3.5"/></svg>
            </button>
          </div>
        </div>
      </div>
    `;
    document.body.appendChild(_root);

    _fab = _root.querySelector(".ai-chat-fab");
    _panel = _root.querySelector(".ai-chat-panel");
    _msgList = _root.querySelector(".ai-chat-msgs");
    _inputEl = _root.querySelector(".ai-chat-input");
    _sendBtn = _root.querySelector(".ai-chat-send");
    _followUpRow = _root.querySelector(".ai-chat-followup");
  }

  // ═══════════════════════════════════════════════════
  // 事件绑定
  // ═══════════════════════════════════════════════════

  function _bindEvents() {
    _fab.addEventListener("click", _openPanel);
    _root.querySelector(".ai-chat-close").addEventListener("click", _closePanel);
    _root.querySelector(".ai-chat-new").addEventListener("click", _newChat);

    _inputEl.addEventListener("input", function () {
      _input = this.value;
      this.style.height = "auto";
      this.style.height = Math.min(this.scrollHeight, 80) + "px";
      _sendBtn.disabled = !_input.trim() || _busy;
    });

    _inputEl.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        _send();
      }
    });

    _sendBtn.addEventListener("click", _send);

    // 点击 panel 外关闭（桌面端）
    document.addEventListener("click", function (e) {
      if (_open && !_panel.contains(e.target) && e.target !== _fab && !_fab.contains(e.target)) {
        _closePanel();
      }
    });
  }

  // ═══════════════════════════════════════════════════
  // 面板控制
  // ═══════════════════════════════════════════════════

  function _openPanel() {
    _open = true;
    _panel.classList.add("is-open");
    _fab.style.display = "none";
    setTimeout(() => _inputEl.focus(), 100);
    _scrollBottom();
  }

  function _closePanel() {
    _open = false;
    _panel.classList.remove("is-open");
    _fab.style.display = "inline-flex";
    if (_abort) { _abort.abort(); _abort = null; _busy = false; }
  }

  function _newChat() {
    if (_abort) { _abort.abort(); _abort = null; }
    _busy = false;
    _messages = [];
    _followUps = [];
    _renderMessages();
    _hideFollowUps();
    _inputEl.focus();
  }

  // ═══════════════════════════════════════════════════
  // 发送
  // ═══════════════════════════════════════════════════

  function _send(text) {
    var body = (text || _input).trim();
    if (!body || _busy) return;
    _inputEl.value = "";
    _input = "";
    _inputEl.style.height = "auto";
    _sendBtn.disabled = true;
    _hideFollowUps();

    _messages.push({ role: "user", content: body });
    _renderMessages();
    _busy = true;
    _showTyping();

    _streamReply(body);
  }

  // ═══════════════════════════════════════════════════
  // 流式请求
  // ═══════════════════════════════════════════════════

  async function _streamReply(query) {
    var ac = new AbortController();
    _abort = ac;
    var acc = "";
    var msgIdx = _messages.length; // placeholder for assistant msg

    try {
      var res = await fetch(_cfg.apiBase + "/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: _messages }),
        signal: ac.signal,
      });

      if (!res.ok || !res.body) {
        _addError("请求失败，请稍后重试。");
        return;
      }

      var reader = res.body.getReader();
      var decoder = new TextDecoder();
      var appended = false;

      while (true) {
        var chunk = await reader.read();
        if (!chunk || chunk.done) break;
        acc += decoder.decode(chunk.value, { stream: true });

        if (!appended) {
          _messages.push({ role: "assistant", content: acc });
          appended = true;
        } else {
          _messages[_messages.length - 1].content = acc;
        }
        _renderMessages();
        _scrollBottom();
      }

      // 流结束
      _finishReply(acc);

    } catch (err) {
      if (err.name === "AbortError") return;
      _addError("连接中断，请重试。");
    }
  }

  function _finishReply(text) {
    _busy = false;
    _abort = null;
    _sendBtn.disabled = !_input.trim();
    _renderMessages();
    _scrollBottom();
    _fetchFollowUps();
  }

  function _addError(msg) {
    _busy = false;
    _abort = null;
    _messages.push({ role: "assistant", content: msg, _error: true });
    _renderMessages();
    _scrollBottom();
  }

  // ═══════════════════════════════════════════════════
  // 追问建议
  // ═══════════════════════════════════════════════════

  async function _fetchFollowUps() {
    try {
      var res = await fetch(_cfg.apiBase + "/api/suggest", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: _messages }),
      });
      if (!res.ok) return;
      var data = await res.json();
      if (Array.isArray(data.suggestions) && data.suggestions.length) {
        _followUps = data.suggestions;
        _renderFollowUps();
      }
    } catch (_) { /* noop */ }
  }

  function _renderFollowUps() {
    _hideFollowUps();
    if (!_followUps.length || _busy) return;
    _followUpRow.style.display = "flex";
    _followUpRow.innerHTML = "";
    _followUps.forEach(function (q) {
      var btn = document.createElement("button");
      btn.textContent = q;
      btn.addEventListener("click", function () { _send(q); });
      _followUpRow.appendChild(btn);
    });
  }

  function _hideFollowUps() {
    _followUpRow.style.display = "none";
    _followUpRow.innerHTML = "";
  }

  // ═══════════════════════════════════════════════════
  // 渲染
  // ═══════════════════════════════════════════════════

  function _showTyping() {
    _renderMessages();
    var dots = document.createElement("div");
    dots.className = "ai-chat-typing";
    dots.innerHTML = "<span></span><span></span><span></span>";
    _msgList.appendChild(dots);
    _scrollBottom();
  }

  function _renderMessages() {
    // 清除所有消息气泡和 typing 动画（每次重新渲染时重建）
    _msgList.querySelectorAll(".ai-chat-msg, .ai-chat-typing").forEach(function (el) { el.remove(); });

    var empty = _msgList.querySelector(".ai-chat-empty");

    if (_messages.length === 0) {
      if (empty) empty.style.display = "";
    } else {
      if (empty) empty.style.display = "none";
      _messages.forEach(function (m, i) {
        var div = document.createElement("div");
        div.className = "ai-chat-msg " + (m._error ? "error" : m.role);
        div.textContent = m.content;
        if (i === _messages.length - 1 && m.role === "assistant" && _busy && !m._error) {
          var cursor = document.createElement("span");
          cursor.className = "cursor";
          div.appendChild(cursor);
        }
        _msgList.insertBefore(div, empty || null);
      });
    }
  }

  function _scrollBottom() {
    requestAnimationFrame(function () {
      _msgList.scrollTop = _msgList.scrollHeight;
    });
  }

  // ═══════════════════════════════════════════════════
  // 导出
  // ═══════════════════════════════════════════════════

  window.AiChat = { init: init, open: _openPanel, close: _closePanel };
})();
