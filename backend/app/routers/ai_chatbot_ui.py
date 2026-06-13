"""链客宝AI客服机器人 Web聊天界面

提供基于FastAPI HTMLResponse的现代聊天UI（类似Intercom风格）。
支持消息历史、快捷问题、转人工按钮。
暗色主题，与链客宝品牌一致。

路由:
  - GET /chatbot  — 聊天界面入口
"""

import logging

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["AI客服Web界面"])


@router.get(
    "/chatbot",
    summary="AI客服聊天界面",
    description="链客宝AI客服机器人Web聊天界面，支持智能问答、FAQ匹配和转人工。",
    response_class=HTMLResponse,
)
async def chatbot_ui(request: Request):
    """返回AI客服聊天界面HTML

    现代暗色主题聊天UI，类似Intercom/Drift风格。
    内联HTML/CSS/JS，无外部依赖。
    """
    html_content = _build_chat_ui_html()
    return HTMLResponse(content=html_content, status_code=200)


def _build_chat_ui_html() -> str:
    """构建聊天界面HTML

    Returns:
        完整HTML字符串
    """
    return """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>链客宝AI客服</title>
    <style>
        /* ================================================================
           全局样式
           ================================================================ */
        * { margin: 0; padding: 0; box-sizing: border-box; }

        :root {
            --bg-primary: #0f0f1a;
            --bg-secondary: #1a1a2e;
            --bg-card: #16213e;
            --bg-input: #1e2a45;
            --bg-user-msg: #2563eb;
            --bg-bot-msg: #1e2a45;
            --bg-escalate: #dc2626;
            --bg-escalate-hover: #b91c1c;
            --text-primary: #e8e8f0;
            --text-secondary: #94a3b8;
            --text-muted: #64748b;
            --text-accent: #60a5fa;
            --text-user: #ffffff;
            --border-color: #2a3a5c;
            --border-focus: #3b82f6;
            --shadow-lg: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
            --shadow-md: 0 4px 6px -1px rgba(0, 0, 0, 0.3);
            --radius-sm: 8px;
            --radius-md: 12px;
            --radius-lg: 16px;
            --radius-xl: 20px;
            --font-sans: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto,
                'Helvetica Neue', Arial, 'Noto Sans SC', sans-serif;
        }

        html, body {
            height: 100%;
            font-family: var(--font-sans);
            background: var(--bg-primary);
            color: var(--text-primary);
            overflow: hidden;
        }

        /* ================================================================
           聊天容器
           ================================================================ */
        .chat-container {
            display: flex;
            flex-direction: column;
            height: 100vh;
            max-width: 480px;
            margin: 0 auto;
            background: var(--bg-secondary);
            box-shadow: var(--shadow-lg);
            position: relative;
            overflow: hidden;
        }

        @media (min-width: 481px) {
            .chat-container {
                height: 100vh;
                border-left: 1px solid var(--border-color);
                border-right: 1px solid var(--border-color);
            }
        }

        /* ================================================================
           顶部导航
           ================================================================ */
        .chat-header {
            display: flex;
            align-items: center;
            padding: 16px 20px;
            background: var(--bg-card);
            border-bottom: 1px solid var(--border-color);
            flex-shrink: 0;
            gap: 12px;
        }

        .chat-header-avatar {
            width: 40px;
            height: 40px;
            border-radius: 50%;
            background: linear-gradient(135deg, #3b82f6, #8b5cf6);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 18px;
            flex-shrink: 0;
        }

        .chat-header-info {
            flex: 1;
            min-width: 0;
        }

        .chat-header-title {
            font-size: 15px;
            font-weight: 600;
            color: var(--text-primary);
        }

        .chat-header-status {
            font-size: 12px;
            color: #22c55e;
            display: flex;
            align-items: center;
            gap: 4px;
        }

        .chat-header-status::before {
            content: '';
            width: 6px;
            height: 6px;
            border-radius: 50%;
            background: #22c55e;
            display: inline-block;
        }

        .chat-header-actions {
            display: flex;
            gap: 8px;
        }

        .chat-header-btn {
            width: 36px;
            height: 36px;
            border-radius: 50%;
            border: 1px solid var(--border-color);
            background: transparent;
            color: var(--text-secondary);
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 16px;
            transition: all 0.2s;
        }

        .chat-header-btn:hover {
            background: var(--bg-input);
            color: var(--text-primary);
        }

        /* ================================================================
           消息区域
           ================================================================ */
        .chat-messages {
            flex: 1;
            overflow-y: auto;
            padding: 20px;
            display: flex;
            flex-direction: column;
            gap: 12px;
            scroll-behavior: smooth;
        }

        .chat-messages::-webkit-scrollbar {
            width: 4px;
        }

        .chat-messages::-webkit-scrollbar-track {
            background: transparent;
        }

        .chat-messages::-webkit-scrollbar-thumb {
            background: var(--border-color);
            border-radius: 2px;
        }

        /* ================================================================
           消息气泡
           ================================================================ */
        .message {
            display: flex;
            gap: 8px;
            max-width: 85%;
            animation: messageIn 0.3s ease-out;
        }

        @keyframes messageIn {
            from { opacity: 0; transform: translateY(8px); }
            to { opacity: 1; transform: translateY(0); }
        }

        .message.user {
            align-self: flex-end;
            flex-direction: row-reverse;
        }

        .message.bot {
            align-self: flex-start;
        }

        .message-avatar {
            width: 28px;
            height: 28px;
            border-radius: 50%;
            flex-shrink: 0;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 12px;
        }

        .message.bot .message-avatar {
            background: linear-gradient(135deg, #3b82f6, #8b5cf6);
        }

        .message.user .message-avatar {
            background: #4f46e5;
        }

        .message-bubble {
            padding: 10px 14px;
            border-radius: var(--radius-md);
            font-size: 14px;
            line-height: 1.6;
            word-break: break-word;
            white-space: pre-wrap;
        }

        .message.bot .message-bubble {
            background: var(--bg-bot-msg);
            color: var(--text-primary);
            border-bottom-left-radius: 4px;
        }

        .message.user .message-bubble {
            background: var(--bg-user-msg);
            color: var(--text-user);
            border-bottom-right-radius: 4px;
        }

        .message-bubble strong {
            color: var(--text-accent);
        }

        .message-time {
            font-size: 10px;
            color: var(--text-muted);
            margin-top: 4px;
            text-align: right;
        }

        .message.user .message-time {
            text-align: left;
        }

        /* ================================================================
           快捷问题
           ================================================================ */
        .suggestions {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            padding: 0 20px 8px;
            flex-shrink: 0;
        }

        .suggestion-btn {
            padding: 6px 14px;
            border-radius: var(--radius-xl);
            border: 1px solid var(--border-color);
            background: var(--bg-card);
            color: var(--text-secondary);
            font-size: 12px;
            cursor: pointer;
            transition: all 0.2s;
            white-space: nowrap;
        }

        .suggestion-btn:hover {
            border-color: var(--text-accent);
            color: var(--text-accent);
            background: rgba(59, 130, 246, 0.1);
        }

        /* ================================================================
           输入区域
           ================================================================ */
        .chat-input-area {
            padding: 12px 16px;
            background: var(--bg-card);
            border-top: 1px solid var(--border-color);
            flex-shrink: 0;
        }

        .chat-input-wrapper {
            display: flex;
            gap: 8px;
            align-items: flex-end;
            background: var(--bg-input);
            border-radius: var(--radius-md);
            border: 1px solid var(--border-color);
            padding: 4px;
            transition: border-color 0.2s;
        }

        .chat-input-wrapper:focus-within {
            border-color: var(--border-focus);
        }

        .chat-input {
            flex: 1;
            border: none;
            background: transparent;
            color: var(--text-primary);
            font-size: 14px;
            font-family: var(--font-sans);
            padding: 8px 12px;
            outline: none;
            resize: none;
            max-height: 120px;
            min-height: 20px;
            line-height: 1.5;
        }

        .chat-input::placeholder {
            color: var(--text-muted);
        }

        .chat-send-btn {
            width: 36px;
            height: 36px;
            border-radius: 50%;
            border: none;
            background: var(--text-accent);
            color: white;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 16px;
            transition: all 0.2s;
            flex-shrink: 0;
        }

        .chat-send-btn:hover {
            background: #2563eb;
            transform: scale(1.05);
        }

        .chat-send-btn:disabled {
            opacity: 0.5;
            cursor: not-allowed;
            transform: none;
        }

        /* ================================================================
           转人工按钮
           ================================================================ */
        .escalate-bar {
            display: flex;
            justify-content: center;
            padding: 8px 20px 4px;
            flex-shrink: 0;
        }

        .escalate-btn {
            padding: 6px 16px;
            border-radius: var(--radius-xl);
            border: 1px solid var(--bg-escalate);
            background: transparent;
            color: var(--bg-escalate);
            font-size: 12px;
            cursor: pointer;
            transition: all 0.2s;
            font-family: var(--font-sans);
        }

        .escalate-btn:hover {
            background: var(--bg-escalate);
            color: white;
        }

        /* ================================================================
           加载动画
           ================================================================ */
        .typing-indicator {
            display: flex;
            gap: 4px;
            padding: 8px 0;
        }

        .typing-indicator span {
            width: 6px;
            height: 6px;
            border-radius: 50%;
            background: var(--text-muted);
            animation: typing 1.4s infinite;
        }

        .typing-indicator span:nth-child(2) {
            animation-delay: 0.2s;
        }

        .typing-indicator span:nth-child(3) {
            animation-delay: 0.4s;
        }

        @keyframes typing {
            0%, 60%, 100% { opacity: 0.3; transform: translateY(0); }
            30% { opacity: 1; transform: translateY(-4px); }
        }

        /* ================================================================
           系统消息
           ================================================================ */
        .system-message {
            text-align: center;
            font-size: 12px;
            color: var(--text-muted);
            padding: 8px 0;
        }

        /* ================================================================
           响应式
           ================================================================ */
        @media (max-width: 480px) {
            .chat-container {
                max-width: 100%;
                border: none;
            }

            .message {
                max-width: 90%;
            }
        }
    </style>
</head>
<body>
    <div class="chat-container">
        <!-- 顶部导航 -->
        <div class="chat-header">
            <div class="chat-header-avatar">AI</div>
            <div class="chat-header-info">
                <div class="chat-header-title">链客宝AI客服</div>
                <div class="chat-header-status">在线</div>
            </div>
            <div class="chat-header-actions">
                <button class="chat-header-btn" onclick="clearChat()" title="清空对话">
                    &#x2796;
                </button>
            </div>
        </div>

        <!-- 消息区域 -->
        <div class="chat-messages" id="chatMessages"></div>

        <!-- 快捷问题 -->
        <div class="suggestions" id="suggestions"></div>

        <!-- 转人工 -->
        <div class="escalate-bar">
            <button class="escalate-btn" onclick="escalateToHuman()">
                &#x1F4AC; 转人工客服
            </button>
        </div>

        <!-- 输入区域 -->
        <div class="chat-input-area">
            <div class="chat-input-wrapper">
                <textarea
                    class="chat-input"
                    id="chatInput"
                    placeholder="输入您的问题..."
                    rows="1"
                    onkeydown="handleKeydown(event)"
                    oninput="autoResize(this)"
                ></textarea>
                <button class="chat-send-btn" id="sendBtn" onclick="sendMessage()">
                    &#x27A4;
                </button>
            </div>
        </div>
    </div>

    <script>
        // ================================================================
        // 状态管理
        // ================================================================
        const STATE = {
            sessionId: null,
            isLoading: false,
            escalated: false,
        };

        const API_BASE = '/api/chatbot';

        // ================================================================
        // 工具函数
        // ================================================================
        function getTimestamp() {
            const now = new Date();
            return now.toLocaleTimeString('zh-CN', {
                hour: '2-digit',
                minute: '2-digit',
            });
        }

        function formatTime(isoStr) {
            if (!isoStr) return getTimestamp();
            try {
                const d = new Date(isoStr);
                return d.toLocaleTimeString('zh-CN', {
                    hour: '2-digit',
                    minute: '2-digit',
                });
            } catch {
                return getTimestamp();
            }
        }

        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        function autoResize(textarea) {
            textarea.style.height = 'auto';
            textarea.style.height = Math.min(textarea.scrollHeight, 120) + 'px';
        }

        // ================================================================
        // 消息渲染
        // ================================================================
        function addMessage(role, text, timestamp) {
            const container = document.getElementById('chatMessages');
            const msgDiv = document.createElement('div');
            msgDiv.className = `message ${role}`;

            const avatar = document.createElement('div');
            avatar.className = 'message-avatar';
            avatar.textContent = role === 'bot' ? 'AI' : 'U';

            const bubbleDiv = document.createElement('div');

            const bubble = document.createElement('div');
            bubble.className = 'message-bubble';
            bubble.innerHTML = text.replace(/\n/g, '<br>');

            const time = document.createElement('div');
            time.className = 'message-time';
            time.textContent = formatTime(timestamp);

            bubbleDiv.appendChild(bubble);
            bubbleDiv.appendChild(time);

            if (role === 'bot') {
                msgDiv.appendChild(avatar);
                msgDiv.appendChild(bubbleDiv);
            } else {
                msgDiv.appendChild(bubbleDiv);
                msgDiv.appendChild(avatar);
            }

            container.appendChild(msgDiv);
            scrollToBottom();
        }

        function addTypingIndicator() {
            const container = document.getElementById('chatMessages');
            const div = document.createElement('div');
            div.className = 'message bot';
            div.id = 'typingIndicator';

            const avatar = document.createElement('div');
            avatar.className = 'message-avatar';
            avatar.textContent = 'AI';

            const bubble = document.createElement('div');
            bubble.className = 'message-bubble';

            const indicator = document.createElement('div');
            indicator.className = 'typing-indicator';
            indicator.innerHTML = '<span></span><span></span><span></span>';

            bubble.appendChild(indicator);
            div.appendChild(avatar);
            div.appendChild(bubble);
            container.appendChild(div);
            scrollToBottom();
        }

        function removeTypingIndicator() {
            const el = document.getElementById('typingIndicator');
            if (el) el.remove();
        }

        function scrollToBottom() {
            const container = document.getElementById('chatMessages');
            requestAnimationFrame(() => {
                container.scrollTop = container.scrollHeight;
            });
        }

        // ================================================================
        // 快捷问题渲染
        // ================================================================
        function showSuggestions(suggestions) {
            const container = document.getElementById('suggestions');
            container.innerHTML = '';
            if (!suggestions || suggestions.length === 0) return;

            suggestions.forEach(text => {
                const btn = document.createElement('button');
                btn.className = 'suggestion-btn';
                btn.textContent = text;
                btn.onclick = () => {
                    document.getElementById('chatInput').value = text;
                    sendMessage();
                };
                container.appendChild(btn);
            });
        }

        // ================================================================
        // API 调用
        // ================================================================
        async function sendMessage() {
            const input = document.getElementById('chatInput');
            const text = input.value.trim();
            if (!text || STATE.isLoading) return;

            // 清空输入
            input.value = '';
            autoResize(input);

            // 清空建议
            showSuggestions([]);

            // 显示用户消息
            addMessage('user', escapeHtml(text));

            // 显示打字指示器
            STATE.isLoading = true;
            document.getElementById('sendBtn').disabled = true;
            addTypingIndicator();

            try {
                const resp = await fetch(`${API_BASE}/message`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${getToken()}`,
                    },
                    body: JSON.stringify({
                        text: text,
                        session_id: STATE.sessionId,
                    }),
                });

                if (!resp.ok) {
                    throw new Error(`HTTP ${resp.status}`);
                }

                const data = await resp.json();

                if (data.code === 200 && data.data) {
                    const result = data.data;
                    STATE.sessionId = result.session_id;

                    removeTypingIndicator();

                    // 显示机器人回复
                    if (result.reply) {
                        addMessage('bot', result.reply);
                    }

                    // 显示建议问题
                    if (result.suggestions && result.suggestions.length > 0) {
                        showSuggestions(result.suggestions);
                    }

                    // 更新转人工状态
                    if (result.escalated) {
                        STATE.escalated = true;
                        if (result.ticket) {
                            const ticketMsg =
                                `已创建工单：${result.ticket.ticket_id || ''}`;
                            // 工单信息已包含在回复中
                        }
                    }
                } else {
                    removeTypingIndicator();
                    addMessage('bot', '抱歉，我暂时无法回答这个问题，请稍后再试。');
                }
            } catch (err) {
                console.error('Send message error:', err);
                removeTypingIndicator();
                addMessage('bot', '网络连接异常，请检查网络后重试。');
            } finally {
                STATE.isLoading = false;
                document.getElementById('sendBtn').disabled = false;
                scrollToBottom();
            }
        }

        // ================================================================
        // 转人工
        // ================================================================
        async function escalateToHuman() {
            if (!STATE.sessionId) {
                addMessage('bot', '请先发送一条消息，再申请转人工客服。');
                return;
            }

            if (STATE.escalated) {
                addMessage('bot', '您已提交转人工申请，客服人员将尽快与您联系。');
                return;
            }

            STATE.isLoading = true;
            addTypingIndicator();

            try {
                const resp = await fetch(`${API_BASE}/escalate`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${getToken()}`,
                    },
                    body: JSON.stringify({
                        session_id: STATE.sessionId,
                        reason: '用户点击转人工按钮',
                    }),
                });

                const data = await resp.json();
                removeTypingIndicator();

                if (data.code === 200 && data.data) {
                    STATE.escalated = true;
                    if (data.data.reply) {
                        addMessage('bot', data.data.reply);
                    }
                    showSuggestions([]);
                } else {
                    addMessage('bot', '转人工申请失败，请拨打客服热线：400-888-8888。');
                }
            } catch (err) {
                console.error('Escalate error:', err);
                removeTypingIndicator();
                addMessage('bot', '网络连接异常，请直接拨打客服热线：400-888-8888。');
            } finally {
                STATE.isLoading = false;
            }
        }

        // ================================================================
        // 键盘事件
        // ================================================================
        function handleKeydown(e) {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
            }
        }

        // ================================================================
        // 清空对话
        // ================================================================
        function clearChat() {
            if (!confirm('确定清空当前对话吗？')) return;
            document.getElementById('chatMessages').innerHTML = '';
            STATE.sessionId = null;
            STATE.escalated = false;
            showSuggestions(['如何加盟？', '费用多少？', '怎么入驻？']);
            addMessage('bot', '您好！我是链客宝AI客服助手，请问有什么可以帮您？');
        }

        // ================================================================
        // Token 获取（从 Cookie / localStorage）
        // ================================================================
        function getToken() {
            // 先从 localStorage 获取
            const token = localStorage.getItem('access_token')
                || localStorage.getItem('token')
                || '';
            if (token) return token;

            // 从 Cookie 获取
            const match = document.cookie.match(
                /(?:^|;\\s*)access_token=([^;]+)/
            );
            return match ? match[1] : '';
        }

        // ================================================================
        // 初始化
        // ================================================================
        document.addEventListener('DOMContentLoaded', () => {
            // 发送欢迎消息
            addMessage('bot', '您好！我是链客宝AI客服助手，很高兴为您服务！\\n\\n您可以问我以下问题：\\n1. 如何成为经销商/加盟商？\\n2. 加盟费用和会员等级\\n3. 如何入驻平台\\n4. 签约流程\\n5. 对接会参加方式');

            // 显示初始建议
            showSuggestions(['如何加盟？', '费用多少？', '怎么入驻？', '转人工']);
        });
    </script>
</body>
</html>"""
