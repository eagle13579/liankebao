/**
 * 链客宝 - 对话式智能匹配搜索组件
 * 自然语言输入 → 结构化需求解构 + API搜索
 * 规则：纯新增，不修改现有业务逻辑
 */

import React, { useState, useCallback, useEffect, useRef } from 'react';

// ─── 类型定义 ───────────────────────────────────────────────

export interface NLSearchResult {
  industry: string;
  companySize: string;
  region: string;
  category: string;
  description: string;
}

export interface NLSearchApiItem {
  id: number;
  title: string;
  company: string;
  position: string;
  description: string;
  tags: string[];
  match_score: number;
  match_reasons: string[];
}

interface ExtractedTag {
  key: keyof NLSearchResult;
  label: string;
  value: string;
  color: string;
}

interface Props {
  /** 搜索回调 — 输出结构化需求 */
  onSearch?: (result: NLSearchResult) => void;
  /** 结果选中回调 */
  onResultSelect?: (item: NLSearchApiItem) => void;
  /** 紧凑模式 */
  compact?: boolean;
}

// ─── 示例查询 ───────────────────────────────────────────────

const EXAMPLE_QUERIES = [
  '找规模200人以上的制造业供应商',
  '需要跨境电商物流服务商',
  '寻找华东地区的科技公司合作伙伴',
  '需要300人以上医疗行业的渠道商',
  '找华南地区做跨境电商的供应商',
];

// ─── 标签配色方案 ──────────────────────────────────────────

const TAG_STYLE: Record<keyof NLSearchResult, { color: string; bg: string; border: string; label: string }> = {
  industry:    { color: '#7C3AED', bg: '#F5F3FF', border: '#DDD6FE', label: '行业' },
  companySize: { color: '#0891B2', bg: '#ECFEFF', border: '#A5F3FC', label: '规模' },
  region:      { color: '#059669', bg: '#ECFDF5', border: '#A7F3D0', label: '地区' },
  category:    { color: '#D97706', bg: '#FFFBEB', border: '#FDE68A', label: '品类' },
};

// ─── API 基础路径 ──────────────────────────────────────────

const API_BASE = '';

// ─── 本地解构引擎 ───────────────────────────────────────────

/**
 * 基于规则的自然语言需求解构
 * 从中文描述中提取：行业、公司规模、地区、品类
 */
function deconstructQuery(text: string): NLSearchResult {
  const trimmed = text.trim();

  // --- 行业提取 ---
  const INDUSTRY_PATTERNS: [RegExp, string][] = [
    /(?:制造业|工业|制造)/,           '制造业',
    /(?:跨境电商|跨境|出口电商)/,     '跨境电商',
    /(?:电商|电子商务|线上零售)/,     '电子商务',
    /(?:物流|供应链|货运|仓储)/,      '物流',
    /(?:科技|互联网|IT|软件|信息)/,   '科技',
    /(?:金融|保险|证券|银行|投资)/,   '金融',
    /(?:教育|培训|在线教育|教培)/,    '教育',
    /(?:医疗|医药|健康|生物|器械)/,   '医疗',
    /(?:房地产|地产|物业|楼盘)/,      '房地产',
    /(?:餐饮|食品|外卖|餐饮连锁)/,    '餐饮',
    /(?:零售|便利店|商超|百货)/,      '零售',
    /(?:汽车|新能源车|汽配)/,         '汽车',
    /(?:旅游|酒店|民宿|出行)/,        '旅游',
    /(?:农业|农产品|农资)/,           '农业',
    /(?:能源|新能源|光伏|电力)/,      '能源',
    /(?:建筑|建材|装修|工程)/,        '建筑',
    /(?:传媒|广告|营销|公关|文化)/,   '传媒',
    /(?:法律|律师|法务)/,             '法律',
    /(?:咨询|顾问|管理咨询)/,         '咨询',
    /(?:人力资源|HR|招聘)/,           '人力资源',
  ];

  let industry = '';
  for (const [pattern, value] of INDUSTRY_PATTERNS) {
    if (pattern.test(trimmed)) {
      industry = value;
      break;
    }
  }

  // --- 公司规模提取 ---
  const sizeMatch = trimmed.match(/(?:规模|人数|团队|员工)?\s*(\d+)\s*(?:[~-到至]?\s*(\d+))?\s*(?:人|名|位)/);
  let companySize = '';
  if (sizeMatch) {
    const min = parseInt(sizeMatch[1]);
    const max = sizeMatch[2] ? parseInt(sizeMatch[2]) : null;
    if (max) {
      companySize = `${min}-${max}人`;
    } else {
      if (/以上/.test(trimmed.slice(0, sizeMatch.index! + sizeMatch[0].length))) {
        companySize = `${min}人以上`;
      } else if (/以下/.test(trimmed.slice(0, sizeMatch.index! + sizeMatch[0].length))) {
        companySize = `${min}人以下`;
      } else if (/中小|微型/.test(trimmed)) {
        companySize = '中小型';
      } else if (/大型/.test(trimmed)) {
        companySize = '大型';
      } else {
        companySize = `${min}人`;
      }
    }
  } else if (/中小型|中小微/.test(trimmed)) {
    companySize = '中小型';
  }

  // --- 地区提取 ---
  const REGION_PATTERNS: [RegExp, string][] = [
    /华东/,                    '华东地区',
    /华南/,                    '华南地区',
    /华北/,                    '华北地区',
    /华中/,                    '华中地区',
    /西南/,                    '西南地区',
    /西北/,                    '西北地区',
    /东北/,                    '东北地区',
    /长三角/,                  '长三角地区',
    /珠三角/,                  '珠三角地区',
    /京津冀/,                  '京津冀地区',
    /上海/,                    '上海',
    /北京/,                    '北京',
    /深圳/,                    '深圳',
    /广州/,                    '广州',
    /杭州/,                    '杭州',
    /成都/,                    '成都',
    /武汉/,                    '武汉',
    /南京/,                    '南京',
    /重庆/,                    '重庆',
    /苏州/,                    '苏州',
    /天津/,                    '天津',
    /长沙/,                    '长沙',
    /郑州/,                    '郑州',
    /西安/,                    '西安',
    /东莞/,                    '东莞',
    /青岛/,                    '青岛',
    /厦门/,                    '厦门',
    /宁波/,                    '宁波',
    /大连/,                    '大连',
    /合肥/,                    '合肥',
    /佛山/,                    '佛山',
    /福州/,                    '福州',
    /昆明/,                    '昆明',
    /沈阳/,                    '沈阳',
    /济南/,                    '济南',
    /无锡/,                    '无锡',
    /珠海/,                    '珠海',
    /海口/,                    '海口',
    /贵阳/,                    '贵阳',
    /南宁/,                    '南宁',
    /哈尔滨/,                  '哈尔滨',
    /长春/,                    '长春',
    /石家庄/,                  '石家庄',
    /太原/,                    '太原',
    /南昌/,                    '南昌',
    /兰州/,                    '兰州',
    /省内|全省/,               '本省',
    /国内|全国/,               '全国',
    /海外|国外|跨境/,          '海外',
  ];

  let region = '';
  for (const [pattern, value] of REGION_PATTERNS) {
    if (pattern.test(trimmed)) {
      region = value;
      break;
    }
  }

  // --- 品类提取 ---
  const CATEGORY_PATTERNS: [RegExp, string][] = [
    /供应商/,         '供应商',
    /服务商/,         '服务商',
    /渠道商/,         '渠道商',
    /经销商/,         '经销商',
    /代理商/,         '代理商',
    /分销商/,         '分销商',
    /合作伙伴/,       '合作伙伴',
    /客户/,           '客户',
    /物流服务商/,     '物流服务商',
    /电商服务商/,     '电商服务商',
    /技术服务商/,     '技术服务商',
    /咨询服务/,       '咨询服务',
    /培训服务/,       '培训服务',
    /代运营/,         '代运营服务',
    /软件服务/,       '软件服务',
    /硬件供应商/,     '硬件供应商',
    /原料供应商/,     '原料供应商',
    /配套商/,         '配套商',
    /加工商/,         '加工商',
    /平台/,           '平台',
  ];

  let category = '';
  for (const [pattern, value] of CATEGORY_PATTERNS) {
    if (pattern.test(trimmed)) {
      category = value;
      break;
    }
  }

  return {
    industry,
    companySize,
    region,
    category,
    description: trimmed,
  };
}

/**
 * 获取非空的标签列表（用于UI渲染）
 */
function getExtractedTags(result: NLSearchResult): ExtractedTag[] {
  const tags: ExtractedTag[] = [];
  const keys: (keyof NLSearchResult)[] = ['industry', 'companySize', 'region', 'category'];
  for (const key of keys) {
    if (result[key]) {
      tags.push({
        key,
        label: TAG_STYLE[key].label,
        value: result[key],
        color: TAG_STYLE[key].color,
      });
    }
  }
  return tags;
}

/**
 * API 搜索 — 调用后端自然语言搜索端点
 */
async function searchByQuery(
  query: string,
  offset = 0,
  limit = 20,
): Promise<{ items: NLSearchApiItem[]; total: number }> {
  const resp = await fetch(`${API_BASE}/api/matching/search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, offset, limit }),
  });
  if (!resp.ok) throw new Error(`搜索失败: ${resp.status}`);
  const json = await resp.json();
  return {
    items: json.data?.items ?? [],
    total: json.data?.total ?? 0,
  };
}

// ─── 组件 ────────────────────────────────────────────────────

export default function NLSearchWidget({ onSearch, onResultSelect, compact = false }: Props) {
  const [input, setInput] = useState('');
  const [result, setResult] = useState<NLSearchResult | null>(null);
  const [showResult, setShowResult] = useState(false);
  const [searchResults, setSearchResults] = useState<NLSearchApiItem[]>([]);
  const [searchTotal, setSearchTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const searchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // 清理定时器
  useEffect(() => {
    return () => {
      if (searchTimerRef.current) {
        clearTimeout(searchTimerRef.current);
      }
    };
  }, []);

  const performSearch = useCallback(async (query: string) => {
    setLoading(true);
    setError(null);
    try {
      const data = await searchByQuery(query);
      setSearchResults(data.items);
      setSearchTotal(data.total);
    } catch (err: any) {
      console.error('[NLSearchWidget] API搜索失败:', err);
      setError(err.message || '搜索请求失败，请稍后重试');
      setSearchResults([]);
      setSearchTotal(0);
    } finally {
      setLoading(false);
    }
  }, []);

  const handleSearch = useCallback((query?: string) => {
    const text = (query ?? input).trim();
    if (!text) return;

    // 1. 本地结构化解析
    const parsed = deconstructQuery(text);
    setResult(parsed);
    setShowResult(true);
    onSearch?.(parsed);

    // 2. 调用后端 API 搜索
    performSearch(text);
  }, [input, onSearch, performSearch]);

  const handleExampleClick = useCallback((query: string) => {
    setInput(query);
    const parsed = deconstructQuery(query);
    setResult(parsed);
    setShowResult(true);
    onSearch?.(parsed);
    performSearch(query);
  }, [onSearch, performSearch]);

  const handleInputChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value;
    setInput(val);
    if (showResult && !val) {
      setShowResult(false);
      setResult(null);
      setSearchResults([]);
      setSearchTotal(0);
      setError(null);
    }
  }, [showResult]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      handleSearch();
    }
  }, [handleSearch]);

  const handleClear = useCallback(() => {
    setInput('');
    setResult(null);
    setShowResult(false);
    setSearchResults([]);
    setSearchTotal(0);
    setError(null);
  }, []);

  const handleSelectResult = useCallback((item: NLSearchApiItem) => {
    onResultSelect?.(item);
  }, [onResultSelect]);

  const tags = result ? getExtractedTags(result) : [];

  /**
   * 渲染搜索结果列表
   */
  const renderSearchResults = () => {
    if (loading) {
      return (
        <div className="flex items-center justify-center py-4">
          <svg className="animate-spin h-5 w-5 text-indigo-500" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          <span className="ml-2 text-sm text-gray-500">正在搜索...</span>
        </div>
      );
    }

    if (error) {
      return (
        <div className="p-3 bg-red-50 rounded-lg border border-red-100">
          <p className="text-xs text-red-600">{error}</p>
          <button
            onClick={() => performSearch(input.trim())}
            className="mt-1 text-xs text-red-500 underline hover:text-red-700"
          >
            重试
          </button>
        </div>
      );
    }

    if (searchResults.length === 0) {
      if (showResult && !loading) {
        return (
          <div className="p-3 bg-gray-50 rounded-lg border border-gray-100 text-center">
            <p className="text-xs text-gray-400">未搜索到匹配的企业名片</p>
          </div>
        );
      }
      return null;
    }

    return (
      <div className="space-y-2">
        <p className="text-xs font-medium text-gray-500">
          搜索到 {searchTotal} 个匹配结果:
        </p>
        <div className="space-y-2 max-h-80 overflow-y-auto">
          {searchResults.map((item) => (
            <div
              key={item.id}
              onClick={() => handleSelectResult(item)}
              className="p-3 bg-white border border-gray-200 rounded-lg hover:border-indigo-300 hover:shadow-sm transition-all cursor-pointer"
            >
              <div className="flex items-start justify-between">
                <div className="flex-1 min-w-0">
                  <h4 className="text-sm font-medium text-gray-800 truncate">
                    {item.title}
                  </h4>
                  {(item.company || item.position) && (
                    <p className="text-xs text-gray-500 mt-0.5 truncate">
                      {[item.position, item.company].filter(Boolean).join(' @ ')}
                    </p>
                  )}
                </div>
                <div className="ml-2 flex-shrink-0">
                  <span
                    className={`inline-flex items-center px-2 py-0.5 text-xs font-medium rounded-full ${
                      item.match_score >= 0.5
                        ? 'bg-green-100 text-green-700'
                        : item.match_score >= 0.25
                        ? 'bg-yellow-100 text-yellow-700'
                        : 'bg-gray-100 text-gray-600'
                    }`}
                  >
                    {Math.round(item.match_score * 100)}%
                  </span>
                </div>
              </div>
              {item.description && (
                <p className="text-xs text-gray-400 mt-1 line-clamp-2">{item.description}</p>
              )}
              {item.tags && item.tags.length > 0 && (
                <div className="flex flex-wrap gap-1 mt-1.5">
                  {item.tags.map((tag, i) => (
                    <span key={i} className="px-1.5 py-0.5 text-[10px] bg-indigo-50 text-indigo-600 rounded-full">
                      {tag}
                    </span>
                  ))}
                </div>
              )}
              {item.match_reasons && item.match_reasons.length > 0 && (
                <p className="text-[10px] text-gray-400 mt-1">{item.match_reasons.join('; ')}</p>
              )}
            </div>
          ))}
        </div>
      </div>
    );
  };

  // ─── 紧凑模式 ────────────────────────────────────────────
  if (compact) {
    return (
      <div className="bg-white rounded-lg border border-gray-200 p-3">
        <div className="flex items-center gap-2">
          <div className="relative flex-1">
            <input
              type="text"
              value={input}
              onChange={handleInputChange}
              onKeyDown={handleKeyDown}
              placeholder="描述您需要的合作伙伴..."
              className="w-full px-3 py-1.5 pr-8 text-xs border border-gray-200 rounded-md focus:ring-1 focus:ring-indigo-400 focus:border-indigo-400"
            />
            {input && (
              <button
                onClick={handleClear}
                className="absolute right-1.5 top-1/2 -translate-y-1/2 text-gray-300 hover:text-gray-500 transition-colors"
              >
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M3 3l8 8M11 3l-8 8" />
                </svg>
              </button>
            )}
          </div>
          <button
            onClick={() => handleSearch()}
            disabled={!input.trim() || loading}
            className="px-2.5 py-1.5 text-xs font-medium bg-indigo-600 text-white rounded-md hover:bg-indigo-700 disabled:bg-gray-200 disabled:text-gray-400 transition-colors"
          >
            {loading ? '搜索中...' : '搜索'}
          </button>
        </div>

        {/* 标签展示 */}
        {showResult && tags.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1">
            {tags.map((tag) => (
              <span
                key={tag.key}
                className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] rounded-full font-medium"
                style={{
                  color: tag.color,
                  backgroundColor: TAG_STYLE[tag.key].bg,
                  borderColor: TAG_STYLE[tag.key].border,
                  borderWidth: 1,
                }}
              >
                {tag.value}
              </span>
            ))}
          </div>
        )}

        {showResult && tags.length === 0 && (
          <p className="mt-2 text-[10px] text-gray-400 italic">
            未提取到结构化标签，将继续以全文匹配方式搜索
          </p>
        )}

        {/* 搜索结果 */}
        {showResult && (
          <div className="mt-2">
            {renderSearchResults()}
          </div>
        )}
      </div>
    );
  }

  // ─── 完整模式 ────────────────────────────────────────────
  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
      {/* 头部 */}
      <div className="px-4 py-3 border-b border-gray-100 bg-gray-50 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-700">
          <span className="mr-1">💬</span>
          智能匹配搜索
        </h3>
        <span className="text-[10px] text-gray-400">自然语言→结构化+API搜索</span>
      </div>

      <div className="p-4 space-y-4">
        {/* 输入区 */}
        <div>
          <div className="relative">
            <input
              type="text"
              value={input}
              onChange={handleInputChange}
              onKeyDown={handleKeyDown}
              placeholder="描述您需要的合作伙伴..."
              className="w-full pl-10 pr-10 py-3 border border-gray-300 rounded-xl text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition-shadow"
            />
            {/* 搜索图标 */}
            <svg
              className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400"
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <circle cx="11" cy="11" r="8" />
              <path d="M21 21l-4.35-4.35" />
            </svg>
            {/* 清除按钮 */}
            {input && (
              <button
                onClick={handleClear}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-300 hover:text-gray-500 transition-colors"
              >
                <svg width="16" height="16" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M3 3l8 8M11 3l-8 8" />
                </svg>
              </button>
            )}
          </div>

          {/* 操作按钮 */}
          <div className="flex gap-2 mt-3">
            <button
              onClick={() => handleSearch()}
              disabled={!input.trim() || loading}
              className="flex-1 py-2 text-sm font-medium rounded-lg text-white bg-indigo-600 hover:bg-indigo-700 disabled:bg-gray-200 disabled:text-gray-400 transition-colors"
            >
              {loading ? '搜索中...' : '搜索匹配'}
            </button>
          </div>
        </div>

        {/* 示例按钮区 */}
        <div>
          <p className="text-xs text-gray-400 mb-2">试试这些示例：</p>
          <div className="flex flex-wrap gap-2">
            {EXAMPLE_QUERIES.slice(0, 2).map((q, i) => (
              <button
                key={i}
                onClick={() => handleExampleClick(q)}
                className="px-3 py-1.5 text-xs rounded-full border border-gray-200 bg-gray-50 text-gray-600 hover:bg-indigo-50 hover:border-indigo-200 hover:text-indigo-600 transition-all"
              >
                "{q}"
              </button>
            ))}
          </div>
          <div className="flex flex-wrap gap-2 mt-1.5">
            {EXAMPLE_QUERIES.slice(2).map((q, i) => (
              <button
                key={i}
                onClick={() => handleExampleClick(q)}
                className="px-3 py-1.5 text-xs rounded-full border border-gray-200 bg-gray-50 text-gray-600 hover:bg-indigo-50 hover:border-indigo-200 hover:text-indigo-600 transition-all"
              >
                "{q}"
              </button>
            ))}
          </div>
        </div>

        {/* 分隔线 */}
        {showResult && <hr className="border-gray-100" />}

        {/* 搜索结果展示区 */}
        {showResult && (
          <div className="space-y-3">
            {/* 原始描述 */}
            <div>
              <p className="text-xs font-medium text-gray-500 mb-1">📝 原始描述：</p>
              <div className="p-2.5 bg-gray-50 rounded-lg border border-gray-100">
                <p className="text-sm text-gray-700">{result?.description}</p>
              </div>
            </div>

            {/* 结构化标签 */}
            <div>
              <p className="text-xs font-medium text-gray-500 mb-2">🏷️ 提取的需求标签：</p>
              {tags.length > 0 ? (
                <div className="flex flex-wrap gap-2">
                  {tags.map((tag) => (
                    <span
                      key={tag.key}
                      className="inline-flex items-center gap-1.5 px-3 py-1 text-xs rounded-full font-medium border"
                      style={{
                        color: tag.color,
                        backgroundColor: TAG_STYLE[tag.key].bg,
                        borderColor: TAG_STYLE[tag.key].border,
                      }}
                    >
                      <span className="text-[10px] opacity-70">{TAG_STYLE[tag.key].label}</span>
                      <span>{tag.value}</span>
                    </span>
                  ))}
                </div>
              ) : (
                <div className="p-3 bg-amber-50 rounded-lg border border-amber-100">
                  <p className="text-xs text-amber-700">
                    💡 未提取到结构化信息，建议使用更具体的描述（如包含行业、规模、地区等关键词）
                  </p>
                </div>
              )}
            </div>

            {/* API 搜索结果 */}
            <div>
              <p className="text-xs font-medium text-gray-500 mb-2">🔎 企业搜索结果：</p>
              {renderSearchResults()}
            </div>

            {/* JSON 预览 */}
            <div>
              <p className="text-xs font-medium text-gray-500 mb-1">📋 结构化输出：</p>
              <pre className="p-3 bg-gray-900 text-green-400 text-[11px] rounded-lg overflow-x-auto leading-relaxed">
{JSON.stringify(result, null, 2)}
              </pre>
            </div>
          </div>
        )}

        {/* 初始提示（无结果时） */}
        {!showResult && (
          <div className="py-6 text-center">
            <div className="text-3xl mb-2">🔍</div>
            <p className="text-sm text-gray-400 mb-1">输入您的需求描述</p>
            <p className="text-xs text-gray-300">
              系统将自动提取行业、规模、地区、品类等关键需求标签，并搜索企业名片
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
