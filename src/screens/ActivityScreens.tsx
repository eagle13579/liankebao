import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ArrowLeft, Clock, Phone, Mail, MessageCircle, Calendar,
  FileText, ShoppingBag, Download, Upload, Users, Star,
  Bell, AlertCircle, Activity, ChevronRight, Filter
} from 'lucide-react';
import { api } from '../api/client';
import { Loading, ErrorBlock } from '../components/StatusComponents';
import type { GlobalActivity } from '../types';

const ACTIVITY_TYPES: Record<string, { label: string; icon: React.ElementType; color: string }> = {
  call: { label: '电话沟通', icon: Phone, color: 'text-emerald-600 bg-emerald-50' },
  meeting: { label: '线下会面', icon: Users, color: 'text-violet-600 bg-violet-50' },
  email: { label: '邮件往来', icon: Mail, color: 'text-blue-600 bg-blue-50' },
  wechat: { label: '微信沟通', icon: MessageCircle, color: 'text-sky-600 bg-sky-50' },
  order: { label: '订单交易', icon: ShoppingBag, color: 'text-amber-600 bg-amber-50' },
  note: { label: '跟进记录', icon: FileText, color: 'text-slate-600 bg-slate-50' },
  import: { label: '导入联系人', icon: Download, color: 'text-rose-600 bg-rose-50' },
  system: { label: '系统通知', icon: Bell, color: 'text-slate-600 bg-slate-50' },
};

function formatTime(dateStr: string): string {
  const d = new Date(dateStr);
  const now = new Date();
  const diff = now.getTime() - d.getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return '刚刚';
  if (minutes < 60) return `${minutes}分钟前`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}小时前`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}天前`;
  return d.toLocaleDateString('zh-CN');
}

function groupByDate(items: GlobalActivity[]): Record<string, GlobalActivity[]> {
  const groups: Record<string, GlobalActivity[]> = {};
  items.forEach(item => {
    const date = new Date(item.created_at).toLocaleDateString('zh-CN', {
      year: 'numeric', month: 'long', day: 'numeric', weekday: 'short',
    });
    if (!groups[date]) groups[date] = [];
    groups[date].push(item);
  });
  return groups;
}

export function ActivityLog() {
  const navigate = useNavigate();
  const [activities, setActivities] = useState<GlobalActivity[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [filterType, setFilterType] = useState('');

  const fetchActivities = async () => {
    setLoading(true);
    setError('');
    try {
      const params = filterType ? `?type=${filterType}` : '';
      const res = await api.get<{ items: GlobalActivity[] }>(`/api/activities${params}`);
      if (res.code === 200 && res.data) {
        setActivities(res.data.items || []);
      } else {
        setActivities([]);
      }
    } catch (e: any) {
      setError(e.message || '加载活动日志失败');
      setActivities([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchActivities();
  }, [filterType]);

  const grouped = groupByDate(activities);
  const typeKeys = Object.keys(ACTIVITY_TYPES);

  return (
    <div className="flex flex-col min-h-screen bg-gradient-to-b from-sky-50/30 via-white to-white font-sans pb-8">
      {/* Header */}
      <header className="bg-gradient-to-r from-sky-600 to-blue-600 px-4 pt-12 pb-6 relative overflow-hidden">
        <div className="absolute inset-0 opacity-10">
          <div className="absolute w-72 h-72 bg-white rounded-full -top-20 -right-20" />
          <div className="absolute w-48 h-48 bg-white rounded-full bottom-0 left-10" />
        </div>
        <div className="flex items-center gap-3 relative z-10 mb-3">
          <button onClick={() => navigate(-1)} className="w-9 h-9 flex items-center justify-center rounded-xl bg-white/20 text-white active:scale-90 transition-all">
            <ArrowLeft className="w-5 h-5" />
          </button>
          <div>
            <h1 className="text-xl font-extrabold text-white font-manrope">活动日志</h1>
            <p className="text-xs text-white/70">用户操作时间线 · 所有动态记录</p>
          </div>
        </div>

        {/* Filter Chips */}
        <div className="relative z-10 flex gap-2 overflow-x-auto no-scrollbar pb-1">
          <button
            onClick={() => setFilterType('')}
            className={`shrink-0 px-3 py-1 rounded-full text-xs font-bold transition-all ${
              !filterType ? 'bg-white text-sky-600' : 'bg-white/20 text-white/80 hover:bg-white/30'
            }`}
          >
            全部
          </button>
          {typeKeys.map(key => (
            <button
              key={key}
              onClick={() => setFilterType(filterType === key ? '' : key)}
              className={`shrink-0 px-3 py-1 rounded-full text-xs font-bold transition-all ${
                filterType === key ? 'bg-white text-sky-600' : 'bg-white/20 text-white/80 hover:bg-white/30'
              }`}
            >
              {ACTIVITY_TYPES[key].label}
            </button>
          ))}
        </div>
      </header>

      <div className="px-4 -mt-3">
        {loading ? (
          <div className="py-8"><Loading text="加载活动记录..." /></div>
        ) : error ? (
          <ErrorBlock message={error} onRetry={fetchActivities} />
        ) : activities.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 text-slate-400">
            <div className="w-16 h-16 rounded-full bg-sky-50 flex items-center justify-center mb-4">
              <Activity className="w-8 h-8 text-sky-300" />
            </div>
            <p className="text-sm font-medium">暂无活动记录</p>
            <p className="text-xs mt-1">您的操作和系统事件将显示在这里</p>
          </div>
        ) : (
          <div className="space-y-6 pt-4">
            {Object.entries(grouped).map(([date, items]) => (
              <div key={date}>
                {/* Date Header */}
                <div className="flex items-center gap-2 mb-3">
                  <Calendar className="w-4 h-4 text-sky-500" />
                  <h3 className="text-xs font-bold text-slate-500 uppercase tracking-wider">{date}</h3>
                  <div className="flex-1 h-px bg-slate-100" />
                  <span className="text-[10px] text-slate-400">{items.length} 条</span>
                </div>

                {/* Activity Timeline */}
                <div className="relative pl-6 space-y-0">
                  {/* Vertical Line */}
                  <div className="absolute left-2.5 top-0 bottom-0 w-px bg-gradient-to-b from-sky-200 via-sky-100 to-transparent" />

                  {items.map((activity) => {
                    const typeDef = ACTIVITY_TYPES[activity.action_type] || {
                      label: activity.action_type || '其他',
                      icon: Activity,
                      color: 'text-slate-600 bg-slate-50',
                    };
                    const Icon = typeDef.icon;

                    return (
                      <div key={activity.id} className="relative pb-5 last:pb-0">
                        {/* Timeline Dot */}
                        <div className={`absolute -left-[18px] top-1 w-3 h-3 rounded-full border-2 border-white ${typeDef.color.split(' ')[1]} shadow-sm`} />

                        {/* Activity Card */}
                        <div className="bg-white rounded-2xl p-4 border border-slate-100 shadow-sm hover:shadow-md transition-all ml-2">
                          <div className="flex items-start gap-3">
                            <div className={`w-9 h-9 rounded-xl ${typeDef.color} flex items-center justify-center shrink-0`}>
                              <Icon className="w-4.5 h-4.5" />
                            </div>
                            <div className="flex-1 min-w-0">
                              {/* Header row */}
                              <div className="flex items-center justify-between gap-2 mb-1">
                                <span className="text-xs font-bold text-slate-700">{typeDef.label}</span>
                                <span className="text-[10px] text-slate-400 shrink-0 flex items-center gap-1">
                                  <Clock className="w-3 h-3" />
                                  {formatTime(activity.created_at)}
                                </span>
                              </div>

                              {/* Summary */}
                              {activity.summary && (
                                <p className="text-sm text-slate-600 leading-relaxed">{activity.summary}</p>
                              )}

                              {/* Detail */}
                              {activity.detail && (
                                <p className="text-xs text-slate-400 mt-1 line-clamp-2">{activity.detail}</p>
                              )}

                              {/* User attribution */}
                              {activity.user_name && (
                                <div className="flex items-center gap-1.5 mt-2 pt-2 border-t border-slate-50">
                                  <div className="w-5 h-5 rounded-full bg-gradient-to-br from-sky-400 to-blue-500 flex items-center justify-center text-white text-[8px] font-bold">
                                    {activity.user_name[0]}
                                  </div>
                                  <span className="text-[10px] text-slate-400">{activity.user_name}</span>
                                  {activity.related_type && (
                                    <span className="text-[10px] text-slate-300">· {activity.related_type}</span>
                                  )}
                                </div>
                              )}
                            </div>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
