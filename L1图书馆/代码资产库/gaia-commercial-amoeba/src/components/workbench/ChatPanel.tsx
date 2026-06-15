"use client";

import { useState, useRef, useEffect } from "react";
import type { Employee, Message, Department, IntentSuggestion } from "@/lib/data";
import EmployeeAvatar from "./EmployeeAvatar";
import IntentSuggestions from "./IntentSuggestions";

interface ChatPanelProps {
  department: Department | undefined;
  employees: Employee[];
  messages: Message[];
  onSendMessage: (content: string) => void;
  workingEmployee: Employee | null;
  onReportRequest: () => void;
  intentSuggestions: IntentSuggestion[];
  streamingMsgId?: string | null;
}

export default function ChatPanel({
  department,
  employees,
  messages,
  onSendMessage,
  workingEmployee,
  onReportRequest,
  intentSuggestions: suggestions,
  streamingMsgId,
}: ChatPanelProps) {
  const [input, setInput] = useState("");
  const [showReportHint, setShowReportHint] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    if (messages.length >= 3 && department) {
      const userMsgs = messages.filter((m) => m.role === "user").length;
      setShowReportHint(userMsgs >= 2);
    }
  }, [messages, department]);

  const handleSend = () => {
    if (!input.trim()) return;
    onSendMessage(input.trim());
    setInput("");
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  if (!department) {
    return (
      <div className="flex-1 flex items-center justify-center bg-slate-800/30">
        <div className="text-center text-slate-500">
          <div className="text-6xl mb-4">🐝</div>
          <p className="text-lg font-medium text-slate-400">选择一个部门进入蜂巢会议</p>
          <p className="text-sm mt-2">左侧选择部门 → 与AI员工团队实时协作 → 生成专业报告</p>
        </div>
      </div>
    );
  }

  const idleEmployees = employees.filter((e) => e.status !== "working");

  return (
    <div className="flex-1 flex flex-col bg-slate-800/20 min-w-0">
      <div className="px-6 py-3 border-b border-slate-700/30 bg-slate-800/40">
        <div className="flex items-center gap-3">
          <span className="text-xl">{department.icon}</span>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="font-semibold text-slate-200">{department.name}·蜂巢会议</h2>
              <span className="text-[10px] px-2 py-0.5 bg-green-900/40 text-green-400 rounded-full animate-pulse">🟢 进行中</span>
            </div>
            <p className="text-xs text-slate-500">{department.description} · {employees.length}人参会</p>
          </div>
        </div>
      </div>

      <div className="px-6 py-3 border-b border-slate-700/20 bg-slate-800/20">
        <div className="flex items-center gap-6">
          <div>
            <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-2">⚡ 工作区</div>
            <div className="flex gap-2">
              {workingEmployee ? (
                <div className="flex flex-col items-center gap-1">
                  <EmployeeAvatar employee={workingEmployee} size="lg" showStatus showName />
                  <span className="text-[10px] text-blue-400/80 animate-pulse">{workingEmployee.specialty[0] ?? "工作中..."}</span>
                </div>
              ) : (
                <div className="w-16 h-16 rounded-xl bg-slate-700/30 flex items-center justify-center text-slate-500 text-xs">空闲</div>
              )}
            </div>
          </div>
          <div className="flex-1">
            <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-2">🎯 待命区</div>
            <div className="flex gap-2 flex-wrap">
              {idleEmployees.slice(0, 6).map((emp) => (
                <EmployeeAvatar key={emp.id} employee={emp} size="sm" showStatus />
              ))}
              {idleEmployees.length > 6 && (
                <div className="w-8 h-8 rounded-xl bg-slate-700/30 flex items-center justify-center text-[10px] text-slate-500">+{idleEmployees.length - 6}</div>
              )}
            </div>
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
        {messages.length === 0 && (
          <div className="text-center text-slate-500 mt-12">
            <p className="text-sm">开始与{department.name}的AI员工对话</p>
            <p className="text-xs mt-2 text-slate-600">例如：「帮我分析一下最新的行业合规要求」</p>
          </div>
        )}
        {messages.map((msg) => (
          <div key={msg.id} className={`flex gap-3 ${msg.role === "user" ? "justify-end" : ""}`}>
            {msg.role === "employee" && msg.employeeId && (
              <EmployeeAvatar employee={employees.find((e) => e.id === msg.employeeId) ?? employees[0]} size="sm" showStatus={false} />
            )}
            <div className={`max-w-[75%] rounded-2xl px-4 py-3 text-sm ${msg.role === "user" ? "bg-blue-600 text-white rounded-tr-md" : "bg-slate-700/50 text-slate-200 rounded-tl-md"}`}>
              <p className="whitespace-pre-wrap">
                {msg.content}
                {msg.id === streamingMsgId && <span className="inline-block w-[2px] h-4 bg-blue-400 animate-pulse ml-0.5 align-text-bottom" />}
              </p>
            </div>
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      {showReportHint && (
        <div className="mx-6 mb-2">
          <button onClick={onReportRequest} className="w-full py-2 px-4 bg-gradient-to-r from-amber-500/20 to-orange-500/20 border border-amber-500/30 rounded-xl text-sm text-amber-300 hover:from-amber-500/30 hover:to-orange-500/30 transition flex items-center justify-center gap-2">
            <span>📄</span>
            <span>基于以上对话，可以生成一份专业诊断报告</span>
            <span className="text-amber-400 text-xs font-medium">查看 →</span>
          </button>
        </div>
      )}

      <IntentSuggestions suggestions={suggestions} onSelect={onSendMessage} />

      <div className="px-6 py-3 border-t border-slate-700/30 bg-slate-800/40">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1 text-slate-500">
            <button className="p-2 hover:text-slate-300 hover:bg-slate-700 rounded-lg transition" title="语音输入">🎤</button>
            <button className="p-2 hover:text-slate-300 hover:bg-slate-700 rounded-lg transition" title="上传文件">📎</button>
          </div>
          <input ref={inputRef} type="text" value={input} onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={`向${department.name}提问...`}
            className="flex-1 bg-slate-700/50 border border-slate-600/50 rounded-xl px-4 py-2.5 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-500/40 transition"
          />
          <button onClick={handleSend} disabled={!input.trim()}
            className="px-4 py-2.5 bg-blue-600 hover:bg-blue-500 disabled:bg-slate-700 disabled:text-slate-500 text-white rounded-xl text-sm font-medium transition flex items-center gap-1.5">
            发送 <span className="text-xs opacity-70">↵</span>
          </button>
        </div>
      </div>
    </div>
  );
}
