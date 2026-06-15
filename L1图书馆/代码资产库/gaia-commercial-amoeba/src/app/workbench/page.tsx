"use client";

import { useState, useCallback, useEffect } from "react";
import Sidebar from "@/components/workbench/Sidebar";
import ChatPanel from "@/components/workbench/ChatPanel";
import BoardPanel from "@/components/workbench/BoardPanel";
import ReportPreviewModal from "@/components/workbench/ReportPreviewModal";
import FileLibrary from "@/components/workbench/FileLibrary";
import {
  departments,
  employees,
  getEmployeesByDepartment,
  getDepartment,
  getEmployee,
  getIntentSuggestions,
  generateReportPreview,
} from "@/lib/data";
import type { Message, Report, Employee } from "@/lib/data";

export default function WorkbenchPage() {
  const [selectedDept, setSelectedDept] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [workingEmployee, setWorkingEmployee] = useState<string | null>(null);
  const [isThinking, setIsThinking] = useState(false);
  const [report, setReport] = useState<Report | null>(null);
  const [showReportModal, setShowReportModal] = useState(false);
  const [paying, setPaying] = useState(false);
  const [paymentUrl, setPaymentUrl] = useState<string | undefined>();
  const [showFileLib, setShowFileLib] = useState(false);
  const [fileCount, setFileCount] = useState(0);

  useEffect(() => {
    const load = async () => {
      try {
        const res = await fetch("/api/files");
        const data = await res.json();
        setFileCount(data.total ?? 0);
      } catch { /* ignore */ }
    };
    load();
  }, []);

  const [streamingMsgId, setStreamingMsgId] = useState<string | null>(null);

  const deptEmployees = selectedDept ? getEmployeesByDepartment(selectedDept) : [];
  const currentWorkingEmp: Employee | null = (workingEmployee ? getEmployee(workingEmployee) : null) ?? null;
  const currentDept = selectedDept ? getDepartment(selectedDept) : undefined;

  const handleSendMessage = useCallback(
    async (content: string) => {
      if (!selectedDept || isThinking) return;

      const userMsg: Message = {
        id: `msg-${Date.now()}-user`,
        role: "user",
        content,
        timestamp: new Date().toISOString(),
      };
      const updatedMessages = [...messages, userMsg];
      setMessages(updatedMessages);
      setIsThinking(true);

      const replyId = `msg-${Date.now()}-reply`;
      const placeholder: Message = {
        id: replyId,
        role: "employee",
        employeeId: undefined,
        content: "",
        timestamp: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, placeholder]);
      setStreamingMsgId(replyId);

      try {
        const res = await fetch("/api/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            departmentId: selectedDept,
            message: content,
            history: updatedMessages.map((m) => ({ role: m.role, content: m.content })),
          }),
        });

        const reader = res.body?.getReader();
        if (!reader) throw new Error("No reader");

        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() ?? "";

          for (const line of lines) {
            const trimmed = line.trim();
            if (!trimmed || !trimmed.startsWith("data: ")) continue;
            const data = trimmed.slice(6);

            try {
              const event = JSON.parse(data);

              if (event.type === "meta" && event.employeeId) {
                setWorkingEmployee(event.employeeId);
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === replyId ? { ...m, employeeId: event.employeeId } : m
                  )
                );
              } else if (event.type === "content") {
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === replyId ? { ...m, content: m.content + event.content } : m
                  )
                );
              } else if (event.type === "done") {
                if (workingEmployee) {
                  const emp = employees.find((e) => e.id === workingEmployee);
                  if (emp) emp.status = "idle";
                }
                setWorkingEmployee(null);
                setStreamingMsgId(null);
              }
            } catch {
              // skip
            }
          }
        }
      } catch {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === replyId
              ? { ...m, content: `收到您的问题：「${content}」。请稍候，我在分析中...` }
              : m
          )
        );
      }
      setIsThinking(false);
    },
    [selectedDept, isThinking, messages, workingEmployee]
  );

  const handleSelectDept = useCallback((deptId: string) => {
    setSelectedDept(deptId);
    setMessages([]);
    setWorkingEmployee(null);
    setReport(null);
    setShowReportModal(false);
  }, []);

  const handleSelectEmployee = useCallback((empId: string) => {
    const emp = getEmployee(empId);
    if (!emp || !selectedDept) return;

    const greeting: Message = {
      id: `msg-${Date.now()}-greet`,
      role: "employee",
      employeeId: empId,
      content: `您好，我是${emp.name}（${emp.title}）。\n\n我的专长包括：${emp.specialty.join("、")}。\n\n请问有什么可以帮您？`,
      timestamp: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, greeting]);
    setWorkingEmployee(empId);
    setTimeout(() => {
      const empRef = employees.find((e) => e.id === empId);
      if (empRef) empRef.status = "idle";
      setWorkingEmployee(null);
    }, 2000);
  }, [selectedDept]);

  const handleReportRequest = useCallback(async () => {
    if (!selectedDept || isThinking) return;

    setIsThinking(true);
    const templatesRes = await fetch(`/api/report?department=${selectedDept}`);
    const templatesData = await templatesRes.json();

    if (templatesData.templates && templatesData.templates.length > 0) {
      const template = templatesData.templates[0];
      const res = await fetch("/api/report", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ departmentId: selectedDept, templateId: template.id }),
      });
      const data = await res.json();
      setReport(data.report);
      setShowReportModal(true);
    } else {
      const fallbackReport = generateReportPreview("rpt-compliance-1", selectedDept);
      setReport(fallbackReport);
      setShowReportModal(true);
    }
    setIsThinking(false);
  }, [selectedDept, isThinking]);

  const handlePurchase = useCallback(async (reportId: string) => {
    if (!selectedDept || !report || paying) return;

    setPaying(true);
    try {
      const templateId = report.templateId || `rpt-${selectedDept}-1`;

      const res = await fetch("/api/checkout", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          reportId,
          departmentId: selectedDept,
          templateId,
        }),
      });

      if (!res.ok) {
        throw new Error("支付会话创建失败");
      }

      const data = await res.json();

      if (data.sessionUrl) {
        setPaymentUrl(data.sessionUrl);
        window.location.href = data.sessionUrl;
      }
    } catch (err) {
      console.error("Payment error:", err);
      alert("支付服务暂时不可用，请稍后重试");
      setPaying(false);
    }
  }, [selectedDept, report, paying]);

  return (
    <div className="flex h-screen bg-slate-900 text-slate-200">
      <Sidebar
        departments={departments}
        employees={employees}
        selectedDept={selectedDept}
        onSelectDept={handleSelectDept}
        onSelectEmployee={handleSelectEmployee}
        onOpenFileLibrary={() => setShowFileLib(true)}
        fileCount={fileCount}
      />

      <ChatPanel
        department={currentDept}
        employees={deptEmployees}
        messages={messages}
        onSendMessage={handleSendMessage}
        workingEmployee={currentWorkingEmp}
        onReportRequest={handleReportRequest}
        intentSuggestions={selectedDept ? getIntentSuggestions(selectedDept) : []}
        streamingMsgId={streamingMsgId}
      />

      <BoardPanel
        selectedDept={selectedDept}
      />

      {isThinking && (
        <div className="fixed inset-0 z-40 pointer-events-none flex items-end justify-center pb-24">
          <div className="bg-slate-800/90 backdrop-blur-sm rounded-full px-6 py-3 flex items-center gap-3 border border-slate-700/50 shadow-xl">
            <div className="flex gap-1">
              <span className="w-2 h-2 bg-blue-400 rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
              <span className="w-2 h-2 bg-blue-400 rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
              <span className="w-2 h-2 bg-blue-400 rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
            </div>
            <span className="text-sm text-slate-300">
              {currentDept?.name}员工正在分析...
            </span>
          </div>
        </div>
      )}

      <ReportPreviewModal
        report={report}
        department={currentDept}
        isOpen={showReportModal}
        onClose={() => { setShowReportModal(false); setPaying(false); }}
        onPurchase={handlePurchase}
        paying={paying}
        paymentUrl={paymentUrl}
      />

      <FileLibrary
        departments={departments}
        selectedDept={selectedDept}
        isOpen={showFileLib}
        onClose={() => setShowFileLib(false)}
      />
    </div>
  );
}
