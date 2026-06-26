/**
 * 链客宝 - 匹配额度 Dashboard
 * =============================
 * 展示当前剩余额度、额度消耗历史、充值入口
 * 对接 /api/membership/credits 和 /api/membership/status
 */

import React, { useState, useEffect } from 'react';
import {
  CreditCard,
  Zap,
  History,
  RefreshCw,
  AlertTriangle,
  ExternalLink,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import {
  fetchCredits,
  fetchMembershipStatus,
  fetchUserProfile,
  getCreditHistory,
} from '../api-matching';
import type { CreditLogEntry } from '../api-matching';

export default function CreditsDashboard() {
  const [credits, setCredits] = useState<number>(0);
  const [totalMonthly, setTotalMonthly] = useState<number>(10);
  const [tier, setTier] = useState<string>('free');
  const [levelName, setLevelName] = useState<string>('免费会员');
  const [expiredAt, setExpiredAt] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showHistory, setShowHistory] = useState(false);
  const [history, setHistory] = useState<CreditLogEntry[]>([]);

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      // Try /api/user/profile (match_credits) first, then membership status, then credits fallback
      let creditValue: number | null = null;
      try {
        const profile = await fetchUserProfile();
        creditValue = profile.match_credits;
        if (profile.tier) setTier(profile.tier);
      } catch {
        // fall through
      }
      try {
        const status = await fetchMembershipStatus();
        if (creditValue === null) creditValue = status.remaining_coupons;
        setTotalMonthly(status.total_coupons_this_month);
        setLevelName(status.level_name);
        setExpiredAt(status.expired_at);
        if (!tier || tier === 'free') setTier(status.level);
      } catch {
        // fallback to simple credits endpoint
        if (creditValue === null) {
          const simple = await fetchCredits();
          creditValue = simple.credits;
          setTier(simple.tier);
        }
      }
      setCredits(creditValue ?? 0);
      setHistory(getCreditHistory());
    } catch (e: any) {
      setError(e.message || '获取额度信息失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const formatDate = (dateStr: string) => {
    try {
      const d = new Date(dateStr);
      return d.toLocaleString('zh-CN', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return dateStr;
    }
  };

  const tierColors: Record<string, string> = {
    free: 'bg-gray-100 text-gray-600 border-gray-300',
    gold: 'bg-yellow-50 text-yellow-700 border-yellow-300',
    diamond: 'bg-blue-50 text-blue-700 border-blue-300',
    board: 'bg-purple-50 text-purple-700 border-purple-300',
  };

  const isLow = credits <= 0;
  const isWarning = credits > 0 && credits <= 2;

  return (
    <div className="mx-4 mb-4">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-lg font-semibold text-gray-800 flex items-center gap-2">
          <CreditCard className="w-5 h-5 text-blue-600" />
          匹配额度
        </h3>
        <button
          onClick={loadData}
          disabled={loading}
          className="p-1.5 text-gray-400 hover:text-blue-500 rounded-lg hover:bg-gray-100 transition-colors"
          title="刷新"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {error && (
        <div className="p-3 mb-3 bg-red-50 border border-red-200 rounded-xl text-red-600 text-sm">{error}</div>
      )}

      {/* Balance card */}
      <div
        className={`p-4 rounded-xl border-2 transition-colors ${
          isLow
            ? 'bg-red-50 border-red-200'
            : isWarning
            ? 'bg-yellow-50 border-yellow-200'
            : 'bg-blue-50 border-blue-200'
        }`}
      >
        <div className="flex items-start justify-between">
          <div>
            <div className="flex items-center gap-2">
              <Zap className={`w-5 h-5 ${isLow ? 'text-red-500' : isWarning ? 'text-yellow-500' : 'text-blue-500'}`} />
              <span className="text-sm text-gray-500">本月剩余</span>
            </div>
            <div className="mt-1 flex items-baseline gap-1">
              <span
                className={`text-3xl font-bold ${
                  isLow ? 'text-red-600' : isWarning ? 'text-yellow-600' : 'text-blue-600'
                }`}
              >
                {loading ? '...' : credits}
              </span>
              <span className="text-sm text-gray-400">/ {totalMonthly} 次匹配</span>
            </div>
          </div>

          {/* Tier badge */}
          <span
            className={`px-2.5 py-1 text-xs font-medium rounded-full border ${
              tierColors[tier] || 'bg-gray-100 text-gray-600'
            }`}
          >
            {levelName}
          </span>
        </div>

        {/* Low balance warning */}
        {isLow && (
          <div className="mt-3 flex items-center gap-2 text-sm text-red-600">
            <AlertTriangle className="w-4 h-4 flex-shrink-0" />
            <span>额度不足，请充值后继续匹配</span>
          </div>
        )}

        {/* Actions */}
        <div className="mt-3 flex gap-2">
          {isLow ? (
            <a
              href="/recharge"
              className="flex-1 flex items-center justify-center gap-1.5 px-4 py-2 bg-red-600 text-white text-sm rounded-lg hover:bg-red-700 transition-colors"
            >
              <ExternalLink className="w-3.5 h-3.5" />
              额度不足，去充值
            </a>
          ) : (
            <a
              href="/recharge"
              className="flex-1 flex items-center justify-center gap-1.5 px-4 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700 transition-colors"
            >
              <ExternalLink className="w-3.5 h-3.5" />
              去充值
            </a>
          )}
        </div>

        {/* Expiry info */}
        {expiredAt && tier !== 'free' && (
          <p className="mt-2 text-xs text-gray-400">
            会员有效期至: {formatDate(expiredAt)}
          </p>
        )}
      </div>

      {/* Usage history toggle */}
      <button
        onClick={() => setShowHistory(!showHistory)}
        className="mt-3 w-full flex items-center justify-between px-4 py-2.5 bg-white border border-gray-200 rounded-xl hover:bg-gray-50 transition-colors"
      >
        <span className="text-sm font-medium text-gray-700 flex items-center gap-2">
          <History className="w-4 h-4 text-gray-400" />
          额度消耗历史
        </span>
        {showHistory ? (
          <ChevronUp className="w-4 h-4 text-gray-400" />
        ) : (
          <ChevronDown className="w-4 h-4 text-gray-400" />
        )}
      </button>

      {/* History list */}
      {showHistory && (
        <div className="mt-2 bg-white border border-gray-200 rounded-xl overflow-hidden">
          {history.length === 0 ? (
            <div className="p-6 text-center text-gray-400 text-sm">
              <History className="w-8 h-8 mx-auto mb-2 opacity-50" />
              暂无消耗记录
            </div>
          ) : (
            <div className="divide-y divide-gray-100">
              {history.map((entry, idx) => (
                <div key={idx} className="px-4 py-3 flex items-center gap-3">
                  <div
                    className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold ${
                      entry.amount < 0
                        ? 'bg-red-50 text-red-600'
                        : 'bg-green-50 text-green-600'
                    }`}
                  >
                    {entry.amount < 0 ? '' : '+'}
                    {entry.amount}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-gray-700 truncate">
                      {entry.reason === 'use'
                        ? `匹配消耗 - ${entry.related_title || ''}`
                        : entry.reason === 'upgrade_reward'
                        ? '会员升级奖励'
                        : entry.reason === 'admin_adjust'
                        ? '管理员调整'
                        : entry.reason}
                    </p>
                    <p className="text-xs text-gray-400 mt-0.5">{formatDate(entry.created_at)}</p>
                  </div>
                  <span className="text-xs text-gray-400">剩余: {entry.balance_after}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* TODO: 对接支付模块，替换 /recharge 链接 */}

    </div>
  );
}
