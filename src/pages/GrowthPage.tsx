/**
 * 增长中心页面
 * ============
 * 邀请/推荐/分享功能
 * - 创建邀请链接
 * - 邀请统计
 * - 邀请记录列表
 */

import React, { useCallback, useEffect, useState } from 'react';

// ============================================================
// 类型定义
// ============================================================
interface InviteStats {
  total_invited: number;
  total_accepted: number;
  total_reward: number;
}

interface InviteRecord {
  code: string;
  inviter_id: number;
  inviter_name: string;
  message: string;
  invite_url: string;
  accepted: boolean;
  accepted_by: number | null;
  accepted_name: string | null;
  accepted_at: string | null;
  reward_earned: number;
  created_at: string;
}

interface InviteListData {
  total: number;
  page: number;
  page_size: number;
  items: InviteRecord[];
}

const API_BASE = '/api/v1';

// ============================================================
// 工具：从 localStorage 获取 token
// ============================================================
function getAuthHeaders(): Record<string, string> {
  const token = localStorage.getItem('token') || '';
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  return headers;
}

// ============================================================
// 工具：格式化日期
// ============================================================
function formatDate(iso: string): string {
  if (!iso) return '-';
  const d = new Date(iso);
  return d.toLocaleDateString('zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit',
  });
}

// ============================================================
// API 调用
// ============================================================
async function fetchStats(): Promise<InviteStats> {
  const res = await fetch(`${API_BASE}/growth/stats`, { headers: getAuthHeaders() });
  const body = await res.json();
  if (body.code !== 200) throw new Error(body.message || '获取统计失败');
  return body.data;
}

async function fetchInvites(page = 1, pageSize = 20): Promise<InviteListData> {
  const res = await fetch(`${API_BASE}/growth/invites?page=${page}&page_size=${pageSize}`, {
    headers: getAuthHeaders(),
  });
  const body = await res.json();
  if (body.code !== 200) throw new Error(body.message || '获取邀请列表失败');
  return body.data;
}

async function createInvite(message = ''): Promise<{ code: string; invite_url: string; expires_at: string }> {
  const res = await fetch(`${API_BASE}/growth/invite`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify({ message }),
  });
  const body = await res.json();
  if (body.code !== 200) throw new Error(body.message || '创建邀请链接失败');
  return body.data;
}

// ============================================================
// 统计卡片组件
// ============================================================
function StatsCard({ stats }: { stats: InviteStats }) {
  return (
    <div className="grid grid-cols-3 gap-4 mb-6">
      <div className="bg-white rounded-xl shadow-sm border border-border-light p-4 text-center">
        <div className="text-3xl font-bold text-primary">{stats.total_invited}</div>
        <div className="text-sm text-on-surface/60 mt-1">已邀请</div>
      </div>
      <div className="bg-white rounded-xl shadow-sm border border-border-light p-4 text-center">
        <div className="text-3xl font-bold text-success">{stats.total_accepted}</div>
        <div className="text-sm text-on-surface/60 mt-1">已注册</div>
      </div>
      <div className="bg-white rounded-xl shadow-sm border border-border-light p-4 text-center">
        <div className="text-3xl font-bold text-warning">{stats.total_reward}</div>
        <div className="text-sm text-on-surface/60 mt-1">奖励积分</div>
      </div>
    </div>
  );
}

// ============================================================
// 邀请记录列表组件
// ============================================================
function InviteList({ records }: { records: InviteRecord[] }) {
  if (records.length === 0) {
    return (
      <div className="text-center py-8 text-on-surface/40">
        暂无邀请记录，点击上方按钮生成第一个邀请链接
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {records.map((r) => (
        <div
          key={r.code}
          className="bg-white rounded-xl shadow-sm border border-border-light p-4 flex items-center justify-between"
        >
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="font-mono text-sm text-primary">{r.code}</span>
              {r.accepted ? (
                <span className="text-xs bg-success/10 text-success px-2 py-0.5 rounded-full">已接受</span>
              ) : (
                <span className="text-xs bg-warning/10 text-warning px-2 py-0.5 rounded-full">待接受</span>
              )}
            </div>
            {r.message && <div className="text-sm text-on-surface/60 mt-1 truncate">{r.message}</div>}
            <div className="text-xs text-on-surface/40 mt-1">
              创建于 {formatDate(r.created_at)}
              {r.accepted && ` · ${r.accepted_name} 于 ${formatDate(r.accepted_at!)} 接受`}
            </div>
          </div>
          <div className="text-right ml-4 flex-shrink-0">
            <div className="text-sm font-medium">+{r.reward_earned} 积分</div>
            <button
              onClick={() => {
                navigator.clipboard.writeText(r.invite_url).catch(() => {});
              }}
              className="text-xs text-primary hover:underline mt-1"
            >
              复制链接
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}

// ============================================================
// 增长中心页面主组件
// ============================================================
export default function GrowthPage() {
  const [stats, setStats] = useState<InviteStats>({ total_invited: 0, total_accepted: 0, total_reward: 0 });
  const [records, setRecords] = useState<InviteRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState('');
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState('');

  // 加载数据
  const loadData = useCallback(async () => {
    try {
      const [s, d] = await Promise.all([fetchStats(), fetchInvites()]);
      setStats(s);
      setRecords(d.items);
    } catch (e: any) {
      setError(e.message || '加载失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // 创建邀请
  const handleCreate = async () => {
    setError('');
    try {
      const result = await createInvite(message);
      await navigator.clipboard.writeText(result.invite_url);
      setCopied(true);
      setMessage('');
      setTimeout(() => setCopied(false), 3000);
      await loadData();
    } catch (e: any) {
      setError(e.message || '创建失败');
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen text-on-surface">
        <div className="animate-spin w-8 h-8 border-2 border-primary border-t-transparent rounded-full" />
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto px-4 py-6">
      {/* 标题 */}
      <h1 className="text-2xl font-bold text-on-surface mb-6">增长中心</h1>

      {/* 统计卡片 */}
      <StatsCard stats={stats} />

      {/* 创建邀请链接 */}
      <div className="bg-white rounded-xl shadow-sm border border-border-light p-5 mb-6">
        <h2 className="text-lg font-semibold text-on-surface mb-3">创建邀请链接</h2>
        <div className="flex gap-3">
          <input
            type="text"
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            placeholder="选填：添加邀请附言…"
            className="flex-1 px-4 py-2.5 rounded-lg border border-border-light bg-neutral-bg text-on-surface placeholder:text-on-surface/30 outline-none focus:border-primary focus:ring-1 focus:ring-primary transition-colors"
            maxLength={200}
          />
          <button
            onClick={handleCreate}
            className="px-6 py-2.5 bg-primary text-white rounded-lg font-medium hover:bg-primary/90 active:scale-95 transition-all whitespace-nowrap"
          >
            生成链接
          </button>
        </div>
        {copied && (
          <div className="mt-2 text-sm text-success">✓ 链接已复制到剪贴板</div>
        )}
        {error && (
          <div className="mt-2 text-sm text-danger">{error}</div>
        )}
      </div>

      {/* 邀请记录 */}
      <div className="bg-white rounded-xl shadow-sm border border-border-light p-5">
        <h2 className="text-lg font-semibold text-on-surface mb-4">
          邀请记录
          <span className="text-sm font-normal text-on-surface/40 ml-2">共 {stats.total_invited} 条</span>
        </h2>
        <InviteList records={records} />
      </div>
    </div>
  );
}
