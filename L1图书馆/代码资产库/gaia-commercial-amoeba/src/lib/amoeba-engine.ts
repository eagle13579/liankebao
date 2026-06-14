/**
 * 阿米巴经营引擎 v1.0
 * 
 * 每个部门是一个独立阿米巴单元，全自动循环：
 *   调研(Research) → 分析(Analyze) → 产出(Produce) → 售卖(Sell) → 复盘(Review)
 * 
 * 数据存储在 data/amoeba/ 目录下，JSON格式持久化
 */

import { promises as fs } from "fs";
import path from "path";
import { departments, employees, reportTemplates } from "@/lib/data";

// ============================================================
// 类型定义
// ============================================================

export interface AmoebaUnit {
  departmentId: string;
  departmentName: string;
  icon: string;
  status: "idle" | "researching" | "analyzing" | "producing" | "selling" | "reviewing";
  cycle: number;          // 第几轮循环
  lastRunAt: string | null;

  // 调研产出
  currentResearch: Research | null;
  researchHistory: Research[];

  // 报告产出
  reportsProduced: number;
  reportsSold: number;

  // 营收
  revenue: number;        // 累计营收(元)
  costs: number;          // 累计成本(元)
  profit: number;         // 累计利润(元)

  // 进化
  lessonsLearned: string[];
  kpi: {
    researchQuality: number;  // 1-10
    reportQuality: number;
    conversionRate: number;   // 百分比
  };
}

export interface Research {
  id: string;
  date: string;
  topic: string;
  summary: string;
  keyFindings: string[];
  marketSignal: string;
  confidence: number;     // 1-10
  suggestedReport: string;

  // 🆕 OSCAR调研体系
  oscar: {
    objective: string;           // O 目标：决策类型+预期输出
    scope: {                     // S 范围：内核/外围/排除
      core: string;
      periphery: string;
      exclude: string;
    };
    checklist: {                 // C 清单：调研对象+评估维度+信息源
      targets: string[];
      dimensions: string[];
      sources: string[];
    };
    acquisition: {               // A 情报：每条标注证据等级
      findings: { content: string; evidence: "确凿" | "可信" | "推测"; source: string }[];
    };
    judgment: {                  // R 判断：结论+交叉验证+行动建议
      conclusion: string;
      crossValidation: string;
      actionPlan: string;
    };
  };
}

export interface AmoebaState {
  units: AmoebaUnit[];
  lastGlobalRun: string | null;
  totalRevenue: number;
  totalProfit: number;
}

// ============================================================
// 数据持久化
// ============================================================

const DATA_DIR = path.join(process.cwd(), "data", "amoeba");
const STATE_FILE = path.join(DATA_DIR, "state.json");

async function ensureDir() {
  await fs.mkdir(DATA_DIR, { recursive: true });
}

export async function loadState(): Promise<AmoebaState> {
  await ensureDir();
  try {
    const data = await fs.readFile(STATE_FILE, "utf-8");
    return JSON.parse(data);
  } catch {
    return createInitialState();
  }
}

export async function saveState(state: AmoebaState): Promise<void> {
  await ensureDir();
  await fs.writeFile(STATE_FILE, JSON.stringify(state, null, 2), "utf-8");
}

function createInitialState(): AmoebaState {
  const units: AmoebaUnit[] = departments.map((dept) => ({
    departmentId: dept.id,
    departmentName: dept.name,
    icon: dept.icon,
    status: "idle",
    cycle: 0,
    lastRunAt: null,
    currentResearch: null,
    researchHistory: [],
    reportsProduced: 0,
    reportsSold: 0,
    revenue: 0,
    costs: 0,
    profit: 0,
    lessonsLearned: [],
    kpi: { researchQuality: 0, reportQuality: 0, conversionRate: 0 },
  }));

  return { units, lastGlobalRun: null, totalRevenue: 0, totalProfit: 0 };
}

// ============================================================
// AI 调研引擎
// ============================================================

export async function callAI(prompt: string, temperature = 0.7): Promise<string> {
  const apiKey = process.env.LLM_API_KEY;
  if (!apiKey) throw new Error("LLM_API_KEY not configured");

  const res = await fetch("https://api.deepseek.com/v1/chat/completions", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${apiKey}`,
    },
    body: JSON.stringify({
      model: "deepseek-chat",
      messages: [{ role: "user", content: prompt }],
      max_tokens: 2000,
      temperature,
    }),
  });

  if (!res.ok) throw new Error(`AI API error: ${res.status}`);
  const data = await res.json();
  return data.choices?.[0]?.message?.content ?? "";
}

export async function extractJSON(text: string): Promise<any> {
  // 尝试直接解析
  try {
    return JSON.parse(text);
  } catch {}

  // 尝试提取 {...} 块
  const match = text.match(/\{[\s\S]*\}/);
  if (!match) throw new Error("No JSON found in AI response");

  // 清理常见问题：注释、尾部逗号、换行
  let json = match[0]
    .replace(/\/\/.*$/gm, "")       // 去注释
    .replace(/,\s*}/g, "}")          // 去尾部逗号
    .replace(/,\s*\]/g, "]")         // 去数组尾部逗号
    .replace(/\n/g, " ")             // 换行变空格
    .replace(/\s+/g, " ")            // 合并空格
    .trim();

  try {
    return JSON.parse(json);
  } catch {
    // 最后手段：逐行修复
    json = json
      .replace(/(['"])?([a-zA-Z0-9_]+)(['"])?\s*:/g, '"$2":')  // 修复裸key
      .replace(/:\s*'([^']*)'/g, ':"$1"');                      // 修复单引号
    return JSON.parse(json);
  }
}

// ============================================================
// 阿米巴核心循环
// ============================================================

/**
 * Phase 1: OSCAR全网调研
 * 遵循O(目标)→S(范围)→C(清单)→A(情报)→R(判断)五阶段
 */
async function research(deptId: string, deptName: string): Promise<Research> {
  const prompt = `你是一个专业的${deptName}市场研究员。请遵循OSCAR五阶段调研框架进行全网调研，输出JSON格式报告。

OSCAR框架要求：
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

## O 明确目标
- 调研目标：当前(2026年6月)${deptName}领域最值得关注的商业机会
- 决策类型：探索型（发现新机会）
- 预期输出：可立即产出的付费报告主题+市场信号

## S 缩小范围
- 内核（必须调研的核心信息）：${deptName}领域最新的市场变化、政策变动、技术突破
- 外围（可跳过）：过于宏观的经济数据
- 排除（不调研）：与本领域无关的信息

## C 罗列清单
- 调研对象：${deptName}领域头部玩家、新进入者、跨界竞争者
- 评估维度：市场规模、增速、竞争格局、技术突破、政策变化
- 信息源：公开财报、行业报告、新闻动态、社交媒体信号

## A 获取情报（关键！每条标注证据等级）
- 每个发现必须标注：确凿(有数据支撑)/可信(多方提及)/推测(趋势判断)
- 至少2个独立来源交叉验证关键结论

## R 完成判断
- 核心结论：支持/反对/待定的明确立场
- 交叉验证：哪些结论已经过多方验证
- 行动建议：基于调研的可执行下一步

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

输出格式（严格JSON，不要markdown包裹）：
{
  "topic": "调研主题(15字内)",
  "summary": "调研摘要(100-150字)",
  "keyFindings": ["发现1(30字)", "发现2(30字)", "发现3(30字)"],
  "marketSignal": "市场信号描述(50字)",
  "confidence": 8,
  "suggestedReport": "建议付费报告标题",
  "oscar": {
    "objective": "一句话调研目标",
    "scope": {
      "core": "核心调研信息",
      "periphery": "外围信息",
      "exclude": "不调研的信息"
    },
    "checklist": {
      "targets": ["调研对象1", "调研对象2"],
      "dimensions": ["维度1", "维度2", "维度3"],
      "sources": ["信息源1", "信息源2"]
    },
    "acquisition": {
      "findings": [
        {"content": "具体发现", "evidence": "确凿/可信/推测", "source": "来源"}
      ]
    },
    "judgment": {
      "conclusion": "核心结论",
      "crossValidation": "交叉验证情况",
      "actionPlan": "行动建议"
    }
  }
}`;

  const raw = await callAI(prompt, 0.8);
  const data = await extractJSON(raw);

  return {
    id: `res-${Date.now()}`,
    date: new Date().toISOString(),
    topic: data.topic ?? "未命名调研",
    summary: data.summary ?? "",
    keyFindings: data.keyFindings ?? [],
    marketSignal: data.marketSignal ?? "",
    confidence: data.confidence ?? 5,
    suggestedReport: data.suggestedReport ?? `${deptName}市场分析报告`,
    oscar: data.oscar ?? {
      objective: `${deptName}领域市场机会调研`,
      scope: { core: `${deptName}市场动态`, periphery: "宏观经济", exclude: "无关领域" },
      checklist: { targets: ["头部企业", "新进入者"], dimensions: ["市场", "技术", "政策"], sources: ["公开信息"] },
      acquisition: { findings: [{ content: data.summary ?? "", evidence: "可信", source: "AI分析" }] },
      judgment: { conclusion: `${deptName}领域存在可切入的市场机会`, crossValidation: "待验证", actionPlan: `建议产出${deptName}专题报告` },
    },
  };
}

/**
 * Phase 2: 产出报告
 * 基于调研结果生成付费报告
 */
async function produceReport(
  deptId: string,
  deptName: string,
  research: Research
): Promise<{ title: string; price: number; content: string }> {
  const prompt = `你是一个${deptName}专家。基于以下调研发现，生成一份付费报告的大纲和核心内容。

调研主题: ${research.topic}
调研摘要: ${research.summary}
关键发现: ${research.keyFindings.join("、")}

要求：
- 报告标题有吸引力，定价合理(300-2000元)
- 报告内容分5个章节，每章有具体分析和可执行建议
- 输出JSON格式

输出格式：
{
  "title": "报告标题",
  "price": 500,
  "sections": [
    {"title": "章节1标题", "content": "内容"},
    {"title": "章节2标题", "content": "内容"}
  ],
  "summary": "报告一句话卖点(30字)"
}`;

  const raw = await callAI(prompt, 0.7);
  const data = await extractJSON(raw);

  return {
    title: data.title ?? research.suggestedReport,
    price: data.price ?? 500,
    content: data.summary ?? `${deptName}专业分析报告`,
  };
}

/**
 * Phase 3: 复盘学习
 * 分析本期阿米巴运营情况，提炼经验
 */
async function review(
  deptName: string,
  research: Research,
  reportTitle: string,
  cycleNumber: number
): Promise<{ lesson: string; quality: number }> {
  const prompt = `你是一个${deptName}的阿米巴负责人。请对第${cycleNumber}轮运营进行复盘。

本轮做了:
1. 调研主题: ${research.topic}
2. 产出报告: ${reportTitle}
3. 关键发现: ${research.keyFindings.join("、")}

请输出JSON格式复盘：
{
  "lesson": "学到的经验教训(50字)",
  "quality": 7,
  "nextAction": "下一轮改进方向(30字)"
}`;

  const raw = await callAI(prompt, 0.6);
  const data = await extractJSON(raw);

  return {
    lesson: data.lesson ?? "继续探索市场机会",
    quality: data.quality ?? 5,
  };
}

// ============================================================
// 主循环入口
// ============================================================

export async function runAmoebaCycle(departmentId?: string): Promise<{
  unit: AmoebaUnit;
  research: Research;
  report: { title: string; price: number };
  lesson: string;
}> {
  const state = await loadState();
  const targetDepts = departmentId
    ? state.units.filter((u) => u.departmentId === departmentId)
    : state.units;

  if (targetDepts.length === 0) throw new Error("部门不存在");

  // 只处理第一个目标部门（单次调用单部门）
  const unit = targetDepts[0];
  const dept = departments.find((d) => d.id === unit.departmentId)!;

  // Phase 1: 调研
  unit.status = "researching";
  unit.cycle += 1;
  await saveState(state);

  const researchResult = await research(unit.departmentId, unit.departmentName);

  // Phase 2: 产出
  unit.status = "producing";
  unit.currentResearch = researchResult;
  unit.researchHistory.push(researchResult);
  await saveState(state);

  const report = await produceReport(unit.departmentId, unit.departmentName, researchResult);
  unit.reportsProduced += 1;
  unit.costs += 50; // 每轮AI调用成本估算

  // Phase 3: 复盘
  unit.status = "reviewing";
  const reviewResult = await review(
    unit.departmentName,
    researchResult,
    report.title,
    unit.cycle
  );
  unit.lessonsLearned.push(reviewResult.lesson);
  unit.kpi.researchQuality = Math.min(10, unit.kpi.researchQuality + 0.5);
  unit.kpi.reportQuality = Math.min(10, unit.kpi.reportQuality + (reviewResult.quality - 5) * 0.1);

  // 模拟营收(真实营收依赖前端销售)
  if (Math.random() > 0.4) {
    const salePrice = report.price;
    unit.revenue += salePrice;
    unit.profit = unit.revenue - unit.costs;
    unit.reportsSold += 1;
  }

  unit.status = "idle";
  unit.lastRunAt = new Date().toISOString();

  // 更新全局汇总
  state.totalRevenue = state.units.reduce((s, u) => s + u.revenue, 0);
  state.totalProfit = state.units.reduce((s, u) => s + u.profit, 0);
  state.lastGlobalRun = new Date().toISOString();

  await saveState(state);

  return {
    unit,
    research: researchResult,
    report: { title: report.title, price: report.price },
    lesson: reviewResult.lesson,
  };
}

/**
 * 运行全部阿米巴单元（全局循环）
 */
export async function runAllAmoebas(): Promise<{
  results: { deptName: string; research: string; report: string }[];
  totalRevenue: number;
}> {
  const state = await loadState();
  const results = [];

  for (const unit of state.units) {
    try {
      unit.status = "researching";
      const researchResult = await research(unit.departmentId, unit.departmentName);

      unit.currentResearch = researchResult;
      unit.researchHistory.push(researchResult);
      unit.status = "producing";

      const report = await produceReport(unit.departmentId, unit.departmentName, researchResult);
      unit.reportsProduced += 1;
      unit.cycle += 1;
      unit.costs += 50;
      unit.status = "idle";
      unit.lastRunAt = new Date().toISOString();

      // 模拟40%转化率
      if (Math.random() > 0.6) {
        unit.revenue += report.price;
        unit.profit = unit.revenue - unit.costs;
        unit.reportsSold += 1;
      }

      results.push({
        deptName: unit.departmentName,
        research: researchResult.topic,
        report: report.title,
      });
    } catch (err) {
      console.error(`Amoeba ${unit.departmentName} failed:`, err);
    }
  }

  state.totalRevenue = state.units.reduce((s, u) => s + u.revenue, 0);
  state.totalProfit = state.units.reduce((s, u) => s + u.profit, 0);
  state.lastGlobalRun = new Date().toISOString();
  await saveState(state);

  return { results, totalRevenue: state.totalRevenue };
}

/**
 * 获取阿米巴仪表盘数据
 */
export async function getDashboard(): Promise<AmoebaState> {
  return await loadState();
}
