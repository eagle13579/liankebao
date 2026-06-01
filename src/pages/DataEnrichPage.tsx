/**
 * 企业数据页面
 * ============
 * 搜索企业名称 → 展示企业信息
 * 调用 GET /api/v1/enrich/company?name=xxx
 */

import React, { useState } from 'react';

// ============================================================
// 类型定义
// ============================================================
interface CompanyInfo {
  name: string;
  short_name?: string;
  credit_code?: string;
  legal_person?: string;
  registered_capital?: string;
  established_date?: string;
  industry?: string;
  region?: string;
  business_scope?: string;
  business_scope_detail?: string;
  status?: string;
  website?: string;
  tags?: string[];
  confidence?: number;
  note?: string;
  contacts?: CompanyContact[];
  phones?: string[];
  email?: string;
  address?: string;
}

interface CompanyContact {
  name: string;
  title?: string;
  department?: string;
}

interface ApiResponse<T> {
  code: number;
  message: string;
  data?: T;
}

// ============================================================
// 工具函数
// ============================================================
const API_BASE = '';

async function fetchJson<T>(url: string): Promise<T> {
  const token = localStorage.getItem('token');
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (token) headers['Authorization'] = 'Bearer ' + token;

  const res = await fetch(API_BASE + url, { headers });
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
  return await res.json();
}

// ============================================================
// 主组件
// ============================================================
export default function DataEnrichPage() {
  const [searchInput, setSearchInput] = useState('');
  const [searchName, setSearchName] = useState('');
  const [company, setCompany] = useState<CompanyInfo | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searched, setSearched] = useState(false);

  const handleSearch = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    const name = searchInput.trim();
    if (!name) return;

    setSearchName(name);
    setLoading(true);
    setError(null);
    setSearched(true);
    setCompany(null);

    try {
      const encodedName = encodeURIComponent(name);
      const json = await fetchJson<ApiResponse<CompanyInfo>>(
        `/api/v1/enrich/company?name=${encodedName}`
      );

      if (json.code === 200 && json.data) {
        setCompany(json.data);
      } else {
        throw new Error(json.message || '查询失败');
      }
    } catch (err: any) {
      setError(err.message || '网络错误，请稍后重试');
    } finally {
      setLoading(false);
    }
  };

  const confidencePercent = company?.confidence
    ? Math.round(company.confidence * 100)
    : 0;

  return (
    <div className="min-h-screen bg-neutral-bg">
      {/* 页面标题 */}
      <div className="bg-surface border-b border-border-light">
        <div className="max-w-4xl mx-auto px-4 pt-6 pb-4">
          <h1 className="text-2xl font-bold text-on-surface font-manrope">企业数据</h1>
          <p className="text-sm text-text-muted mt-1">查询企业工商信息、经营范围和联系人</p>
        </div>
      </div>

      <div className="max-w-4xl mx-auto px-4 py-6">
        {/* 搜索框 */}
        <div className="bg-surface rounded-xl border border-border-light p-4 mb-6">
          <form onSubmit={handleSearch} className="flex gap-3">
            <div className="flex-1 relative">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted text-sm">🔍</span>
              <input
                type="text"
                value={searchInput}
                onChange={e => setSearchInput(e.target.value)}
                placeholder="输入企业全称或关键词，如「字节跳动」"
                className="w-full pl-9 pr-3 py-2.5 text-sm border border-border-light rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary bg-white"
              />
            </div>
            <button
              type="submit"
              disabled={loading || !searchInput.trim()}
              className="px-6 py-2.5 bg-primary text-white text-sm font-medium rounded-lg hover:bg-primary-container transition-colors disabled:opacity-50 disabled:cursor-not-allowed shadow-sm"
            >
              {loading ? '查询中...' : '查询'}
            </button>
          </form>
          <p className="text-[10px] text-text-muted mt-2">
            数据来源：企查查/天眼查（模拟数据），生产环境切换为真实API
          </p>
        </div>

        {/* 加载态 */}
        {loading && (
          <div className="flex items-center justify-center py-20">
            <div className="animate-spin w-8 h-8 border-2 border-primary border-t-transparent rounded-full" />
            <span className="ml-3 text-sm text-text-muted">正在查询企业信息...</span>
          </div>
        )}

        {/* 错误态 */}
        {!loading && error && (
          <div className="bg-surface rounded-xl border border-border-light p-8">
            <div className="flex flex-col items-center justify-center">
              <div className="w-16 h-16 bg-error/10 rounded-full flex items-center justify-center mb-4">
                <span className="text-3xl">⚠️</span>
              </div>
              <p className="text-sm text-error mb-2">{error}</p>
              <p className="text-xs text-text-muted mb-4">请检查企业名称后重试</p>
              <button
                onClick={handleSearch}
                className="px-4 py-2 bg-primary text-white text-sm rounded-lg hover:bg-primary-container transition-colors"
              >
                重新查询
              </button>
            </div>
          </div>
        )}

        {/* 搜索结果 */}
        {!loading && !error && company && (
          <div className="space-y-6">
            {/* 基本信息卡片 */}
            <div className="bg-surface rounded-xl border border-border-light overflow-hidden">
              {/* 头部 */}
              <div className="p-5 border-b border-border-light">
                <div className="flex items-start justify-between">
                  <div className="flex-1 min-w-0">
                    <h2 className="text-lg font-bold text-on-surface font-manrope mb-1">
                      {company.name}
                    </h2>
                    {company.short_name && (
                      <span className="text-xs text-text-muted">简称: {company.short_name}</span>
                    )}
                  </div>
                  <div className="flex items-center gap-2 shrink-0 ml-4">
                    {company.status && (
                      <span className={`text-xs px-2 py-1 rounded-full font-medium ${
                        company.status === '存续'
                          ? 'bg-emerald-100 text-emerald-700'
                          : company.status === '未知'
                            ? 'bg-slate-100 text-text-muted'
                            : 'bg-amber-100 text-amber-700'
                      }`}>
                        {company.status}
                      </span>
                    )}
                    {company.confidence && company.confidence > 0 && (
                      <span className="text-xs px-2 py-1 bg-sky-100 text-sky-700 rounded-full font-medium">
                        置信度 {confidencePercent}%
                      </span>
                    )}
                  </div>
                </div>
                {company.note && (
                  <p className="text-xs text-amber-600 mt-2 bg-amber-50 px-3 py-1.5 rounded-lg">{company.note}</p>
                )}
              </div>

              {/* 详细信息 */}
              <div className="p-5 grid grid-cols-1 md:grid-cols-2 gap-4">
                <InfoItem label="统一社会信用代码" value={company.credit_code} />
                <InfoItem label="法定代表人" value={company.legal_person} />
                <InfoItem label="注册资本" value={company.registered_capital} />
                <InfoItem label="成立日期" value={company.established_date} />
                <InfoItem label="所属行业" value={company.industry} />
                <InfoItem label="所属地区" value={company.region} />
                {company.website && <InfoItem label="企业官网" value={company.website} link />}
              </div>

              {/* 标签 */}
              {company.tags && company.tags.length > 0 && (
                <div className="px-5 pb-5">
                  <p className="text-xs font-medium text-text-muted mb-2">企业标签</p>
                  <div className="flex flex-wrap gap-1.5">
                    {company.tags.map((tag, idx) => (
                      <span
                        key={idx}
                        className="text-[10px] px-2.5 py-1 bg-sky-50 text-sky-700 rounded-full border border-sky-200"
                      >
                        {tag}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* 经营范围 */}
            {(company.business_scope || company.business_scope_detail) && (
              <div className="bg-surface rounded-xl border border-border-light p-5">
                <h3 className="text-sm font-semibold text-on-surface mb-3">经营范围</h3>
                <p className="text-xs text-on-surface leading-relaxed">
                  {company.business_scope_detail || company.business_scope}
                </p>
              </div>
            )}

            {/* 联系人信息 */}
            <div className="bg-surface rounded-xl border border-border-light p-5">
              <h3 className="text-sm font-semibold text-on-surface mb-3">联系人信息</h3>

              {company.contacts && company.contacts.length > 0 ? (
                <div className="space-y-3 mb-4">
                  {company.contacts.map((contact, idx) => (
                    <div key={idx} className="flex items-center gap-3 p-3 bg-neutral-bg rounded-lg border border-border-light">
                      <div className="w-8 h-8 bg-primary/10 rounded-full flex items-center justify-center text-sm font-bold text-primary shrink-0">
                        {contact.name.charAt(0)}
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-on-surface">{contact.name}</p>
                        <p className="text-xs text-text-muted">
                          {[contact.department, contact.title].filter(Boolean).join(' · ') || '—'}
                        </p>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="flex items-center gap-2 py-3 text-xs text-text-muted">
                  <span>📭</span>
                  <span>{company.note?.includes('联系人') ? company.note : '暂无联系人信息'}</span>
                </div>
              )}

              {/* 联系电话 */}
              {company.phones && company.phones.length > 0 && (
                <div className="pt-3 border-t border-border-light">
                  <p className="text-xs font-medium text-text-muted mb-2">联系电话</p>
                  <div className="flex flex-wrap gap-2">
                    {company.phones.map((phone, idx) => (
                      <span key={idx} className="text-xs px-2.5 py-1 bg-green-50 text-green-700 rounded-full border border-green-200">
                        📞 {phone}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* 邮箱 & 地址 */}
              {(company.email || company.address) && (
                <div className="pt-3 border-t border-border-light mt-3">
                  {company.email && (
                    <p className="text-xs text-text-muted mb-1">📧 {company.email}</p>
                  )}
                  {company.address && (
                    <p className="text-xs text-text-muted">📍 {company.address}</p>
                  )}
                </div>
              )}
            </div>

            {/* 数据来源 */}
            <div className="text-center py-4">
              <p className="text-[10px] text-text-muted">
                💡 数据来源：企查查模拟数据 · 查询名称：{searchName}
              </p>
            </div>
          </div>
        )}

        {/* 初始空态 */}
        {!loading && !error && !company && !searched && (
          <div className="flex flex-col items-center justify-center py-20">
            <div className="w-20 h-20 bg-sky-50 rounded-full flex items-center justify-center mb-4">
              <span className="text-4xl">🏢</span>
            </div>
            <h3 className="text-base font-semibold text-on-surface mb-2">查询企业信息</h3>
            <p className="text-sm text-text-muted text-center max-w-xs">
              输入企业名称，即可获取工商信息、经营范围、联系人和电话等数据
            </p>
          </div>
        )}

        {/* 未找到 */}
        {!loading && !error && !company && searched && (
          <div className="flex flex-col items-center justify-center py-16">
            <div className="w-16 h-16 bg-slate-100 rounded-full flex items-center justify-center mb-4">
              <span className="text-3xl">🔍</span>
            </div>
            <p className="text-sm text-text-muted">未找到「{searchName}」的企业信息</p>
            <p className="text-xs text-text-muted mt-1">请检查企业名称是否准确</p>
          </div>
        )}
      </div>
    </div>
  );
}

// ============================================================
// 信息项子组件
// ============================================================
function InfoItem({ label, value, link }: { label: string; value?: string; link?: boolean }) {
  if (!value || value === '未知') return null;

  return (
    <div>
      <p className="text-[10px] text-text-muted mb-0.5">{label}</p>
      {link ? (
        <a
          href={value}
          target="_blank"
          rel="noopener noreferrer"
          className="text-xs text-primary hover:underline"
        >
          {value}
        </a>
      ) : (
        <p className="text-sm text-on-surface">{value}</p>
      )}
    </div>
  );
}
