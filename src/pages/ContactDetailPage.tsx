import { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  ChevronLeft, Phone, Mail, MessageCircle, Building2, Briefcase, Calendar,
  Clock, Tag, Edit3, Plus, FileText, User, Smartphone, MapPin, Star
} from 'lucide-react';
import { api } from '../api/client';
import { Contact, Activity } from '../types';
import { Loading, ErrorBlock } from '../components/StatusComponents';

const ACTION_TYPE_LABELS: Record<string, string> = {
  call: '通话',
  meeting: '会面',
  message: '消息',
  email: '邮件',
  wechat: '微信',
  remark: '备注',
  other: '其他',
};

const ACTION_TYPE_ICONS: Record<string, React.ReactNode> = {
  call: <Phone className="w-4 h-4" />,
  meeting: <User className="w-4 h-4" />,
  message: <MessageCircle className="w-4 h-4" />,
  email: <Mail className="w-4 h-4" />,
  wechat: <MessageCircle className="w-4 h-4" />,
  remark: <FileText className="w-4 h-4" />,
};

export default function ContactDetailPage() {
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const [contact, setContact] = useState<Contact | null>(null);
  const [activities, setActivities] = useState<Activity[]>([]);
  const [status, setStatus] = useState<'loading' | 'error' | 'success'>('loading');
  const [error, setError] = useState('');
  const [showAddActivity, setShowAddActivity] = useState(false);
  const [newActivity, setNewActivity] = useState({ action_type: 'other', summary: '', detail: '' });

  useEffect(() => {
    if (!id) return;
    setStatus('loading');
    Promise.all([
      api.get<Contact>(`/api/contacts/${id}`),
      api.get<{ items: Activity[] }>(`/api/contacts/${id}/activities`),
    ]).then(([contactRes, activityRes]) => {
      if (contactRes.data) setContact(contactRes.data);
      if (activityRes.data?.items) setActivities(activityRes.data.items);
      setStatus('success');
    }).catch((e: any) => {
      setError(e.message || '加载失败');
      setStatus('error');
    });
  }, [id]);

  const handleAddActivity = async () => {
    if (!newActivity.summary.trim()) return;
    try {
      const res = await api.post<Activity>(`/api/contacts/${id}/activities`, newActivity);
      if (res.data) {
        setActivities(prev => [res.data!, ...prev]);
        setShowAddActivity(false);
        setNewActivity({ action_type: 'other', summary: '', detail: '' });
      }
    } catch (e: any) {
      alert('添加失败：' + (e.message || '未知错误'));
    }
  };

  const formatDate = (dateStr: string) => {
    const d = new Date(dateStr);
    return d.toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' });
  };

  const formatDateTime = (dateStr: string) => {
    const d = new Date(dateStr);
    return d.toLocaleString('zh-CN', {
      year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit',
    });
  };

  if (status === 'loading') return (
    <div className="flex flex-col min-h-screen bg-neutral-bg font-sans">
      <header className="fixed top-0 w-full z-50 bg-neutral-bg border-b border-border-light flex items-center px-4 h-16">
        <button onClick={() => navigate(-1)} className="text-slate-600"><ChevronLeft className="w-6 h-6" /></button>
      </header>
      <main className="pt-16"><Loading /></main>
    </div>
  );

  if (status === 'error') return (
    <div className="flex flex-col min-h-screen bg-neutral-bg font-sans">
      <header className="fixed top-0 w-full z-50 bg-neutral-bg border-b border-border-light flex items-center px-4 h-16">
        <button onClick={() => navigate(-1)} className="text-slate-600"><ChevronLeft className="w-6 h-6" /></button>
        <h1 className="font-manrope text-lg font-bold text-primary-container ml-3">联系人详情</h1>
      </header>
      <main className="pt-16"><ErrorBlock message={error} /></main>
    </div>
  );

  if (!contact) return null;

  const infoItems = [
    { icon: <Phone className="w-4 h-4" />, label: '电话', value: contact.phone },
    { icon: <Mail className="w-4 h-4" />, label: '邮箱', value: contact.email },
    { icon: <MessageCircle className="w-4 h-4" />, label: '微信', value: contact.wechat_id },
    { icon: <Building2 className="w-4 h-4" />, label: '公司', value: contact.company },
    { icon: <Briefcase className="w-4 h-4" />, label: '职位', value: contact.position },
    { icon: <MapPin className="w-4 h-4" />, label: '来源', value: contact.source },
  ].filter(item => item.value);

  return (
    <div className="flex flex-col min-h-screen bg-neutral-bg font-sans pb-24">
      {/* Header */}
      <header className="fixed top-0 w-full z-50 bg-neutral-bg border-b border-border-light flex items-center justify-between px-4 h-16">
        <div className="flex items-center gap-3">
          <button onClick={() => navigate(-1)} className="text-slate-600">
            <ChevronLeft className="w-6 h-6" />
          </button>
          <h1 className="font-manrope text-lg font-bold text-primary-container">联系人详情</h1>
        </div>
        <button
          onClick={() => navigate(`/contacts/${id}?edit=1`, { state: { transition: 'push' } })}
          className="flex items-center gap-1 text-primary-container text-xs font-bold active:opacity-70"
        >
          <Edit3 className="w-4 h-4" />
          编辑
        </button>
      </header>

      <main className="pt-16 p-4 space-y-4">
        {/* Profile Card */}
        <div className="bg-white rounded-2xl border border-border-light p-5">
          <div className="flex items-center gap-4">
            <div className="w-16 h-16 rounded-full bg-sky-50 flex items-center justify-center overflow-hidden shrink-0">
              {contact.avatar ? (
                <img src={contact.avatar} className="w-full h-full object-cover" />
              ) : (
                <User className="w-8 h-8 text-primary-container" />
              )}
            </div>
            <div className="flex-1 min-w-0">
              <h2 className="text-xl font-bold text-on-surface">{contact.name}</h2>
              <div className="flex items-center gap-2 mt-1">
                {contact.company && (
                  <span className="text-xs text-slate-500 flex items-center gap-1">
                    <Building2 className="w-3.5 h-3.5" />
                    {contact.company}
                  </span>
                )}
                {contact.position && (
                  <span className="text-xs text-slate-400">· {contact.position}</span>
                )}
              </div>
            </div>
          </div>

          {/* Tags */}
          {contact.tags && contact.tags.length > 0 && (
            <div className="mt-4 flex flex-wrap gap-2">
              {contact.tags.map((tag, i) => (
                <span key={i} className="flex items-center gap-1 text-xs bg-sky-50 text-primary-container px-2.5 py-1 rounded-full font-medium">
                  <Tag className="w-3 h-3" />
                  {tag}
                </span>
              ))}
            </div>
          )}
        </div>

        {/* Contact Info */}
        {infoItems.length > 0 && (
          <div className="bg-white rounded-2xl border border-border-light p-4 space-y-3">
            <h3 className="text-sm font-bold flex items-center gap-2">
              <span className="w-1 h-4 bg-primary-container rounded-full"></span>
              联系方式
            </h3>
            {infoItems.map((item, i) => (
              <div key={i} className="flex items-center gap-3 text-sm">
                <span className="text-slate-400 w-5 flex justify-center">{item.icon}</span>
                <span className="text-slate-500 w-12 text-xs">{item.label}</span>
                <span className="text-on-surface font-medium">{item.value}</span>
              </div>
            ))}
          </div>
        )}

        {/* Notes */}
        {contact.notes && (
          <div className="bg-white rounded-2xl border border-border-light p-4">
            <h3 className="text-sm font-bold flex items-center gap-2 mb-2">
              <span className="w-1 h-4 bg-primary-container rounded-full"></span>
              备注
            </h3>
            <p className="text-sm text-slate-600 whitespace-pre-wrap">{contact.notes}</p>
          </div>
        )}

        {/* Meta */}
        <div className="bg-white rounded-2xl border border-border-light p-4">
          <div className="flex items-center gap-4 text-xs text-text-muted">
            <span className="flex items-center gap-1">
              <Calendar className="w-3.5 h-3.5" />
              创建于 {formatDate(contact.created_at)}
            </span>
            <span className="flex items-center gap-1">
              <Clock className="w-3.5 h-3.5" />
              更新于 {formatDate(contact.updated_at)}
            </span>
          </div>
        </div>

        {/* Timeline */}
        <div className="bg-white rounded-2xl border border-border-light overflow-hidden">
          <div className="p-4 border-b border-border-light flex items-center justify-between">
            <h3 className="text-sm font-bold flex items-center gap-2">
              <span className="w-1 h-4 bg-primary-container rounded-full"></span>
              互动时间线
            </h3>
            <button
              onClick={() => setShowAddActivity(true)}
              className="flex items-center gap-1 text-primary-container text-xs font-bold active:opacity-70"
            >
              <Plus className="w-4 h-4" />
              添加活动
            </button>
          </div>

          {showAddActivity && (
            <div className="p-4 border-b border-border-light bg-sky-50/50 space-y-3">
              <div>
                <label className="text-xs font-bold text-slate-500 mb-1 block">活动类型</label>
                <select
                  value={newActivity.action_type}
                  onChange={e => setNewActivity(prev => ({ ...prev, action_type: e.target.value }))}
                  className="w-full text-sm border border-border-light rounded-lg px-3 py-2 bg-white outline-none"
                >
                  {Object.entries(ACTION_TYPE_LABELS).map(([k, v]) => (
                    <option key={k} value={k}>{v}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="text-xs font-bold text-slate-500 mb-1 block">概要</label>
                <input
                  value={newActivity.summary}
                  onChange={e => setNewActivity(prev => ({ ...prev, summary: e.target.value }))}
                  className="w-full text-sm border border-border-light rounded-lg px-3 py-2 bg-white outline-none focus:ring-1 focus:ring-primary-container"
                  placeholder="简单描述..."
                />
              </div>
              <div>
                <label className="text-xs font-bold text-slate-500 mb-1 block">详情（可选）</label>
                <textarea
                  value={newActivity.detail}
                  onChange={e => setNewActivity(prev => ({ ...prev, detail: e.target.value }))}
                  rows={2}
                  className="w-full text-sm border border-border-light rounded-lg px-3 py-2 bg-white outline-none focus:ring-1 focus:ring-primary-container resize-none"
                  placeholder="详细内容..."
                />
              </div>
              <div className="flex gap-2">
                <button
                  onClick={handleAddActivity}
                  className="flex-1 py-2 bg-primary-container text-white rounded-lg text-xs font-bold active:scale-95 transition-transform"
                >
                  保存
                </button>
                <button
                  onClick={() => setShowAddActivity(false)}
                  className="px-4 py-2 bg-white border border-border-light rounded-lg text-xs font-bold text-slate-500 active:scale-95 transition-transform"
                >
                  取消
                </button>
              </div>
            </div>
          )}

          {activities.length === 0 ? (
            <div className="p-8 text-center text-sm text-text-muted">暂无互动记录</div>
          ) : (
            <div className="relative">
              {/* Timeline line */}
              <div className="absolute left-7 top-0 bottom-0 w-0.5 bg-slate-100" />

              <div className="space-y-0">
                {activities.map((act) => (
                  <div key={act.id} className="relative flex gap-4 px-4 py-3">
                    {/* Dot */}
                    <div className="relative z-10 mt-1">
                      <div className="w-4 h-4 rounded-full bg-sky-100 flex items-center justify-center">
                        <div className="w-2 h-2 rounded-full bg-primary-container" />
                      </div>
                    </div>
                    {/* Content */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-bold text-primary-container">
                          {ACTION_TYPE_LABELS[act.action_type] || act.action_type}
                        </span>
                        <span className="text-[10px] text-text-muted">{formatDateTime(act.created_at)}</span>
                      </div>
                      {act.summary && (
                        <p className="text-sm text-on-surface mt-1">{act.summary}</p>
                      )}
                      {act.detail && (
                        <p className="text-xs text-text-muted mt-0.5">{act.detail}</p>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
