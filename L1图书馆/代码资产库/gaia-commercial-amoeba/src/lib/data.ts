/**
 * AI数字员工工作台 — 数据层
 * 部门/员工/报告数据结构定义 + Mock数据
 * 生产环境时替换为memory.db读取
 */

// ============================================================
// 类型定义
// ============================================================

export interface Employee {
  id: string;
  name: string;
  title: string;
  department: string;
  avatar: string; // emoji
  status: "working" | "idle" | "standby";
  specialty: string[];
  soul: string; // 灵魂描述
}

export interface Department {
  id: string;
  name: string;
  icon: string;
  description: string;
  employeeCount: number;
  tier: "free" | "standard" | "premium";
}

export interface Message {
  id: string;
  role: "user" | "employee";
  employeeId?: string;
  content: string;
  timestamp: string;
}

export interface ReportTemplate {
  id: string;
  title: string;
  description: string;
  price: number;
  departmentId: string;
}

export interface Report {
  id: string;
  templateId: string;
  title: string;
  departmentId: string;
  preview: string;
  fullContent?: string;
  price: number;
  locked: boolean;
  createdAt: string;
}

export interface BoardTopic {
  id: string;
  title: string;
  content: string;
  author: string;
  departmentId: string;
  createdAt: string;
  tags: string[];
}

// ============================================================
// Mock 部门数据（对应记忆宫殿167员工组织架构）
// ============================================================

export const departments: Department[] = [
  {
    id: "compliance",
    name: "合规部",
    icon: "🛡️",
    description: "法规穿透 · 合规诊断 · 风险预警",
    employeeCount: 24,
    tier: "free",
  },
  {
    id: "intelligence",
    name: "情报部",
    icon: "🔍",
    description: "竞品分析 · 市场情报 · 趋势捕捉",
    employeeCount: 18,
    tier: "standard",
  },
  {
    id: "marketing",
    name: "市场部",
    icon: "📢",
    description: "品牌传播 · 内容营销 · 增长策略",
    employeeCount: 22,
    tier: "standard",
  },
  {
    id: "legal",
    name: "法务部",
    icon: "⚖️",
    description: "合同审查 · 知识产权 · 合规体系",
    employeeCount: 15,
    tier: "premium",
  },
  {
    id: "finance",
    name: "财务部",
    icon: "💰",
    description: "财税分析 · 成本优化 · 预算管理",
    employeeCount: 12,
    tier: "premium",
  },
  {
    id: "strategy",
    name: "战略部",
    icon: "🧠",
    description: "商业模式设计 · 赛道选择 · 资本运作",
    employeeCount: 10,
    tier: "premium",
  },
  {
    id: "technology",
    name: "技术部",
    icon: "⚙️",
    description: "架构设计 · 代码审查 · 技术创新",
    employeeCount: 28,
    tier: "standard",
  },
  {
    id: "design",
    name: "设计部",
    icon: "🎨",
    description: "UI设计 · 品牌视觉 · 交互体验",
    employeeCount: 4,
    tier: "standard",
  },
  {
    id: "operations",
    name: "运营部",
    icon: "📊",
    description: "流程优化 · 数据驱动 · 增长实验",
    employeeCount: 16,
    tier: "standard",
  },
];

// ============================================================
// Mock 员工数据（精选自167数字员工）
// ============================================================

export const employees: Employee[] = [
  // 合规部
  { id: "emp-xuzhun", name: "徐准", title: "合规总监", department: "compliance", avatar: "👨‍⚖️", status: "idle", specialty: ["法规穿透", "合规诊断", "风险预警"], soul: "铁面无私的合规守门人" },
  { id: "emp-zaihao", name: "宰贤", title: "知识产权专员", department: "compliance", avatar: "🧑‍💼", status: "idle", specialty: ["知识产权", "专利审查", "商标维权"], soul: "知识产权守护者" },
  { id: "emp-yiheng", name: "意恒", title: "合规工程师", department: "compliance", avatar: "👨‍🔬", status: "idle", specialty: ["法规解读", "合规审计", "风险量化"], soul: "合规科技的领航员" },
  // 情报部
  { id: "emp-shengxun", name: "晟勋", title: "情报总监", department: "intelligence", avatar: "🕵️", status: "idle", specialty: ["竞品分析", "市场情报", "趋势预判"], soul: "洞察先机的战略情报官" },
  { id: "emp-huizhen", name: "慧珍", title: "市场分析师", department: "intelligence", avatar: "👩‍💻", status: "idle", specialty: ["数据分析", "行业研究", "报告撰写"], soul: "数据背后的真相挖掘者" },
  { id: "emp-dongjian", name: "东健", title: "情报分析师", department: "intelligence", avatar: "🧑‍🔬", status: "idle", specialty: ["信息采集", "交叉验证", "模式识别"], soul: "信息海洋中的航海家" },
  // 市场部
  { id: "emp-jiuwei", name: "九尾狐", title: "公关总监", department: "marketing", avatar: "🦊", status: "idle", specialty: ["品牌传播", "媒体关系", "危机公关"], soul: "品牌塑造的艺术家" },
  { id: "emp-yingzhao", name: "英招", title: "市场总监", department: "marketing", avatar: "🦅", status: "idle", specialty: ["客户签约", "ROI优化", "渠道策略"], soul: "客户成功的驱动力" },
  { id: "emp-xiangliu", name: "相柳", title: "商务拓展总监", department: "marketing", avatar: "🐍", status: "idle", specialty: ["商务谈判", "合作伙伴", "生态建设"], soul: "连接万物的商务使者" },
  // 法务部
  { id: "emp-bi-an", name: "狴犴", title: "法务审查官", department: "legal", avatar: "🐯", status: "idle", specialty: ["合同审查", "缺陷发现", "质量门禁"], soul: "铁面无私的审查守护神" },
  { id: "emp-meiying", name: "美英", title: "签证移民律师", department: "legal", avatar: "👩‍⚖️", status: "idle", specialty: ["移民法", "签证合规", "跨法域协调"], soul: "跨境法律安全的灯塔" },
  // 财务部
  { id: "emp-jiran", name: "计然", title: "战略财务官", department: "finance", avatar: "🧮", status: "idle", specialty: ["财务建模", "成本分析", "投资评估"], soul: "数字背后的战略家" },
  // 战略部
  { id: "emp-shu-huan", name: "䑏疏", title: "战略总监", department: "strategy", avatar: "🦏", status: "idle", specialty: ["趋势捕捉", "商业分析", "赛道选择"], soul: "穿透迷雾的战略罗盘" },
  { id: "emp-chenghuang", name: "乘黄", title: "产品总监", department: "strategy", avatar: "🦄", status: "idle", specialty: ["用户痛点", "需求收敛", "产品设计"], soul: "让产品拥有灵魂的设计师" },
  // 技术部
  { id: "emp-zhulong", name: "烛龙", title: "首席架构师", department: "technology", avatar: "🐉", status: "idle", specialty: ["系统架构", "工程治理", "技术决策"], soul: "照亮技术迷雾的明灯" },
  { id: "emp-jinwu", name: "金乌", title: "前端架构师", department: "technology", avatar: "🦅", status: "idle", specialty: ["前端架构", "UI工程", "性能优化"], soul: "构建美丽界面的太阳鸟" },
  { id: "emp-wenyao", name: "文鳐", title: "技术文档工程师", department: "technology", avatar: "🐟", status: "idle", specialty: ["文档规范", "知识管理", "API设计"], soul: "让知识有序流动的守护者" },
  // 运营部
  { id: "emp-shangyang", name: "商羊", title: "运营总监", department: "operations", avatar: "🐏", status: "idle", specialty: ["流程优化", "数据驱动", "增长实验"], soul: "让系统自我进化的运营大脑" },
  { id: "emp-kunpeng", name: "鲲鹏", title: "增长架构师", department: "operations", avatar: "🐋", status: "idle", specialty: ["增长策略", "转化优化", "数据漏斗"], soul: "从数据到增长的桥梁" },
  // 设计部
  { id: "emp-tiangong", name: "天工", title: "首席设计师", department: "design", avatar: "🔧", status: "idle", specialty: ["设计系统", "品牌视觉", "创意方向"], soul: "巧夺天工的设计大师" },
  { id: "emp-danqing", name: "丹青", title: "UI/视觉设计师", department: "design", avatar: "🎨", status: "idle", specialty: ["UI设计", "视觉系统", "插画"], soul: "用色彩和形状讲述故事" },
  { id: "emp-ziqi", name: "子期", title: "UX研究员", department: "design", avatar: "🔍", status: "idle", specialty: ["用户研究", "可用性测试", "信息架构"], soul: "听懂用户未说出口的需求" },
  { id: "emp-luban", name: "鲁班", title: "交互设计师", department: "design", avatar: "🛠️", status: "idle", specialty: ["交互设计", "原型设计", "动效设计"], soul: "让每一像素都有灵魂" },
];

// ============================================================
// Helper: 按部门获取员工
// ============================================================

export function getEmployeesByDepartment(deptId: string): Employee[] {
  return employees.filter((e) => e.department === deptId);
}

export function getDepartment(deptId: string): Department | undefined {
  return departments.find((d) => d.id === deptId);
}

export function getEmployee(id: string): Employee | undefined {
  return employees.find((e) => e.id === id);
}

// ============================================================
// 报告模板数据
// ============================================================

export const reportTemplates: ReportTemplate[] = [
  { id: "rpt-compliance-1", title: "合规健康度诊断报告", description: "全面评估企业合规体系，识别风险敞口并提供修复路径", price: 500, departmentId: "compliance" },
  { id: "rpt-intel-1", title: "竞品深度分析报告", description: "多维度竞品解剖，含产品/定价/渠道/营销策略", price: 800, departmentId: "intelligence" },
  { id: "rpt-market-1", title: "市场机会评估报告", description: "市场规模·竞争格局·进入策略一站式分析", price: 600, departmentId: "marketing" },
  { id: "rpt-legal-1", title: "合同风险审查报告", description: "合同条款逐条审查，识别隐藏风险并提出修改建议", price: 500, departmentId: "legal" },
  { id: "rpt-finance-1", title: "财务健康度诊断", description: "财务报表分析·现金流评估·成本优化建议", price: 700, departmentId: "finance" },
  { id: "rpt-strategy-1", title: "商业模式评估报告", description: "三层MECE拆解·资本套利识别·增长飞轮设计", price: 1000, departmentId: "strategy" },
  { id: "rpt-tech-1", title: "技术架构评审报告", description: "系统架构·技术债务·安全风险全面诊断", price: 600, departmentId: "technology" },
  { id: "rpt-ops-1", title: "运营效率优化报告", description: "流程瓶颈·数据漏斗·增长实验设计", price: 500, departmentId: "operations" },
  { id: "rpt-design-1", title: "UI/UX体验审计报告", description: "界面设计·交互流程·品牌一致性·可访问性全面评估", price: 600, departmentId: "design" },
];

// ============================================================
// 公告板话题
// ============================================================

export const boardTopics: BoardTopic[] = [
  {
    id: "topic-1",
    title: "新《公司法》注册资本5年实缴解读",
    content: "2026年7月1日起，有限责任公司股东出资期限不得超过5年。现有公司需在3年内逐步调整。合规部已整理完整应对方案。",
    author: "徐准",
    departmentId: "compliance",
    createdAt: "2026-06-14T08:00:00Z",
    tags: ["法规更新", "合规"],
  },
  {
    id: "topic-2",
    title: "跨境电商出口退税政策最新调整",
    content: "财政部新规：跨境电商综合试验区出口退税流程简化，退税周期从30天缩短至7天。市场部建议抓住政策红利。",
    author: "慧珍",
    departmentId: "intelligence",
    createdAt: "2026-06-13T10:30:00Z",
    tags: ["政策", "跨境电商"],
  },
  {
    id: "topic-3",
    title: "AI生成内容标识管理办法征求意见",
    content: "网信办发布《人工智能生成内容标识管理办法》，要求所有AIGC内容必须添加显著标识，违规最高罚款100万。",
    author: "狴犴",
    departmentId: "legal",
    createdAt: "2026-06-12T14:00:00Z",
    tags: ["AI监管", "法规"],
  },
  {
    id: "topic-4",
    title: "Q2 SaaS行业投融资趋势报告",
    content: "2026 Q2 SaaS行业融资总额同比下降23%，但AI+SaaS赛道逆势增长67%。投资人关注垂直场景的AI应用落地能力。",
    author: "䑏疏",
    departmentId: "strategy",
    createdAt: "2026-06-11T09:00:00Z",
    tags: ["行业趋势", "融资"],
  },
];

// ============================================================
// 报告生成模拟
// ============================================================

// ============================================================
// 意图推荐位（每个部门3个快捷问题）
// ============================================================

export interface IntentSuggestion {
  id: string;
  text: string;
  icon: string;
  departmentId: string;
}

export const intentSuggestions: IntentSuggestion[] = [
  // 合规部
  { id: "int-comp-1", text: "最新法规变更对我有什么影响？", icon: "📋", departmentId: "compliance" },
  { id: "int-comp-2", text: "帮我做一次合规健康度检查", icon: "🔍", departmentId: "compliance" },
  { id: "int-comp-3", text: "数据合规需要注意什么？", icon: "🔒", departmentId: "compliance" },
  // 情报部
  { id: "int-intel-1", text: "我的竞品最近有什么动作？", icon: "🕵️", departmentId: "intelligence" },
  { id: "int-intel-2", text: "分析一下这个市场趋势", icon: "📈", departmentId: "intelligence" },
  { id: "int-intel-3", text: "帮我搜集行业最新动态", icon: "📡", departmentId: "intelligence" },
  // 市场部
  { id: "int-mkt-1", text: "帮我优化品牌定位", icon: "🎯", departmentId: "marketing" },
  { id: "int-mkt-2", text: "设计一个营销增长策略", icon: "🚀", departmentId: "marketing" },
  { id: "int-mkt-3", text: "分析我的目标受众画像", icon: "👥", departmentId: "marketing" },
  // 法务部
  { id: "int-legal-1", text: "审查这份合同的风险点", icon: "⚖️", departmentId: "legal" },
  { id: "int-legal-2", text: "知识产权保护方案建议", icon: "🔐", departmentId: "legal" },
  { id: "int-legal-3", text: "我需要做哪些合规备案？", icon: "📝", departmentId: "legal" },
  // 财务部
  { id: "int-fin-1", text: "分析我的财务报表", icon: "💰", departmentId: "finance" },
  { id: "int-fin-2", text: "成本优化建议有哪些？", icon: "✂️", departmentId: "finance" },
  { id: "int-fin-3", text: "现金流管理怎么做？", icon: "💧", departmentId: "finance" },
  // 战略部
  { id: "int-strat-1", text: "评估我的商业模式", icon: "🧠", departmentId: "strategy" },
  { id: "int-strat-2", text: "下一步该选什么赛道？", icon: "🎯", departmentId: "strategy" },
  { id: "int-strat-3", text: "资本运作有什么机会？", icon: "🏦", departmentId: "strategy" },
  // 技术部
  { id: "int-tech-1", text: "帮我做技术架构评审", icon: "🏗️", departmentId: "technology" },
  { id: "int-tech-2", text: "技术债务怎么清理？", icon: "🧹", departmentId: "technology" },
  { id: "int-tech-3", text: "安全合规方面有哪些风险？", icon: "🔒", departmentId: "technology" },
  // 运营部
  { id: "int-ops-1", text: "运营效率如何提升？", icon: "⚡", departmentId: "operations" },
  { id: "int-ops-2", text: "帮我做增长实验设计", icon: "🧪", departmentId: "operations" },
  { id: "int-ops-3", text: "数据漏斗分析怎么做？", icon: "📊", departmentId: "operations" },
  // 设计部
  { id: "int-des-1", text: "帮我审计现有UI设计", icon: "🎨", departmentId: "design" },
  { id: "int-des-2", text: "品牌视觉升级建议", icon: "✨", departmentId: "design" },
  { id: "int-des-3", text: "用户体验诊断怎么做？", icon: "🔍", departmentId: "design" },
];

export function getIntentSuggestions(deptId: string): IntentSuggestion[] {
  return intentSuggestions.filter((s) => s.departmentId === deptId).slice(0, 3);
}

// ============================================================
// 会员体系
// ============================================================

export interface MembershipTier {
  id: string;
  name: string;
  price: number;
  period: "month" | "year";
  departments: number; // 最大部门数量
  reportsPerMonth: number; // 每月报告份数（-1=无限）
  features: string[];
  highlighted?: boolean;
}

export const membershipTiers: MembershipTier[] = [
  {
    id: "free",
    name: "免费体验",
    price: 0,
    period: "month",
    departments: 1,
    reportsPerMonth: 2,
    features: ["1个部门体验", "2份报告/月", "基础对话", "社区支持"],
  },
  {
    id: "standard",
    name: "标准版",
    price: 299,
    period: "month",
    departments: 1,
    reportsPerMonth: 5,
    features: ["1个部门全员工", "5份报告/月", "优先响应", "报告PDF下载"],
    highlighted: true,
  },
  {
    id: "professional",
    name: "专业版",
    price: 499,
    period: "month",
    departments: 3,
    reportsPerMonth: -1,
    features: ["3个部门并发", "无限报告", "专属客户经理", "API访问", "高级分析"],
  },
  {
    id: "enterprise",
    name: "企业版",
    price: 1999,
    period: "month",
    departments: 99,
    reportsPerMonth: -1,
    features: ["全部部门", "私有化部署", "SLA保障", "定制开发", "专属支持"],
  },
];

export function getDepartmentAccess(departmentId: string, userTier: string): boolean {
  if (userTier === "enterprise" || userTier === "professional") return true;
  if (userTier === "standard") {
    const freeDepts = ["compliance", "design"]; // 标准版可解锁合规部+设计部
    return freeDepts.includes(departmentId);
  }
  // 免费版
  return departmentId === "compliance";
}

export function getReportsRemaining(userTier: string, usedReports: number): number {
  const tier = membershipTiers.find((t) => t.id === userTier);
  if (!tier) return 0;
  if (tier.reportsPerMonth === -1) return 99; // 无限
  return Math.max(0, tier.reportsPerMonth - usedReports);
}

export function generateReportPreview(templateId: string, departmentId: string): Report {
  const template = reportTemplates.find((t) => t.id === templateId);
  return {
    id: `report-${Date.now()}`,
    templateId,
    title: template?.title ?? "专业分析报告",
    departmentId,
    preview: `本报告基于您提供的信息，结合${getDepartment(departmentId)?.name ?? "专业"}团队的分析框架，从${8}个维度进行全面评估。报告共${12}页，含${5}张数据图表和${3}条可执行建议。`,
    fullContent: undefined,
    price: template?.price ?? 500,
    locked: true,
    createdAt: new Date().toISOString(),
  };
}
