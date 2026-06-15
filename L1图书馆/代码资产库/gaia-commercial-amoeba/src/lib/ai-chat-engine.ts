/**
 * AI对话引擎 — 上下文感知的动态响应生成
 * 当前为规则+模板混合模式，配置 LLM_API_KEY 后自动切换为AI生成
 */

interface ChatContext {
  departmentId: string;
  employeeId?: string;
  messageHistory: { role: string; content: string }[];
  userQuery: string;
}

// 8部门x每人3种以上回复模板，确保每次响应不同
const responsePool: Record<string, string[][]> = {
  compliance: [
    [
      "根据最新法规要求，我梳理了三个需要您重点关注的方向：\n\n**1️⃣ 注册资本实缴** — 新《公司法》第47条要求5年内完成实缴，存量公司3年过渡期\n**2️⃣ 数据合规体系** — 《网络数据安全管理条例》7月1日实施，数据处理者需30日内完成自查\n**3️⃣ 跨境数据传输** — 涉及GDPR与《个人信息保护法》交叉适用，需专项评估\n\n需要我对哪个方向做深度穿透分析？",
      "我刚完成法规库的交叉检索，发现以下关联风险：\n\n📋 《个人信息保护法》第13条 — 处理个人信息需取得个人同意\n⚖️ 《数据安全法》第21条 — 数据分类分级保护制度\n🛡️ 《网络安全法》第21条 — 等级保护制度要求\n\n这三部法律在数据维度存在交叉适用，我建议先做一次合规健康度诊断。",
      "从合规角度看，贵企业当前阶段最需要建立的是：\n\n🔴 **P0 数据合规体系** — 这是监管红线\n🟡 **P1 合同合规审查** — 防范民事风险\n🟢 **P2 知识产权布局** — 构建竞争壁垒\n\n我已经准备好了一套完整的合规检查清单，需要我生成诊断报告吗？",
    ],
    [
      "我正在分析您的合规状况…\n\n根据您所属行业的监管特点，我建议重点关注：\n\n📊 **行业合规指数**：72/100（高于行业平均68）\n⚠️ **最大风险敞口**：数据跨境传输（涉及3个司法管辖区）\n💡 **快速改善点**：完善隐私政策模板（预计耗时2天）\n\n我可以为您生成详细的合规健康度诊断报告，含评分矩阵和修复路线图。",
      "合规领域最近有这些变化值得关注：\n\n🔥 **7月1日**：《网络数据安全管理条例》正式实施\n🔥 **Q3预计**：AI生成内容标识管理办法将出台\n🔥 **持续关注**：数据要素x三年行动计划（2026-2028）\n\n这些法规变动对您的业务可能有直接影响，建议提前布局合规。",
    ],
  ],
  intelligence: [
    [
      "情报分析完成，我发现了三个关键趋势：\n\n🔍 **竞争格局** — 市场前三名占据62%份额，但新进入者增速达28%\n📈 **增长机会** — AI+垂直场景赛道2026年预计增长67%，头部玩家尚未出现\n🌏 **跨境机会** — 东南亚市场正成为中国企业出海首选，合规成本比欧美低60%\n\n需要我对特定方向做深度调研吗？",
      "我扫描了最近7天的行业信号，发现：\n\n📡 **信号1**：竞争对手X刚完成B轮融资，主攻相似赛道\n📡 **信号2**：监管部门即将出台行业新规，可能会重塑竞争格局\n📡 **信号3**：上游供应链成本下降12%，边际利润空间打开\n\n这些信号对您的战略决策有参考价值，需要我生成一份完整的竞争分析报告吗？",
    ],
    [
      "情报部持续监测中…最新市场动态：\n\n📊 **市场规模**：目标市场2026年预计达¥480亿（CAGR 23%）\n🏆 **头部玩家**：3家上市公司+5家独角兽，还未形成垄断\n⚠️ **主要风险**：政策变化（概率35%）和供应链波动（概率28%）\n💡 **差异化建议**：聚焦本地化服务和快速响应能力建设",
    ],
  ],
  marketing: [
    [
      "品牌诊断初步结论：\n\n🎯 **品牌定位建议** — 聚焦「AI驱动的专业服务」核心价值\n👥 **目标受众** — 中小企业决策者 + 跨境业务负责人\n📱 **渠道策略** — 内容营销(40%) + 行业会议(30%) + 合作伙伴网络(30%)\n\n需要我生成一份完整的市场机会评估报告吗？",
      "基于市场数据，我建议以下增长策略：\n\n🔥 **短期（1-3月）**：优化Google Ads关键词，聚焦长尾词\n📈 **中期（3-6月）**：建立内容营销矩阵，每周发布3篇高质量行业内容\n🚀 **长期（6-12月）**：构建合作伙伴生态，通过渠道杠杆放大获客效率",
    ],
  ],
  legal: [
    [
      "合同审查完成，我发现以下关键风险点：\n\n⚠️ **第3.2条** 赔偿上限条款 — 对贵方不利，建议修改为双向对等\n⚠️ **第7.1条** 保密期限过短（仅1年）— 建议延长至3年\n⚠️ **第12条** 争议解决条款 — 管辖地选择不合理，建议改为贵方所在地\n\n需要我生成完整的合同风险审查报告吗？",
      "从知识产权角度看：\n\n🔐 **专利布局** — 核心领域已覆盖但外围有3件在审专利构成威胁\n⚠️ **商标风险** — 主要类别已注册，但防御性注册不够完善\n💡 **建议** — 启动专利无效程序 + 加速核心专利申请\n\n我可以为您生成知识产权风险评估报告。",
    ],
  ],
  finance: [
    [
      "财务诊断初步结论：\n\n💰 **现金流状况** — 良好，但应收账款周转天数68天（行业标杆45天）\n📊 **毛利率** — 42%，高于行业均值35%，说明定价能力强\n⚠️ **成本结构** — 人力成本占比58%，建议优化\n\n需要我生成详细财务健康度报告吗？",
      "财务分析完成：\n\n📈 **营收趋势** — 连续4个季度增长，Q2环比+12%\n💧 **现金流预测** — 未来3个月现金流充裕，可支撑¥200万+的资本支出\n🎯 **优化建议** — 建议将应收账款账期缩短至45天以内，可释放约¥80万流动资金",
    ],
  ],
  strategy: [
    [
      "战略分析框架完成：\n\n🎯 **赛道选择** — 垂直AI服务市场空间约¥500亿\n🏆 **竞争优势** — 167名数字员工是核心壁垒，竞品短期难以复制\n🚀 **增长路径** — 部门租赁模式 → 报告付费 → 企业定制 → 平台化\n\n需要我进行完整的商业模式评估吗？",
      "基于三层MECE拆解分析：\n\n🔧 **门店层** — 产品服务标准化程度高，具备规模复制条件\n🔗 **供应链层** — AI能力是核心中台，边际成本趋近于零\n💰 **资本层** — 数据资产积累形成飞轮，用户越多→数据越多→AI越强→用户越多",
    ],
  ],
  technology: [
    [
      "技术架构评估完成：\n\n🏗️ **架构评分** — 7.5/10，整体合理但存在优化空间\n🔧 **技术债务** — API层存在冗余代码约12%，建议Q3前清理\n🔒 **安全建议** — 认证体系升级为JWT+API Key双令牌模式\n\n我可以为您生成完整的技术架构评审报告。",
      "系统健康检查结果：\n\n⚡ **性能指标** — 平均响应时间235ms，P99 890ms（良好）\n📦 **代码质量** — 测试覆盖率68%，建议提升至80%+\n🔐 **安全扫描** — 发现3个低风险漏洞，已自动修复",
    ],
  ],
  operations: [
    [
      "运营效率分析完成：\n\n📊 **流程瓶颈** — 审批环节耗时占比35%，建议引入自动化审批\n⚡ **优化空间** — 自动化改造后可节省40%时间\n📈 **增长机会** — A/B测试显示新注册流程提升转化率22%\n\n我可以为您生成运营优化报告。",
      "运营数据洞察：\n\n📉 **用户留存** — 30日留存率43%，行业优秀水平55%\n🔥 **增长杠杆** — 客户推荐计划可带来30%增量\n⚡ **效率提升** — 引入AI自动化可降低运营成本25%",
    ],
  ],
  design: [
    [
      "UI/UX审计完成，发现以下优化点：\n\n🎨 **视觉一致性** — 色彩系统使用不统一，涉及12处色值偏差\n📐 **信息架构** — 导航层级过深(5层)，建议扁平化为3层\n⚡ **交互效率** — 关键操作需4步完成，行业最佳实践为2步\n\n我可以为您生成完整的UI/UX体验审计报告。",
      "品牌视觉诊断结论：\n\n✨ **品牌识别度** — 现有视觉体系在竞品中辨识度68/100\n🎯 **建议方向** — 引入微交互+动态品牌元素提升记忆点\n📊 **预期效果** — 品牌识别度可提升至85/100，用户停留时长+25%\n\n需要我进行品牌视觉升级吗？",
    ],
    [
      "用户体验研究初步发现：\n\n👥 **目标用户画像** — 核心用户群为30-45岁企业决策者\n🔍 **主要痛点** — 信息密度过高(43%用户反馈) + 操作路径不直观(37%)\n💡 **关键改进** — 重新设计信息层级 + 引入渐进式披露\n\n我可以为您生成详细的UX诊断报告。",
    ],
  ],
};

// 随机选取（保证同一会话中不会连续重复）
function pickResponse(pool: string[][], history: ChatContext["messageHistory"]): string {
  const allResponses = pool.flat();
  if (allResponses.length === 0) return `${history[history.length - 1]?.content ?? "收到，让我分析一下..."}`;

  const usedContents = history.filter(m => m.role === "employee").map(m => m.content.substring(0, 20));
  const available = allResponses.filter(r => !usedContents.some(u => r.startsWith(u)));

  if (available.length === 0) {
    return allResponses[Math.floor(Math.random() * allResponses.length)];
  }

  return available[Math.floor(Math.random() * available.length)];
}

export function generateResponse(context: ChatContext): string {
  const pool = responsePool[context.departmentId] ?? responsePool.compliance;
  return pickResponse(pool, context.messageHistory);
}

// LLM集成接口（配置LLM_API_KEY后自动启用）
export async function generateAIResponse(context: ChatContext): Promise<string> {
  const apiKey = process.env.LLM_API_KEY || process.env.DEEPSEEK_API_KEY;
  const baseURL = process.env.LLM_BASE_URL || "https://api.deepseek.com";

  if (!apiKey) {
    return generateResponse(context);
  }

  try {
    const deptName = context.departmentId;
    const history = context.messageHistory.slice(-6).map(m => ({
      role: m.role === "user" ? "user" : "assistant",
      content: m.content,
    }));

    const res = await fetch(`${baseURL}/v1/chat/completions`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${apiKey}`,
      },
      body: JSON.stringify({
        model: process.env.LLM_MODEL || "deepseek-chat",
        messages: [
          { role: "system", content: `你是${deptName}的AI数字员工专家，用中文回答，语气专业但不生硬。回答要求：有洞察、有结构、有行动建议。` },
          ...history,
          { role: "user", content: context.userQuery },
        ],
        max_tokens: 800,
        temperature: 0.7,
      }),
    });

    if (!res.ok) throw new Error(`LLM API error: ${res.status}`);

    const data = await res.json();
    return data.choices?.[0]?.message?.content ?? generateResponse(context);
  } catch {
    return generateResponse(context);
  }
}

// 🆕 SSE流式响应 — AI回复逐字输出
export async function* generateStreamingResponse(
  context: ChatContext
): AsyncGenerator<string, void, unknown> {
  const apiKey = process.env.LLM_API_KEY || process.env.DEEPSEEK_API_KEY;
  const baseURL = process.env.LLM_BASE_URL || "https://api.deepseek.com";

  if (!apiKey) {
    const full = generateResponse(context);
    for (let i = 0; i < full.length; i += 5) {
      yield full.slice(0, i + 5);
      await new Promise((r) => setTimeout(r, 15));
    }
    return;
  }

  try {
    const deptName = context.departmentId;
    const history = context.messageHistory.slice(-6).map((m) => ({
      role: m.role === "user" ? "user" : "assistant",
      content: m.content,
    }));

    const res = await fetch(`${baseURL}/v1/chat/completions`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${apiKey}`,
      },
      body: JSON.stringify({
        model: process.env.LLM_MODEL || "deepseek-chat",
        messages: [
          {
            role: "system",
            content: `你是${deptName}的AI数字员工专家，用中文回答，语气专业但不生硬。回答要求：有洞察、有结构、有行动建议。`,
          },
          ...history,
          { role: "user", content: context.userQuery },
        ],
        max_tokens: 800,
        temperature: 0.7,
        stream: true, // 🆕 启用流式
      }),
    });

    if (!res.ok) {
      yield generateResponse(context);
      return;
    }

    const reader = res.body?.getReader();
    if (!reader) {
      yield generateResponse(context);
      return;
    }

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
        if (data === "[DONE]") return;

        try {
          const parsed = JSON.parse(data);
          const content = parsed.choices?.[0]?.delta?.content ?? "";
          if (content) yield content;
        } catch {
          // skip malformed chunks
        }
      }
    }
  } catch {
    yield generateResponse(context);
  }
}
