"use client";

import { useState, useEffect } from "react";
import Link from "next/link";

export default function AmoebaPage() {
  const [tab, setTab] = useState<"units" | "signals" | "pipeline">("units");
  const [data, setData] = useState<any>(null);
  const [signals, setSignals] = useState<any>(null);
  const [pipelineLogs, setPipelineLogs] = useState<any[]>([]);
  const [running, setRunning] = useState(false);
  const [log, setLog] = useState<string[]>([]);

  const addLog = (msg: string) => setLog((p) => [msg, ...p].slice(0, 30));

  const loadAmoeba = async () => {
    try {
      const r = await fetch("/api/amoeba");
      const d = await r.json();
      setData(d.units ? d : d.dashboard ?? d);
    } catch {}
  };

  const loadSignals = async (mode = "real") => {
    try {
      const r = await fetch(`/api/signals?type=${mode}`);
      const d = await r.json();
      setSignals(d);
      addLog(`📡 采集到 ${d.totalSignals ?? d.signals?.length ?? 0} 条信号 (${mode})`);
    } catch {}
  };

  const loadPipeline = async () => {
    try {
      const r = await fetch("/api/pipeline");
      const d = await r.json();
      setPipelineLogs(d.recentLogs ?? []);
    } catch {}
  };

  useEffect(() => {
    loadAmoeba();
    loadPipeline();
  }, []);

  const runDept = async (id: string, name: string) => {
    setRunning(true);
    addLog(`🏁 ${name} 启动阿米巴循环...`);
    try {
      const r = await fetch("/api/amoeba", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ departmentId: id }),
      });
      const result = await r.json();
      addLog(`✅ ${name}: ${result.research?.slice(0, 30) ?? ""}... ${result.report ?? ""}`);
      await loadAmoeba();
    } catch (e) {
      addLog(`❌ ${name}: ${e}`);
    }
    setRunning(false);
  };

  const runPipeline = async () => {
    setRunning(true);
    addLog("🏁 启动自动变现管道(采集->匹配->调研->报告)...");
    try {
      const r = await fetch("/api/pipeline", { method: "POST" });
      const result = await r.json();
      addLog(`✅ 管道完成: 采集${result.collected}条, 触发${result.triggered}条调研`);
      await loadAmoeba();
      await loadPipeline();
    } catch (e) {
      addLog(`❌ 管道失败: ${e}`);
    }
    setRunning(false);
  };

  const units = data?.units ?? [];
  const totalRevenue = data?.totalRevenue ?? 0;
  const totalProfit = data?.totalProfit ?? 0;

  return (
    <div className="min-h-screen bg-slate-900 text-slate-200">
      <header className="border-b border-slate-800 bg-slate-900/80 backdrop-blur-sm sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="text-2xl">🧬</span>
            <span className="font-bold text-lg">阿米巴作战中心</span>
          </div>
          <div className="flex items-center gap-3">
            <Link href="/workbench" className="text-sm text-slate-400 hover:text-slate-200">← 蜂巢会议</Link>
            <div className="flex gap-1 bg-slate-800 rounded-lg p-1">
              {(["units", "signals", "pipeline"] as const).map((t) => (
                <button key={t} onClick={() => setTab(t)}
                  className={`px-3 py-1.5 text-xs rounded-md transition ${tab === t ? "bg-blue-600 text-white" : "text-slate-400 hover:text-slate-200"}`}>
                  {t === "units" ? "🧬 阿米巴" : t === "signals" ? "📡 信号" : "⚡ 管道"}
                </button>
              ))}
            </div>
            <button onClick={runPipeline} disabled={running}
              className="px-4 py-2 bg-gradient-to-r from-emerald-500 to-teal-500 text-white text-sm font-medium rounded-xl hover:opacity-90 transition disabled:opacity-50">
              {running ? "⏳" : "▶ 全自动"}
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-6">
        <div className="grid grid-cols-5 gap-3 mb-6">
          <div className="bg-gradient-to-br from-green-500/20 to-emerald-500/20 rounded-xl p-4 border border-green-500/30">
            <div className="text-2xl font-bold">¥{totalRevenue.toLocaleString()}</div>
            <div className="text-xs text-slate-400">总营收</div>
          </div>
          <div className={`bg-gradient-to-br rounded-xl p-4 border ${totalProfit >= 0 ? "from-blue-500/20 to-indigo-500/20 border-blue-500/30" : "from-red-500/20 to-rose-500/20 border-red-500/30"}`}>
            <div className="text-2xl font-bold">¥{totalProfit.toLocaleString()}</div>
            <div className="text-xs text-slate-400">总利润</div>
          </div>
          <div className="bg-gradient-to-br from-purple-500/20 to-violet-500/20 rounded-xl p-4 border border-purple-500/30">
            <div className="text-2xl font-bold">{units.filter((u: any) => u.cycle > 0).length}/{units.length}</div>
            <div className="text-xs text-slate-400">活跃阿米巴</div>
          </div>
          <div className="bg-gradient-to-br from-amber-500/20 to-orange-500/20 rounded-xl p-4 border border-amber-500/30">
            <div className="text-2xl font-bold">{units.reduce((s: number, u: any) => s + u.cycle, 0)}轮</div>
            <div className="text-xs text-slate-400">累计运行</div>
          </div>
          <div className="bg-gradient-to-br from-cyan-500/20 to-sky-500/20 rounded-xl p-4 border border-cyan-500/30">
            <div className="text-2xl font-bold">{units.reduce((s: number, u: any) => s + u.reportsProduced, 0)}份</div>
            <div className="text-xs text-slate-400">报告产出</div>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 space-y-3">
            {tab === "units" && (
              <>
                <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wider mb-2">🧬 阿米巴单元 (按营收排序)</h2>
                {[...units].sort((a: any, b: any) => b.revenue - a.revenue).map((unit: any) => (
                  <div key={unit.departmentId} className="bg-slate-800/50 rounded-xl p-4 border border-slate-700/30">
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-3">
                        <span className="text-2xl">{unit.icon}</span>
                        <div>
                          <h3 className="font-semibold text-slate-200 text-sm">{unit.departmentName}</h3>
                          <p className="text-[10px] text-slate-500">第{unit.cycle}轮 · 报告{unit.reportsSold}/{unit.reportsProduced}</p>
                        </div>
                      </div>
                      <div className="flex items-center gap-3">
                        <div className="text-right">
                          <div className="text-sm font-bold text-green-400">¥{unit.revenue}</div>
                          <div className="text-[10px] text-slate-500">{unit.profit >= 0 ? "+" : ""}¥{unit.profit}</div>
                        </div>
                        <button onClick={() => runDept(unit.departmentId, unit.departmentName)} disabled={running}
                          className="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 disabled:bg-slate-700 text-white text-xs rounded-lg transition">
                          ▶
                        </button>
                      </div>
                    </div>
                    <div className="flex gap-2 text-[10px]">
                      <span className="text-slate-500">调研: {"⭐".repeat(Math.min(5, Math.round(unit.kpi.researchQuality / 2)))}</span>
                      <span className="text-slate-500">报告: {"⭐".repeat(Math.min(5, Math.round(unit.kpi.reportQuality / 2)))}</span>
                      {unit.lessonsLearned?.length > 0 && (
                        <span className="text-slate-600">💡 {unit.lessonsLearned[unit.lessonsLearned.length - 1].slice(0, 30)}...</span>
                      )}
                    </div>
                  </div>
                ))}
              </>
            )}

            {tab === "signals" && (
              <>
                <div className="flex items-center justify-between mb-2">
                  <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wider">📡 实时信号流</h2>
                  <div className="flex gap-2">
                    <button onClick={() => loadSignals("real")} className="px-3 py-1 text-xs bg-green-600/30 text-green-300 rounded-lg">真实</button>
                    <button onClick={() => loadSignals("hybrid")} className="px-3 py-1 text-xs bg-blue-600/30 text-blue-300 rounded-lg">混合</button>
                  </div>
                </div>
                {signals?.signals?.slice(0, 15).map((s: any, i: number) => (
                  <div key={i} className="bg-slate-800/30 rounded-xl p-3 border border-slate-700/20">
                    <div className="flex items-center justify-between">
                      <div className="flex-1 min-w-0">
                        <p className="text-sm text-slate-200 truncate">{s.title}</p>
                        <p className="text-[10px] text-slate-500">{s.source} · 热度:{s.hotScore ?? s.totalScore}</p>
                      </div>
                      <span className={`text-[10px] px-2 py-0.5 rounded-full ${s.source?.includes("模拟") ? "bg-yellow-900/30 text-yellow-400" : "bg-green-900/30 text-green-400"}`}>
                        {s.source?.includes("模拟") ? "模拟" : "真实"}
                      </span>
                    </div>
                  </div>
                ))}
                {!signals && (
                  <div className="text-center text-slate-500 py-12">
                    <p className="text-2xl mb-2">📡</p>
                    <p className="text-sm">点击上方的「真实」或「混合」加载信号</p>
                  </div>
                )}
              </>
            )}

            {tab === "pipeline" && (
              <>
                <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wider mb-2">⚡ 管道日志</h2>
                {pipelineLogs.length === 0 ? (
                  <div className="text-center text-slate-500 py-12">
                    <p className="text-2xl mb-2">⚡</p>
                    <p className="text-sm">点击「全自动」启动管道</p>
                  </div>
                ) : (
                  pipelineLogs.map((log: any, i: number) => (
                    <div key={i} className="bg-slate-800/30 rounded-xl p-3 border border-slate-700/20">
                      <div className="flex items-center gap-2">
                        <span className={`text-xs px-2 py-0.5 rounded-full ${log.action === "report_created" ? "bg-green-900/30 text-green-400" : "bg-slate-700 text-slate-400"}`}>
                          {log.action}
                        </span>
                        <span className="text-sm text-slate-300 truncate">{log.signalTitle}</span>
                      </div>
                      {log.reportTitle && (
                        <p className="text-xs text-blue-300 mt-1">📄 {log.reportTitle} (¥{log.reportPrice})</p>
                      )}
                      <p className="text-[10px] text-slate-600 mt-0.5">{log.source} → {log.matchedDept}</p>
                    </div>
                  ))
                )}
              </>
            )}
          </div>

          <div className="lg:col-span-1">
            <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wider mb-2">📋 运行日志</h2>
            <div className="bg-slate-800/30 rounded-xl p-4 border border-slate-700/30 h-[600px] overflow-y-auto">
              {log.length === 0 ? (
                <div className="text-center text-slate-500 text-sm py-12">
                  <p className="text-2xl mb-2">🧬</p>
                  <p>点击部门「▶」或「全自动」启动</p>
                </div>
              ) : (
                <div className="space-y-2 font-mono text-xs text-slate-400">
                  {log.map((entry, i) => (
                    <div key={i} className="leading-relaxed">{entry}</div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
