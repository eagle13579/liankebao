import { useState, useEffect, useRef, useCallback } from 'react';
import { Bell, X, CheckCheck } from 'lucide-react';

/* ===== 类型定义 ===== */
interface NotificationItem {
  id: number;
  user_id: number;
  type: string;
  title: string;
  content: string;
  related_id: number | null;
  is_read: boolean;
  created_at: string;
}

interface NotifResponse {
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  unread_count: number;
  notifications: NotificationItem[];
}

const API_BASE = '';

async function fetchNotifications(page = 1): Promise<NotifResponse> {
  const resp = await fetch(`${API_BASE}/api/notifications?page=${page}&page_size=10`);
  if (!resp.ok) return { total: 0, page, page_size: 10, total_pages: 1, unread_count: 0, notifications: [] };
  const json = await resp.json();
  return json.data || json;
}

async function fetchUnreadCount(): Promise<number> {
  try {
    const resp = await fetch(`${API_BASE}/api/notifications/unread-count`);
    if (!resp.ok) return 0;
    const json = await resp.json();
    return json.data?.unread ?? json.unread_count ?? 0;
  } catch {
    return 0;
  }
}

async function markAsRead(notificationId: number): Promise<boolean> {
  try {
    const resp = await fetch(`${API_BASE}/api/notifications/${notificationId}/read`, { method: 'PUT' });
    return resp.ok;
  } catch {
    return false;
  }
}

async function markAllAsRead(): Promise<void> {
  try {
    await fetch(`${API_BASE}/api/notifications/read-all`, { method: 'PUT' });
  } catch { /* ignore */ }
}

export default function NotificationBell() {
  const [open, setOpen] = useState(false);
  const [unread, setUnread] = useState(0);
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [loading, setLoading] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);

  // 初始加载未读数
  useEffect(() => {
    fetchUnreadCount().then(setUnread);
    // 每 30 秒轮询
    const interval = setInterval(() => {
      fetchUnreadCount().then(setUnread);
    }, 30000);
    return () => clearInterval(interval);
  }, []);

  // 点击外部关闭
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    if (open) document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [open]);

  const handleToggle = useCallback(async () => {
    if (!open) {
      setLoading(true);
      const data = await fetchNotifications();
      setNotifications(data.notifications || []);
      setUnread(data.unread_count || 0);
      setLoading(false);
    }
    setOpen(prev => !prev);
  }, [open]);

  const handleMarkRead = useCallback(async (notif: NotificationItem) => {
    if (notif.is_read) return;
    await markAsRead(notif.id);
    setNotifications(prev =>
      prev.map(n => n.id === notif.id ? { ...n, is_read: true } : n)
    );
    setUnread(prev => Math.max(0, prev - 1));
  }, []);

  const handleMarkAllRead = useCallback(async () => {
    await markAllAsRead();
    setNotifications(prev => prev.map(n => ({ ...n, is_read: true })));
    setUnread(0);
  }, []);

  // 格式化时间
  const formatTime = (iso: string) => {
    const d = new Date(iso);
    const now = new Date();
    const diffMs = now.getTime() - d.getTime();
    const diffMin = Math.floor(diffMs / 60000);
    if (diffMin < 1) return '刚刚';
    if (diffMin < 60) return `${diffMin}分钟前`;
    const diffHour = Math.floor(diffMin / 60);
    if (diffHour < 24) return `${diffHour}小时前`;
    return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' });
  };

  // 通知类型对应图标文字
  const typeLabel = (type: string) => {
    const map: Record<string, string> = {
      match_alert: '匹配提醒',
      order_status: '订单状态',
      payment: '支付通知',
      withdrawal: '提现通知',
      review_result: '审核结果',
      system: '系统通知',
    };
    return map[type] || type;
  };

  return (
    <div ref={panelRef} className="relative">
      {/* 铃铛按钮 */}
      <button
        onClick={handleToggle}
        className="relative p-2 text-gray-600 hover:text-blue-600 transition-colors rounded-full hover:bg-gray-100"
        aria-label="通知"
      >
        <Bell className="w-5 h-5" />
        {unread > 0 && (
          <span className="absolute -top-0.5 -right-0.5 inline-flex items-center justify-center w-4.5 h-4.5 text-[10px] font-bold text-white bg-red-500 rounded-full min-w-[18px] px-1">
            {unread > 99 ? '99+' : unread}
          </span>
        )}
      </button>

      {/* 下拉面板 */}
      {open && (
        <div className="absolute right-0 top-full mt-2 w-80 sm:w-96 bg-white border border-gray-200 rounded-xl shadow-lg z-50 max-h-[480px] flex flex-col">
          {/* 面板头部 */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100">
            <h3 className="text-sm font-semibold text-gray-800">通知</h3>
            <div className="flex items-center gap-2">
              {unread > 0 && (
                <button
                  onClick={handleMarkAllRead}
                  className="flex items-center gap-1 text-xs text-blue-600 hover:text-blue-700"
                >
                  <CheckCheck className="w-3.5 h-3.5" /> 全部已读
                </button>
              )}
              <button onClick={() => setOpen(false)} className="text-gray-400 hover:text-gray-600">
                <X className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* 列表 */}
          <div className="flex-1 overflow-y-auto">
            {loading ? (
              <div className="flex justify-center py-8">
                <div className="w-5 h-5 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
              </div>
            ) : notifications.length === 0 ? (
              <div className="py-8 text-center text-sm text-gray-400">暂无通知</div>
            ) : (
              <div className="divide-y divide-gray-50">
                {notifications.map(notif => (
                  <div
                    key={notif.id}
                    onClick={() => handleMarkRead(notif)}
                    className={`px-4 py-3 cursor-pointer transition-colors hover:bg-gray-50 ${
                      notif.is_read ? '' : 'bg-blue-50/40'
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-1.5 mb-0.5">
                          <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded-full ${
                            notif.type === 'match_alert'
                              ? 'bg-green-100 text-green-700'
                              : 'bg-gray-100 text-gray-600'
                          }`}>
                            {typeLabel(notif.type)}
                          </span>
                          {!notif.is_read && (
                            <span className="w-2 h-2 bg-blue-500 rounded-full flex-shrink-0" />
                          )}
                        </div>
                        <p className="text-sm font-medium text-gray-800 truncate">{notif.title}</p>
                        {notif.content && (
                          <p className="text-xs text-gray-500 mt-0.5 line-clamp-2">{notif.content}</p>
                        )}
                      </div>
                      <span className="text-[10px] text-gray-400 whitespace-nowrap flex-shrink-0 mt-0.5">
                        {formatTime(notif.created_at)}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* 底部提示 */}
          {notifications.length > 0 && (
            <div className="px-4 py-2 border-t border-gray-100 text-center text-[10px] text-gray-400">
              {notifications.length} 条通知
            </div>
          )}
        </div>
      )}
    </div>
  );
}
