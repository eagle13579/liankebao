/**
 * 链客宝 - AI对话助手浮动组件
 * 右下角浮动聊天按钮，点击展开聊天窗口
 * 纯前端UI组件，不包含API调用逻辑
 * 规则：纯新增，不修改现有业务逻辑
 */

import React, { useState, useCallback, useRef, useEffect } from 'react';

// ─── 类型定义 ───────────────────────────────────────────────

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: number;
}

interface Props {
  /** 发送消息回调 — 由父组件处理API调用 */
  onSendMessage?: (text: string) => void;
  /** 外部消息列表注入（可选） */
  messages?: ChatMessage[];
  /** 是否允许在未连接时发送（默认true） */
  allowSendWhenOffline?: boolean;
  /** 标题文本 */
  title?: string;
}

// ─── 默认消息示例 ──────────────────────────────────────────

const WELCOME_MESSAGE: ChatMessage = {
  id: 'welcome',
  role: 'assistant',
  content: '你好！我是链客宝AI助手，有什么可以帮助你的？',
  timestamp: Date.now(),
};

// ─── 工具函数 ───────────────────────────────────────────────

let _msgIdCounter = 0;
function generateId(): string {
  _msgIdCounter += 1;
  return `msg_${Date.now()}_${_msgIdCounter}`;
}

// ─── 组件 ──────────────────────────────────────────────────

export default function AIChatWidget({
  onSendMessage,
  messages: externalMessages,
  title = 'AI 助手',
}: Props) {
  const [isOpen, setIsOpen] = useState(false);
  const [input, setInput] = useState('');
  const [internalMessages, setInternalMessages] = useState<ChatMessage[]>([WELCOME_MESSAGE]);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // 使用外部消息列表（若提供），否则使用内部状态
  const messages = externalMessages ?? internalMessages;

  // ─── 自动滚动到底部 ─────────────────────────────────────
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // ─── 展开时自动聚焦输入框 ────────────────────────────────
  useEffect(() => {
    if (isOpen) {
      // 等待展开动画完成后再聚焦
      const timer = setTimeout(() => inputRef.current?.focus(), 150);
      return () => clearTimeout(timer);
    }
  }, [isOpen]);

  // ─── 发送消息 ─────────────────────────────────────────────
  const handleSend = useCallback(() => {
    const text = input.trim();
    if (!text) return;

    // 添加到内部消息列表（仅当未提供外部列表时）
    if (!externalMessages) {
      const userMsg: ChatMessage = {
        id: generateId(),
        role: 'user',
        content: text,
        timestamp: Date.now(),
      };
      setInternalMessages((prev) => [...prev, userMsg]);
    }

    // 回调父组件处理实际API调用
    onSendMessage?.(text);
    setInput('');
  }, [input, onSendMessage, externalMessages]);

  // ─── 键盘事件 ─────────────────────────────────────────────
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLInputElement>) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    },
    [handleSend],
  );

  // ─── 渲染 ─────────────────────────────────────────────────
  return (
    <div className="fixed bottom-6 right-6 z-50 flex flex-col items-end">
      {/* ── 聊天窗口 ── */}
      {isOpen && (
        <div className="mb-4 w-80 sm:w-96 bg-white rounded-2xl shadow-2xl border border-gray-200 overflow-hidden flex flex-col animate-in slide-in-from-bottom-4 fade-in duration-200">
          {/* 标题栏 */}
          <div className="flex items-center justify-between px-4 py-3 bg-secondary-600 text-white">
            <div className="flex items-center gap-2">
              <svg
                className="w-5 h-5"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z"
                />
              </svg>
              <span className="text-sm font-semibold">{title}</span>
            </div>
            <button
              onClick={() => setIsOpen(false)}
              className="p-1 rounded-lg hover:bg-secondary-500 transition-colors"
              aria-label="关闭聊天"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M6 18L18 6M6 6l12 12"
                />
              </svg>
            </button>
          </div>

          {/* 消息列表 */}
          <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3 max-h-80 min-h-[200px] bg-gray-50">
            {messages.map((msg) => (
              <div
                key={msg.id}
                className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                <div
                  className={`max-w-[80%] px-3 py-2 rounded-2xl text-sm leading-relaxed whitespace-pre-wrap break-words ${
                    msg.role === 'user'
                      ? 'bg-secondary-600 text-white rounded-br-md'
                      : 'bg-white text-gray-800 border border-gray-200 rounded-bl-md shadow-sm'
                  }`}
                >
                  {msg.content}
                </div>
              </div>
            ))}
            <div ref={messagesEndRef} />
          </div>

          {/* 输入区 */}
          <div className="flex items-center gap-2 border-t border-gray-200 px-3 py-2.5 bg-white">
            <input
              ref={inputRef}
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="输入消息..."
              className="flex-1 px-3 py-2 text-sm border border-gray-200 rounded-xl focus:ring-2 focus:ring-secondary-400 focus:border-secondary-400 outline-none transition-all"
            />
            <button
              onClick={handleSend}
              disabled={!input.trim()}
              className="p-2.5 bg-secondary-600 text-white rounded-xl hover:bg-secondary-700 disabled:bg-gray-200 disabled:text-gray-400 transition-colors flex-shrink-0"
              aria-label="发送消息"
            >
              <svg
                className="w-4 h-4"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"
                />
              </svg>
            </button>
          </div>
        </div>
      )}

      {/* ── 浮动按钮 ── */}
      <button
        onClick={() => setIsOpen((prev) => !prev)}
        className={`flex items-center justify-center w-14 h-14 rounded-full shadow-xl transition-all duration-200 ${
          isOpen
            ? 'bg-gray-600 hover:bg-gray-700 rotate-90'
            : 'bg-secondary-600 hover:bg-secondary-700 hover:scale-105'
        }`}
        aria-label={isOpen ? '关闭AI助手' : '打开AI助手'}
      >
        {isOpen ? (
          <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M6 18L18 6M6 6l12 12"
            />
          </svg>
        ) : (
          <svg
            className="w-6 h-6 text-white"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z"
            />
          </svg>
        )}
      </button>
    </div>
  );
}
