import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api/client';

const ArrowLeft = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M15 18l-6-6 6-6" />
  </svg>
);

const CATEGORIES = ['大健康', '企业服务', '科技产品', '教育培训', '消费品'];

export function PostNeed() {
  const navigate = useNavigate();
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [category, setCategory] = useState('');
  const [budget, setBudget] = useState('');
  const [region, setRegion] = useState('');
  const [contactName, setContactName] = useState('');
  const [contactPhone, setContactPhone] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async () => {
    setError('');

    if (!title.trim()) { setError('请填写需求标题'); return; }
    if (!contactName.trim()) { setError('请填写联系人'); return; }

    setSubmitting(true);
    try {
      const res = await api.post('/api/needs', {
        title: title.trim(),
        description: description.trim() || undefined,
        category: category || undefined,
        budget: budget.trim() || undefined,
        region: region.trim() || undefined,
        contact_name: contactName.trim(),
        contact_phone: contactPhone.trim() || undefined,
      });
      setSubmitting(false);

      if (res.code === 200) {
        navigate('/supply-demand', { state: { transition: 'push_back' } });
      } else {
        setError(res.message || '发布失败，请重试');
      }
    } catch (e: any) {
      setSubmitting(false);
      setError(e.message || '网络错误，请稍后重试');
    }
  };

  return (
    <div className="flex flex-col min-h-screen bg-gradient-to-b from-sky-50/50 via-white to-white font-sans pb-24">
      {/* Header */}
      <header className="sky-gradient px-4 pt-12 pb-6 relative overflow-hidden">
        <div className="absolute inset-0 opacity-10">
          <div className="bubble w-72 h-72 bg-white -top-20 -right-20" />
          <div className="bubble w-48 h-48 bg-white bottom-0 left-10" />
        </div>
        <div className="flex items-center gap-3 relative z-10">
          <button onClick={() => navigate(-1)} className="w-9 h-9 flex items-center justify-center rounded-xl bg-white/20 text-white active:scale-90 transition-all">
            <ArrowLeft />
          </button>
          <div>
            <h1 className="text-xl font-extrabold text-white font-manrope">发布需求</h1>
            <p className="text-xs text-white/70">填写商机信息，快速对接合作伙伴</p>
          </div>
        </div>
      </header>

      <div className="px-4 -mt-3 space-y-4">
        {/* Error message */}
        {error && (
          <div className="bg-rose-50 border border-rose-200 rounded-2xl px-4 py-3 text-sm text-rose-600">
            {error}
          </div>
        )}

        {/* Title */}
        <div className="bg-white rounded-2xl p-5 border border-slate-100 shadow-sm">
          <label className="text-xs font-bold text-slate-500 mb-2 block">需求标题 *</label>
          <input
            type="text"
            placeholder="例如：寻找大健康产品供应链合作伙伴"
            value={title}
            onChange={e => setTitle(e.target.value)}
            maxLength={200}
            className="w-full text-sm text-slate-800 placeholder-slate-300 border-0 outline-none bg-transparent"
          />
          <div className="text-right text-[10px] text-slate-400 mt-1">{title.length}/200</div>
        </div>

        {/* Category */}
        <div className="bg-white rounded-2xl p-5 border border-slate-100 shadow-sm">
          <label className="text-xs font-bold text-slate-500 mb-3 block">需求品类</label>
          <div className="flex flex-wrap gap-2">
            {CATEGORIES.map(cat => (
              <button
                key={cat}
                onClick={() => setCategory(category === cat ? '' : cat)}
                className={`px-4 py-1.5 rounded-full text-sm font-medium transition-all ${
                  category === cat
                    ? 'bg-rose-500 text-white shadow-md shadow-rose-500/20'
                    : 'bg-slate-50 text-slate-500 hover:bg-slate-100'
                }`}
              >
                {cat}
              </button>
            ))}
          </div>
        </div>

        {/* Description */}
        <div className="bg-white rounded-2xl p-5 border border-slate-100 shadow-sm">
          <label className="text-xs font-bold text-slate-500 mb-2 block">需求描述</label>
          <textarea
            placeholder="请详细描述您的需求，包括具体要求、期望合作方式等..."
            value={description}
            onChange={e => setDescription(e.target.value)}
            rows={5}
            className="w-full text-sm text-slate-800 placeholder-slate-300 border-0 outline-none bg-transparent resize-none"
          />
        </div>

        {/* Budget & Region */}
        <div className="grid grid-cols-2 gap-3">
          <div className="bg-white rounded-2xl p-5 border border-slate-100 shadow-sm">
            <label className="text-xs font-bold text-slate-500 mb-2 block">预算范围</label>
            <input
              type="text"
              placeholder="面议"
              value={budget}
              onChange={e => setBudget(e.target.value)}
              className="w-full text-sm text-slate-800 placeholder-slate-300 border-0 outline-none bg-transparent"
            />
          </div>
          <div className="bg-white rounded-2xl p-5 border border-slate-100 shadow-sm">
            <label className="text-xs font-bold text-slate-500 mb-2 block">所在地区</label>
            <input
              type="text"
              placeholder="如：北京"
              value={region}
              onChange={e => setRegion(e.target.value)}
              className="w-full text-sm text-slate-800 placeholder-slate-300 border-0 outline-none bg-transparent"
            />
          </div>
        </div>

        {/* Contact */}
        <div className="bg-white rounded-2xl p-5 border border-slate-100 shadow-sm">
          <label className="text-xs font-bold text-slate-500 mb-3 block">联系方式</label>
          <div className="space-y-3">
            <input
              type="text"
              placeholder="联系人 *"
              value={contactName}
              onChange={e => setContactName(e.target.value)}
              className="w-full text-sm text-slate-800 placeholder-slate-300 border-0 outline-none bg-transparent pb-3 border-b border-slate-100"
            />
            <input
              type="tel"
              placeholder="联系电话"
              value={contactPhone}
              onChange={e => setContactPhone(e.target.value)}
              className="w-full text-sm text-slate-800 placeholder-slate-300 border-0 outline-none bg-transparent"
            />
          </div>
        </div>

        {/* Submit */}
        <button
          onClick={handleSubmit}
          disabled={submitting}
          className="w-full py-4 rounded-2xl bg-gradient-to-r from-rose-500 to-pink-600 text-white font-bold text-base shadow-xl shadow-rose-500/30 active:scale-[0.98] transition-all disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {submitting ? '发布中...' : '确认发布需求'}
        </button>
      </div>
    </div>
  );
}
