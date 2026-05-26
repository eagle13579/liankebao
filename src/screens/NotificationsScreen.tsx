import { useNavigate } from 'react-router-dom';
import { Bell, ArrowLeft, CheckCheck, MailOpen } from 'lucide-react';
import { useState, useEffect, useCallback } from 'react';
import { api } from '../api/client';
import { Loading, Empty } from '../components/StatusComponents';

interface NotificationItem {
  id: number;
  title: string;
  content: string;
  is_read: boolean;
  created_at: string;
  type?: string;
}

export default function NotificationsScreen() {
  const navigate = useNavigate();
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const fetchNotifications = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await api.get<NotificationItem[]>('/api/notifications');
      if (res.data) {
        setNotifications(res.data);
      } else {
        setError(res.message || '获取通知失败');
      }
    } catch (e: any) {
      setError(e.message || '网络错误');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchNotifications();
  }, [fetchNotifications]);

  const markAsRead = async (id: number) => {
    try {
      await api.put(`/api/notifications/${id}/read`, {});
      setNotifications(prev =>
        prev.map(n => (n.id === id ? { ...n, is_read: true } : n))
      );
    } catch {}
  };

  const formatTime = (dateStr: string) => {
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMin = Math.floor(diffMs / 60000);
    const diffHour = Math.floor(diffMs / 3600000);
    const diffDay = Math.floor(diffMs / 86400000);

    if (diffMin < 1) return '刚刚';
    if (diffMin < 60) return `${diffMin}分钟前`;
    if (diffHour < 24) return `${diffHour}小时前`;
    if (diffDay < 7) return `${diffDay}天前`;
    return date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' });
  };

  return (
    <div className="flex flex-col min-h-screen bg-gradient-to-b from-sky-50/30 via-white to-white font-sans">
      {/* Header */}
      <header className="fixed top-0 w-full z-50 bg-white/80 backdrop-blur-xl border-b border-sky-100/50 px-4 h-16">
        <div className="flex items-center justify-between h-full max-w-3xl mx-auto">
          <div className="flex items-center gap-3">
            <button
              onClick={() => navigate(-1)}
              className="w-8 h-8 rounded-full bg-slate-50 flex items-center justify-center text-slate-500 hover:bg-sky-50 hover:text-sky-600 active:scale-90 transition-all border border-slate-100"
            >
              <ArrowLeft className="w-4.5 h-4.5" />
            </button>
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-lg brand-gradient flex items-center justify-center">
                <Bell className="w-4 h-4 text-white" />
              </div>
              <h1 className="font-manrope text-lg font-extrabold bg-gradient-to-r from-sky-600 to-blue-600 bg-clip-text text-transparent">
                消息中心
              </h1>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {notifications.some(n => !n.is_read) && (
              <span className="text-[10px] text-slate-400 font-medium bg-slate-50 px-2 py-1 rounded-full border border-slate-100">
                {notifications.filter(n => !n.is_read).length}条未读
              </span>
            )}
          </div>
        </div>
      </header>

      {/* Body */}
      <main className="pt-16 max-w-3xl mx-auto w-full">
        {loading ? (
          <div className="px-4">
            <Loading text="加载消息中..." />
          </div>
        ) : error ? (
          <div className="px-4 pt-8">
            <div className="flex flex-col items-center justify-center py-16 text-center">
              <div className="w-16 h-16 bg-gradient-to-br from-red-50 to-rose-50 rounded-2xl flex items-center justify-center mb-4 border border-red-100 shadow-sm">
                <svg className="w-8 h-8 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9 3.75h.008v.008H12v-.008Z" />
                </svg>
              </div>
              <p className="text-sm text-red-500 font-medium mb-4 max-w-xs">{error}</p>
              <button
                onClick={fetchNotifications}
                className="px-5 py-2.5 bg-gradient-to-r from-sky-500 to-blue-600 text-white rounded-xl text-xs font-bold active:scale-95 transition-all shadow-md shadow-sky-500/20 hover:shadow-lg"
              >
                重新加载
              </button>
            </div>
          </div>
        ) : notifications.length === 0 ? (
          <div className="px-4 pt-8">
            <Empty text="暂无消息" description="当有新的通知时，会在这里显示" />
          </div>
        ) : (
          <div className="px-4 pt-4 pb-8 space-y-3">
            {notifications.map((item) => (
              <div
                key={item.id}
                onClick={() => !item.is_read && markAsRead(item.id)}
                className={`bg-white rounded-2xl p-4 border shadow-sm transition-all cursor-pointer active:scale-[0.98] ${
                  item.is_read
                    ? 'border-slate-100 opacity-70'
                    : 'border-sky-100 hover:shadow-md hover:border-sky-200'
                }`}
              >
                <div className="flex items-start gap-3">
                  {/* Icon */}
                  <div
                    className={`w-10 h-10 rounded-xl flex items-center justify-center shrink-0 ${
                      item.is_read
                        ? 'bg-slate-50 text-slate-400'
                        : 'bg-sky-50 text-sky-600'
                    }`}
                  >
                    {item.is_read ? (
                      <MailOpen className="w-5 h-5" />
                    ) : (
                      <Bell className="w-5 h-5" />
                    )}
                  </div>

                  {/* Content */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between gap-2">
                      <h3
                        className={`text-sm font-bold truncate ${
                          item.is_read ? 'text-slate-500' : 'text-slate-800'
                        }`}
                      >
                        {item.title}
                      </h3>
                      {!item.is_read && (
                        <span className="w-2 h-2 rounded-full bg-sky-500 shrink-0" />
                      )}
                    </div>
                    <p
                      className={`text-xs mt-1 line-clamp-2 ${
                        item.is_read ? 'text-slate-400' : 'text-slate-600'
                      }`}
                    >
                      {item.content}
                    </p>
                    <div className="flex items-center gap-2 mt-2">
                      <span className="text-[10px] text-slate-400">
                        {formatTime(item.created_at)}
                      </span>
                      {item.is_read && (
                        <span className="text-[10px] text-sky-400 flex items-center gap-0.5">
                          <CheckCheck className="w-3 h-3" /> 已读
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
