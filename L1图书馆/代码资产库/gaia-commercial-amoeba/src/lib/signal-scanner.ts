/**
 * 阿米巴信号扫描器 — 每日自动捕捉赚钱机会
 * 
 * 每个部门用AI扫描2-3个信号源，初筛后输出结构化机会报告
 * 每天早8:00自动运行，每部门耗时约10分钟，API成本约¥0.5
 */

import { departments } from "@/lib/data";
import { extractJSON, callAI } from "./amoeba-engine";

// ============================================================
// 信号源定义
// ============================================================

export interface SignalSource {
  name: string;
  url: string;
  type: "问答" | "新闻" | "社交" | "招聘" | "代码" | "政策" | "财务";
}

export interface OpportunitySignal {
  id: string;
  date: string;
  departmentId: string;
  departmentName: string;
  
  // 信号来源
  source: SignalSource;
  title: string;
  summary: string;
  
  // 三维评分
  heatScore: number;       // 热度 1-10
  payScore: number;        // 付费意愿 1-10  
  advantageScore: number;  // 竞争优势 1-10
  totalScore: number;      // 综合 = heat*0.3 + pay*0.4 + advantage*0.3
  
  // OSCAR入口
  recommendOSCAR: boolean; // ≥7分推荐进入OSCAR调研
  suggestedReport: string;
  
  // 证据
  evidence: "确凿" | "可信" | "推测";
  sourceUrl: string;
}

// ============================================================
// 各部门专属信号源
// ============================================================

const DEPT_SOURCES: Record<string, { name: string; scanPrompt: string }[]> = {
  compliance: [
    { name: "知乎法律版热门", scanPrompt: "扫描知乎法律/合规话题下近7天最热门的5个问题，找出蕴含合规咨询需求的问题" },
    { name: "政府政策更新", scanPrompt: "扫描中国政府网/司法部网站近7天发布的新法规、新政策，关注企业合规相关的变化" },
  ],
  intelligence: [
    { name: "36氪快讯", scanPrompt: "扫描36氪/虎嗅近7天最热门的10篇商业报道，识别正在升温的赛道和融资事件" },
    { name: "Crunchbase融资", scanPrompt: "扫描Crunchbase/IT桔子近7天中国企业的融资事件，关注B轮前的早期项目方向" },
  ],
  marketing: [
    { name: "小红书/抖音热点", scanPrompt: "扫描小红书和抖音近7天的消费类热门话题，识别正在爆发的消费趋势和品牌机会" },
    { name: "微博热搜商业版", scanPrompt: "扫描微博热搜中与商业/消费相关的话题，提取3个值得关注的信号" },
  ],
  design: [
    { name: "设计社区趋势", scanPrompt: "扫描Dribbble/Behance近7天最受欢迎的设计作品和热门话题，识别设计趋势变化" },
    { name: "设计工具更新", scanPrompt: "扫描Figma/设计类公众号近7天的产品更新和行业讨论，找出设计工具的变革方向" },
  ],
  legal: [
    { name: "裁判文书新案例", scanPrompt: "扫描中国裁判文书网近7天的新型纠纷案例，识别新的法律风险点和合同需求" },
    { name: "知识产权动态", scanPrompt: "扫描国知局/商标局近7天的政策变化和典型案例，关注知识产权保护新需求" },
  ],
  finance: [
    { name: "财税政策更新", scanPrompt: "扫描财政部/税务总局近7天的新政策，关注企业财税合规相关的变化" },
    { name: "上市公司财报季", scanPrompt: "扫描近7天发布财报的上市公司，提取行业财务趋势和标杆数据" },
  ],
  strategy: [
    { name: "深度商业分析", scanPrompt: "扫描36氪深度/哈佛商业评论近7天的深度文章，识别商业模式创新的信号" },
    { name: "政策导向分析", scanPrompt: "扫描国家发改委/工信部近期政策文件，识别国家重点扶持的产业方向" },
  ],
  technology: [
    { name: "GitHub趋势", scanPrompt: "扫描GitHub Trending近7天最热门的项目，识别技术趋势和开发者需求" },
    { name: "HackerNews/arXiv", scanPrompt: "扫描HackerNews和arXiv近7天讨论最热烈的技术话题，找出技术突破点" },
  ],
  operations: [
    { name: "增长案例库", scanPrompt: "扫描增长黑客/运营案例类公众号近7天的案例分享，识别可复用的增长策略" },
    { name: "SaaS动态", scanPrompt: "扫描SaaS行业公众号近7天的产品更新和运营策略，找出运营优化方向" },
  ],
};

// ============================================================
// AI信号扫描引擎
// ============================================================

async function scanSources(
  deptId: string,
  deptName: string
): Promise<OpportunitySignal[]> {
  const sources = DEPT_SOURCES[deptId] ?? [];
  const signals: OpportunitySignal[] = [];

  for (const source of sources) {
    try {
      const prompt = `你是一位专业的${deptName}市场信号侦察员。

${source.scanPrompt}

要求：
1. 找出最有可能蕴含「付费商业需求」的3个信号
2. 每个信号必须评估：热度(1-10)、付费意愿(1-10)、我们的竞争优势(1-10)
3. 综合评分=热度×30%+付费意愿×40%+竞争优势×30%
4. 综合≥7分的标注推荐进入OSCAR深度调研
5. 证据等级标注：确凿(有数据) / 可信(多方提及) / 推测(趋势判断)

输出JSON（严格JSON，不要markdown）：
{
  "signals": [
    {
      "title": "信号标题",
      "summary": "信号描述(60字)",
      "heatScore": 8,
      "payScore": 7,
      "advantageScore": 6,
      "totalScore": 7.1,
      "recommendOSCAR": true,
      "suggestedReport": "建议付费报告标题",
      "evidence": "确凿/可信/推测",
      "sourceUrl": "模拟来源URL"
    }
  ]
}`;

      const raw = await callAI(prompt, 0.8);
      const data = await extractJSON(raw);

      if (data.signals && Array.isArray(data.signals)) {
        for (const s of data.signals) {
          signals.push({
            id: `sig-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
            date: new Date().toISOString(),
            departmentId: deptId,
            departmentName: deptName,
            source: { name: source.name, url: "#", type: "新闻" },
            title: s.title ?? "未命名信号",
            summary: s.summary ?? "",
            heatScore: s.heatScore ?? 5,
            payScore: s.payScore ?? 5,
            advantageScore: s.advantageScore ?? 5,
            totalScore: s.totalScore ?? 5,
            recommendOSCAR: s.recommendOSCAR ?? false,
            suggestedReport: s.suggestedReport ?? `${deptName}专题报告`,
            evidence: s.evidence ?? "推测",
            sourceUrl: s.sourceUrl ?? "#",
          });
        }
      }
    } catch (err) {
      console.error(`Signal scan failed for ${deptName}/${source.name}:`, err);
    }
  }

  return signals;
}

// ============================================================
// 全部门扫描入口
// ============================================================

export async function scanAllDepartments(): Promise<{
  signals: OpportunitySignal[];
  hotSignals: OpportunitySignal[];  // totalScore ≥ 7
  summary: string;
}> {
  const allSignals: OpportunitySignal[] = [];

  for (const dept of departments) {
    const signals = await scanSources(dept.id, dept.name);
    allSignals.push(...signals);
  }

  const hotSignals = allSignals.filter((s) => s.recommendOSCAR);
  
  const summaryPrompt = `请汇总以下${allSignals.length}条商业信号，生成一份200字的今日机会简报。

信号列表：
${allSignals.map((s) => `- [${s.departmentName}] ${s.title} (评分${s.totalScore})`).join("\n")}

简报格式：今日最值得关注的领域 + 热门信号TOP3 + 各阿米巴行动建议`;

  let summary = "";
  try {
    summary = await callAI(summaryPrompt, 0.6);
  } catch {
    summary = `今日扫描到${allSignals.length}条信号，其中${hotSignals.length}条推荐进入OSCAR调研。`;
  }

  return { signals: allSignals, hotSignals, summary };
}
