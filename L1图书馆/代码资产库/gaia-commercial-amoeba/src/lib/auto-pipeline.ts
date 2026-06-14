/**
 * 自动信号→报告变现管道
 * 
 * 信号评分≥7 → 自动匹配部门 → 触发OSCAR调研 → 生成报告 → 上架
 * 完全无人值守，定时自动运行
 */

import { collectAllRealSignals, RealSignal } from "./real-signal-sources";
import { runAmoebaCycle } from "./amoeba-engine";
import { departments, reportTemplates } from "@/lib/data";

// ============================================================
// 管道日志
// ============================================================

export interface PipelineLog {
  id: string;
  timestamp: string;
  signalTitle: string;
  source: string;
  score: number;
  matchedDept: string;
  action: "auto_triggered" | "score_too_low" | "no_dept_match" | "report_created" | "listed";
  reportTitle?: string;
  reportPrice?: number;
  error?: string;
}

const logs: PipelineLog[] = [];

function addLog(log: PipelineLog) {
  logs.unshift(log);
  if (logs.length > 100) logs.pop();
  console.log(`[Pipeline] ${log.action}: ${log.signalTitle} → ${log.reportTitle ?? "—"}`);
}

export function getPipelineLogs(): PipelineLog[] {
  return logs;
}

// ============================================================
// 部门匹配引擎
// ============================================================

const DEPT_KEYWORDS: Record<string, string[]> = {
  compliance: ["合规", "法规", "监管", "数据安全", "隐私", "合规", "esg", "政策"],
  intelligence: ["情报", "竞品", "市场分析", "趋势", "融资", "并购", "竞争"],
  marketing: ["营销", "品牌", "推广", "增长", "传播", "转化", "广告"],
  design: ["设计", "ui", "ux", "视觉", "交互", "品牌", "figma"],
  legal: ["法律", "合同", "知识产权", "诉讼", "专利", "商标", "版权"],
  finance: ["财务", "税务", "审计", "财报", "融资", "成本", "预算"],
  strategy: ["战略", "商业模式", "赛道", "创新", "颠覆", "蓝海"],
  technology: ["技术", "ai", "人工智能", "开源", "github", "架构", "代码", "agent", "llm"],
  operations: ["运营", "效率", "流程", "sop", "自动化", "增长"],
};

function matchDepartment(signal: RealSignal): string | null {
  const title = signal.title.toLowerCase();
  const summary = signal.summary.toLowerCase();
  const text = `${title} ${summary}`;

  if (signal.departmentHint && signal.departmentHint.length > 0) {
    for (const hint of signal.departmentHint) {
      if (departments.some((d) => d.id === hint)) return hint;
    }
  }

  let bestDept: string | null = null;
  let bestScore = 0;

  for (const [deptId, keywords] of Object.entries(DEPT_KEYWORDS)) {
    let score = 0;
    for (const kw of keywords) {
      if (text.includes(kw)) score += kw.length;
    }
    if (score > bestScore) {
      bestScore = score;
      bestDept = deptId;
    }
  }

  return bestScore > 0 ? bestDept : null;
}

// ============================================================
// 信号缓存（防止重复处理同一条信号）
// ============================================================

const processedSignals = new Set<string>();

function isProcessed(signal: RealSignal): boolean {
  const key = `${signal.source}|${signal.title}`;
  return processedSignals.has(key);
}

function markProcessed(signal: RealSignal) {
  const key = `${signal.source}|${signal.title}`;
  processedSignals.add(key);
  if (processedSignals.size > 1000) {
    const first = processedSignals.values().next().value;
    if (first) processedSignals.delete(first);
  }
}

// ============================================================
// 主管道：全自动信号→报告
// ============================================================

export async function runAutoPipeline(): Promise<{
  collected: number;
  triggered: number;
  logs: PipelineLog[];
}> {
  console.log("🏁 自动变现管道启动...");

  const { signals } = await collectAllRealSignals();
  console.log(`   📡 采集到 ${signals.length} 条信号`);

  let triggered = 0;

  for (const signal of signals) {
    if (isProcessed(signal)) continue;
    markProcessed(signal);

    const deptId = matchDepartment(signal);

    if (!deptId) {
      addLog({
        id: `pl-${Date.now()}-${Math.random().toString(36).slice(2, 4)}`,
        timestamp: new Date().toISOString(),
        signalTitle: signal.title,
        source: signal.source,
        score: signal.hotScore,
        matchedDept: "unknown",
        action: "no_dept_match",
      });
      continue;
    }

    if (signal.hotScore < 7) {
      addLog({
        id: `pl-${Date.now()}-${Math.random().toString(36).slice(2, 4)}`,
        timestamp: new Date().toISOString(),
        signalTitle: signal.title,
        source: signal.source,
        score: signal.hotScore,
        matchedDept: deptId,
        action: "score_too_low",
      });
      continue;
    }

    try {
      const result = await runAmoebaCycle(deptId);

      addLog({
        id: `pl-${Date.now()}-${Math.random().toString(36).slice(2, 4)}`,
        timestamp: new Date().toISOString(),
        signalTitle: signal.title,
        source: signal.source,
        score: signal.hotScore,
        matchedDept: deptId,
        action: "report_created",
        reportTitle: result.report.title,
        reportPrice: result.report.price,
      });

      triggered++;
      await new Promise((r) => setTimeout(r, 2000));
    } catch (err) {
      addLog({
        id: `pl-${Date.now()}-${Math.random().toString(36).slice(2, 4)}`,
        timestamp: new Date().toISOString(),
        signalTitle: signal.title,
        source: signal.source,
        score: signal.hotScore,
        matchedDept: deptId,
        action: "auto_triggered",
        error: String(err),
      });
    }
  }

  console.log(`   🎯 触发 ${triggered}/${signals.length} 条信号进入OSCAR调研`);
  return { collected: signals.length, triggered, logs: getPipelineLogs().slice(0, 10) };
}
