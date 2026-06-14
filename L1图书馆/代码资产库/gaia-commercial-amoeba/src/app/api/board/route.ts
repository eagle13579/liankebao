import { NextRequest, NextResponse } from "next/server";

async function generateTopics() {
  const apiKey = process.env.LLM_API_KEY;
  if (!apiKey) {
    return { topics: [] };
  }

  const prompt = `你是一个行业情报分析师，请生成4条关于中国企业合规/商业/法律/技术的最新热门讨论话题。

要求：
- 每条话题包含：标题(15字内)、内容(80-120字)、所属部门(compliance/intelligence/marketing/legal/finance/strategy/technology/operations之一)、2个标签
- 话题必须是2026年6月真实可能发生的商业事件
- 输出JSON格式，不要markdown包裹

输出格式：
{
  "topics": [
    {
      "title": "...",
      "content": "...",
      "departmentId": "compliance",
      "tags": ["tag1", "tag2"]
    }
  ]
}`;

  try {
    const res = await fetch("https://api.deepseek.com/v1/chat/completions", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${apiKey}`,
      },
      body: JSON.stringify({
        model: "deepseek-chat",
        messages: [{ role: "user", content: prompt }],
        max_tokens: 2000,
        temperature: 0.8,
      }),
    });

    if (!res.ok) throw new Error(`API error: ${res.status}`);
    const data = await res.json();
    const text = data.choices?.[0]?.message?.content ?? "";

    const jsonMatch = text.match(/\{[\s\S]*\}/);
    if (!jsonMatch) throw new Error("No JSON in response");

    return JSON.parse(jsonMatch[0]);
  } catch (err) {
    console.error("Topic generation failed:", err);
    return { topics: [] };
  }
}

const fallbackTopics = [
  { title: "新公司法注册资本5年实缴", content: "有限责任公司股东出资期限不得超过5年，存量公司3年内调整。合规部已整理完整应对方案。", departmentId: "compliance", tags: ["法规更新", "合规"] },
  { title: "跨境电商出口退税政策利好", content: "跨境电商综合试验区出口退税流程简化，退税周期从30天缩短至7天。建议抓住政策红利。", departmentId: "intelligence", tags: ["政策", "跨境电商"] },
  { title: "AI生成内容标识管理办法", content: "网信办要求所有AIGC内容必须添加显著标识，违规最高罚款100万。", departmentId: "legal", tags: ["AI监管", "法规"] },
  { title: "Q2 SaaS行业投融资趋势", content: "2026 Q2 SaaS融资同比下降23%，但AI+SaaS赛道逆势增长67%。", departmentId: "strategy", tags: ["行业趋势", "融资"] },
];

export async function GET(request: NextRequest) {
  const deptId = request.nextUrl.searchParams.get("department");
  const force = request.nextUrl.searchParams.get("force") === "true";

  if (force) {
    const aiTopics = await generateTopics();
    const topics = aiTopics.topics.length >= 3 ? aiTopics.topics : fallbackTopics;

    if (deptId) {
      return NextResponse.json({ topics: topics.filter(t => t.departmentId === deptId) });
    }
    return NextResponse.json({ topics });
  }

  const filtered = deptId
    ? fallbackTopics.filter(t => t.departmentId === deptId)
    : fallbackTopics;

  return NextResponse.json({ topics: filtered });
}
