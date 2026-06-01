import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Calendar, Clock, MapPin, Users, ChevronLeft, Video,
  CheckCircle, AlertCircle, Star, Send, X, Loader2
} from 'lucide-react';

interface MatchingEvent {
  id: number;
  title: string;
  description: string;
  cover_image: string | null;
  event_date: string;
  end_date: string | null;
  location: string;
  max_participants: number;
  current_participants: number;
  price: number;
  status: string;
  tags: string[];
  is_registered?: boolean;
}

export default function MatchingEventsPage() {
  const navigate = useNavigate();
  const [events, setEvents] = useState<MatchingEvent[]>([]);
  const [selectedEvent, setSelectedEvent] = useState<MatchingEvent | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [registering, setRegistering] = useState(false);
  const [registerMsg, setRegisterMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [showFeedback, setShowFeedback] = useState(false);
  const [feedbackRating, setFeedbackRating] = useState(5);
  const [feedbackComment, setFeedbackComment] = useState('');
  const [feedbackMsg, setFeedbackMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [submittingFeedback, setSubmittingFeedback] = useState(false);

  useEffect(() => {
    fetchEvents();
  }, []);

  async function fetchEvents() {
    setLoading(true);
    setError('');
    try {
      const token = localStorage.getItem('token');
      const res = await fetch('/api/v1/events/online?page_size=50', {
        headers: { Authorization: `Bearer ${token}` },
      });
      const json = await res.json();
      if (json.code === 200) {
        setEvents(json.data);
      } else {
        setError(json.message || '加载失败');
      }
    } catch {
      setError('网络错误，请稍后重试');
    } finally {
      setLoading(false);
    }
  }

  async function handleRegister(eventId: number) {
    setRegistering(true);
    setRegisterMsg(null);
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`/api/v1/events/online/${eventId}/register`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({}),
      });
      const json = await res.json();
      if (json.code === 200) {
        setRegisterMsg({ type: 'success', text: '报名成功！我们将通过您注册的手机号联系您。' });
        fetchEvents();
      } else {
        setRegisterMsg({ type: 'error', text: json.detail || json.message || '报名失败' });
      }
    } catch {
      setRegisterMsg({ type: 'error', text: '网络错误，请稍后重试' });
    } finally {
      setRegistering(false);
    }
  }

  async function handleSubmitFeedback(eventId: number) {
    setSubmittingFeedback(true);
    setFeedbackMsg(null);
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`/api/v1/events/online/${eventId}/feedback`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ rating: feedbackRating, comment: feedbackComment || undefined }),
      });
      const json = await res.json();
      if (json.code === 200) {
        setFeedbackMsg({ type: 'success', text: '反馈提交成功，感谢您的参与！' });
        setShowFeedback(false);
        setFeedbackComment('');
        setFeedbackRating(5);
      } else {
        setFeedbackMsg({ type: 'error', text: json.detail || json.message || '提交失败' });
      }
    } catch {
      setFeedbackMsg({ type: 'error', text: '网络错误，请稍后重试' });
    } finally {
      setSubmittingFeedback(false);
    }
  }

  function formatDate(iso: string) {
    const d = new Date(iso);
    return d.toLocaleDateString('zh-CN', {
      year: 'numeric', month: 'long', day: 'numeric', weekday: 'long',
    });
  }

  function formatTime(iso: string) {
    const d = new Date(iso);
    return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
  }

  function statusBadge(status: string) {
    const map: Record<string, { label: string; color: string }> = {
      draft: { label: '草稿', color: 'bg-slate-100 text-slate-600' },
      published: { label: '报名中', color: 'bg-emerald-100 text-emerald-700' },
      ongoing: { label: '进行中', color: 'bg-blue-100 text-blue-700' },
      completed: { label: '已结束', color: 'bg-slate-100 text-slate-500' },
      cancelled: { label: '已取消', color: 'bg-red-100 text-red-600' },
    };
    const m = map[status] || { label: status, color: 'bg-slate-100 text-slate-600' };
    return <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${m.color}`}>{m.label}</span>;
  }

  return (
    <div className="flex flex-col min-h-screen bg-gradient-to-b from-indigo-50/30 via-white to-white font-sans pb-12">
      {/* Header */}
      <header className="sticky top-0 z-50 bg-white/80 backdrop-blur-xl border-b border-indigo-100/50 flex items-center gap-3 px-4 h-16">
        <button
          onClick={() => navigate(-1)}
          className="w-8 h-8 rounded-full bg-slate-50 flex items-center justify-center text-slate-500 hover:bg-indigo-50 hover:text-indigo-600 active:scale-90 transition-all"
        >
          <ChevronLeft className="w-5 h-5" />
        </button>
        <h1 className="font-manrope text-lg font-extrabold bg-gradient-to-r from-indigo-600 to-violet-600 bg-clip-text text-transparent">
          线上闭门对接会
        </h1>
      </header>

      <main className="max-w-3xl mx-auto w-full p-4 space-y-4">
        {/* Hero Banner */}
        <div className="relative w-full aspect-[21/8] rounded-2xl overflow-hidden bg-gradient-to-br from-indigo-500 via-purple-600 to-violet-700 shadow-lg">
          <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,rgba(255,255,255,0.15),transparent_60%)]" />
          <div className="absolute inset-0 flex flex-col justify-center px-6">
            <div className="flex items-center gap-2 mb-1">
              <Video className="w-5 h-5 text-indigo-200" />
              <span className="text-white/80 text-[10px] font-bold">钻石会员专享</span>
            </div>
            <h2 className="text-white font-bold text-2xl leading-tight">线上闭门对接会</h2>
            <p className="text-white/70 text-xs mt-1 max-w-xs">
              腾讯会议/飞书线上进行，与优质企业家一对一精准对接
            </p>
          </div>
        </div>

        {/* Error */}
        {error && (
          <div className="flex items-center gap-2 p-3 bg-red-50 border border-red-100 rounded-xl text-red-600 text-xs">
            <AlertCircle className="w-4 h-4 shrink-0" />
            {error}
          </div>
        )}

        {/* Loading */}
        {loading && (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="w-6 h-6 text-indigo-500 animate-spin" />
          </div>
        )}

        {/* Register Message */}
        {registerMsg && (
          <div className={`flex items-center gap-2 p-3 rounded-xl text-xs ${
            registerMsg.type === 'success'
              ? 'bg-emerald-50 border border-emerald-100 text-emerald-700'
              : 'bg-red-50 border border-red-100 text-red-600'
          }`}>
            {registerMsg.type === 'success' ? <CheckCircle className="w-4 h-4 shrink-0" /> : <AlertCircle className="w-4 h-4 shrink-0" />}
            {registerMsg.text}
          </div>
        )}

        {/* Feedback Message */}
        {feedbackMsg && (
          <div className={`flex items-center gap-2 p-3 rounded-xl text-xs ${
            feedbackMsg.type === 'success'
              ? 'bg-emerald-50 border border-emerald-100 text-emerald-700'
              : 'bg-red-50 border border-red-100 text-red-600'
          }`}>
            {feedbackMsg.type === 'success' ? <CheckCircle className="w-4 h-4 shrink-0" /> : <AlertCircle className="w-4 h-4 shrink-0" />}
            {feedbackMsg.text}
          </div>
        )}

        {/* Event List */}
        {!loading && events.length === 0 && (
          <div className="text-center py-12 text-slate-400">
            <Calendar className="w-12 h-12 mx-auto mb-3 opacity-50" />
            <p className="text-sm">暂无近期对接会</p>
            <p className="text-xs mt-1">敬请期待下一场闭门对接会</p>
          </div>
        )}

        {events.map((event) => (
          <div
            key={event.id}
            className="bg-white rounded-2xl border border-slate-100 shadow-sm overflow-hidden hover:shadow-md transition-shadow"
          >
            {/* Cover */}
            {event.cover_image && (
              <div className="w-full h-36 overflow-hidden bg-slate-100">
                <img
                  src={event.cover_image}
                  alt={event.title}
                  className="w-full h-full object-cover"
                  onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
                />
              </div>
            )}

            <div className="p-4 space-y-3">
              {/* Title + Status */}
              <div className="flex items-start justify-between gap-2">
                <h3 className="font-bold text-slate-800 text-sm leading-tight">{event.title}</h3>
                {statusBadge(event.status)}
              </div>

              {/* Description */}
              {event.description && (
                <p className="text-xs text-slate-500 leading-relaxed line-clamp-2">{event.description}</p>
              )}

              {/* Info Row */}
              <div className="flex flex-wrap gap-x-4 gap-y-1.5 text-[11px] text-slate-500">
                <div className="flex items-center gap-1">
                  <Calendar className="w-3.5 h-3.5 text-indigo-400" />
                  {formatDate(event.event_date)}
                </div>
                <div className="flex items-center gap-1">
                  <Clock className="w-3.5 h-3.5 text-indigo-400" />
                  {formatTime(event.event_date)}
                </div>
                <div className="flex items-center gap-1">
                  <MapPin className="w-3.5 h-3.5 text-indigo-400" />
                  {event.location || '线上（腾讯会议/飞书）'}
                </div>
                <div className="flex items-center gap-1">
                  <Users className="w-3.5 h-3.5 text-indigo-400" />
                  {event.current_participants}/{event.max_participants}人
                </div>
              </div>

              {/* Tags */}
              {event.tags.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {event.tags.map((tag, i) => (
                    <span key={i} className="text-[9px] bg-indigo-50 text-indigo-600 px-2 py-0.5 rounded-full font-medium">
                      {tag}
                    </span>
                  ))}
                </div>
              )}

              {/* Actions */}
              <div className="flex items-center gap-2 pt-1">
                {event.status === 'published' && !event.is_registered && (
                  <button
                    onClick={() => handleRegister(event.id)}
                    disabled={registering}
                    className="flex-1 py-2.5 rounded-xl bg-gradient-to-r from-indigo-500 to-violet-600 text-white text-xs font-bold active:scale-[0.97] transition-transform disabled:opacity-50 disabled:cursor-not-allowed shadow-sm"
                  >
                    {registering ? '报名中...' : '立即报名'}
                  </button>
                )}
                {event.is_registered && (
                  <div className="flex-1 flex items-center gap-2">
                    <div className="flex-1 py-2 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-700 text-xs font-bold text-center">
                      <CheckCircle className="w-3.5 h-3.5 inline-block mr-1" />
                      已报名
                    </div>
                    {event.status === 'completed' && (
                      <button
                        onClick={() => { setSelectedEvent(event); setShowFeedback(true); }}
                        className="py-2 px-4 rounded-xl bg-amber-50 border border-amber-200 text-amber-700 text-xs font-bold active:scale-[0.97] transition-transform"
                      >
                        <Star className="w-3.5 h-3.5 inline-block mr-1" />
                        反馈
                      </button>
                    )}
                  </div>
                )}
              </div>
            </div>
          </div>
        ))}
      </main>

      {/* Feedback Modal */}
      {showFeedback && selectedEvent && (
        <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl w-full max-w-sm p-5 shadow-xl animate-in fade-in zoom-in">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-bold text-slate-800 text-sm">提交反馈</h3>
              <button
                onClick={() => { setShowFeedback(false); setFeedbackMsg(null); }}
                className="w-7 h-7 rounded-full bg-slate-100 flex items-center justify-center text-slate-400"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <p className="text-xs text-slate-500 mb-3">{selectedEvent.title}</p>

            {/* Rating */}
            <div className="flex items-center gap-1 mb-4">
              {[1, 2, 3, 4, 5].map((star) => (
                <button
                  key={star}
                  onClick={() => setFeedbackRating(star)}
                  className="p-1"
                >
                  <Star
                    className={`w-6 h-6 ${star <= feedbackRating ? 'text-amber-400 fill-amber-400' : 'text-slate-200'}`}
                  />
                </button>
              ))}
              <span className="text-xs text-slate-400 ml-2">{feedbackRating}分</span>
            </div>

            {/* Comment */}
            <textarea
              value={feedbackComment}
              onChange={(e) => setFeedbackComment(e.target.value)}
              placeholder="分享您的参会体验和建议..."
              className="w-full h-24 resize-none rounded-xl border border-slate-200 p-3 text-xs text-slate-700 placeholder-slate-300 focus:outline-none focus:border-indigo-300 focus:ring-1 focus:ring-indigo-200"
            />

            <button
              onClick={() => handleSubmitFeedback(selectedEvent.id)}
              disabled={submittingFeedback}
              className="w-full mt-3 py-2.5 rounded-xl bg-gradient-to-r from-indigo-500 to-violet-600 text-white text-xs font-bold active:scale-[0.97] transition-transform disabled:opacity-50 disabled:cursor-not-allowed shadow-sm flex items-center justify-center gap-1.5"
            >
              {submittingFeedback ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Send className="w-4 h-4" />
              )}
              提交反馈
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
