import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Search, List, Grid3X3, Upload, Edit3, Trash2, ChevronLeft, ChevronRight, Tag, User, Phone, Building2, Calendar, ArrowUpDown } from 'lucide-react';
import { api } from '../api/client';
import { Contact, ContactListResponse } from '../types';
import { Loading, ErrorBlock, Empty } from '../components/StatusComponents';

const PAGE_SIZE = 20;

export default function ContactsPage() {
  const navigate = useNavigate();
  const [viewMode, setViewMode] = useState<'card' | 'table'>('card');
  const [search, setSearch] = useState('');
  const [searchInput, setSearchInput] = useState('');
  const [tags, setTags] = useState('');
  const [page, setPage] = useState(1);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [total, setTotal] = useState(0);
  const [status, setStatus] = useState<'loading' | 'error' | 'success'>('loading');
  const [error, setError] = useState('');
  const [availableTags, setAvailableTags] = useState<string[]>([]);
  const [showTagFilter, setShowTagFilter] = useState(false);

  const fetchContacts = useCallback(async () => {
    setStatus('loading');
    try {
      const params = new URLSearchParams();
      if (search) params.set('search', search);
      if (tags) params.set('tags', tags);
      params.set('page', String(page));
      params.set('page_size', String(PAGE_SIZE));
      const res = await api.get<ContactListResponse>(`/api/contacts?${params}`);
      if (res.data) {
        setContacts(res.data.items);
        setTotal(res.data.total);
      }
      setStatus('success');
    } catch (e: any) {
      setError(e.message || '加载失败');
      setStatus('error');
    }
  }, [search, tags, page]);

  useEffect(() => { fetchContacts(); }, [fetchContacts]);

  useEffect(() => {
    api.get<{ tags: string[] }>('/api/contacts/tags').then(r => {
      if (r.data?.tags) setAvailableTags(r.data.tags);
    }).catch(() => {});
  }, []);

  const handleSearchKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      setSearch(searchInput);
      setPage(1);
    }
  };

  const totalPages = Math.ceil(total / PAGE_SIZE);

  const handleDelete = async (id: number) => {
    if (!confirm('确定删除此联系人？')) return;
    try {
      await api.post(`/api/contacts/${id}/delete`, {});
      fetchContacts();
    } catch (e: any) {
      alert('删除失败：' + (e.message || '未知错误'));
    }
  };

  const toggleTag = (tag: string) => {
    const currentTags = tags ? tags.split(',') : [];
    const idx = currentTags.indexOf(tag);
    if (idx >= 0) {
      currentTags.splice(idx, 1);
    } else {
      currentTags.push(tag);
    }
    setTags(currentTags.join(','));
    setPage(1);
  };

  return (
    <div className="flex flex-col min-h-screen bg-neutral-bg font-sans pb-20">
      <header className="fixed top-0 w-full z-50 bg-neutral-bg border-b border-border-light flex items-center justify-between px-4 h-16">
        <div className="flex items-center gap-3">
          <button onClick={() => navigate(-1)} className="text-slate-600">
            <ChevronLeft className="w-6 h-6" />
          </button>
          <h1 className="font-manrope text-lg font-bold text-primary-container">人脉管理</h1>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => navigate('/contacts/import', { state: { transition: 'push' } })}
            className="flex items-center gap-1 bg-primary-container text-white px-3 py-1.5 rounded-xl text-xs font-bold active:scale-95 transition-transform"
          >
            <Upload className="w-4 h-4" />
            导入
          </button>
          <button
            onClick={() => setViewMode(viewMode === 'card' ? 'table' : 'card')}
            className="p-2 rounded-xl bg-white border border-border-light text-slate-600 active:scale-95 transition-transform"
          >
            {viewMode === 'card' ? <List className="w-5 h-5" /> : <Grid3X3 className="w-5 h-5" />}
          </button>
        </div>
      </header>

      <main className="pt-16">
        {/* Search */}
        <div className="p-4 pb-2">
          <div className="relative flex items-center">
            <Search className="absolute left-3 text-slate-400 w-5 h-5" />
            <input
              value={searchInput}
              onChange={e => setSearchInput(e.target.value)}
              onKeyDown={handleSearchKeyDown}
              className="w-full bg-white border border-border-light rounded-xl py-2.5 pl-10 pr-4 text-sm outline-none focus:ring-1 focus:ring-primary-container"
              placeholder="搜索姓名、电话、公司..."
            />
          </div>
        </div>

        {/* Tags */}
        <div className="px-4 pb-3">
          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowTagFilter(!showTagFilter)}
              className={`flex items-center gap-1 px-3 py-1.5 rounded-full text-xs font-bold border transition-all ${
                showTagFilter ? 'bg-primary-container text-white border-primary-container' : 'bg-white text-slate-500 border-border-light'
              }`}
            >
              <Tag className="w-3.5 h-3.5" />
              标签
            </button>
            {tags && (
              <button
                onClick={() => { setTags(''); setPage(1); }}
                className="text-xs text-slate-400 underline"
              >
                清除筛选
              </button>
            )}
          </div>
          {showTagFilter && availableTags.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-2">
              {availableTags.map(tag => {
                const selected = tags.split(',').includes(tag);
                return (
                  <button
                    key={tag}
                    onClick={() => toggleTag(tag)}
                    className={`px-2.5 py-1 rounded-full text-xs font-medium border transition-all ${
                      selected ? 'bg-primary-container text-white border-primary-container' : 'bg-white text-slate-600 border-border-light'
                    }`}
                  >
                    {tag}
                  </button>
                );
              })}
            </div>
          )}
        </div>

        {/* Content */}
        {status === 'loading' ? (
          <Loading />
        ) : status === 'error' ? (
          <ErrorBlock message={error} onRetry={fetchContacts} />
        ) : contacts.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 px-6">
            <div className="w-28 h-28 bg-gradient-to-br from-violet-100 to-purple-50 rounded-3xl flex items-center justify-center mb-6 shadow-lg shadow-violet-100/50 border border-violet-100">
              <svg className="w-14 h-14 text-violet-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.5">
                <path strokeLinecap="round" strokeLinejoin="round" d="M15 19.128a9.38 9.38 0 0 0 2.625.372 9.337 9.337 0 0 0 4.121-.952 4.125 4.125 0 0 0-7.533-2.493M15 19.128v-.003c0-1.113-.285-2.16-.786-3.07M15 19.128v.106A12.318 12.318 0 0 1 8.624 21c-2.331 0-4.512-.645-6.374-1.766l-.001-.109a6.375 6.375 0 0 1 11.964-3.07M12 6.375a3.375 3.375 0 1 1-6.75 0 3.375 3.375 0 0 1 6.75 0Zm8.25 2.25a2.625 2.625 0 1 1-5.25 0 2.625 2.625 0 0 1 5.25 0Z" />
              </svg>
            </div>
            <h3 className="text-xl font-extrabold text-slate-800 mb-3">还没有联系人</h3>
            <p className="text-sm text-slate-400 mb-8 text-center max-w-[280px] leading-relaxed">导入或添加联系人，开启你的人际网络管理</p>
            <button
              onClick={() => navigate('/contacts/import')}
              className="px-8 py-3 bg-gradient-to-r from-violet-500 to-purple-600 text-white text-sm font-extrabold rounded-2xl shadow-lg shadow-violet-500/25 hover:shadow-xl hover:shadow-violet-500/30 active:scale-95 transition-all"
            >
              去导入联系人
            </button>
          </div>
        ) : (
          <>
            <div className="px-4 pb-2 flex items-center justify-between">
              <span className="text-xs text-text-muted">共 {total} 位联系人</span>
              <button
                onClick={() => navigate('/contacts/merge', { state: { transition: 'push' } })}
                className="text-xs text-primary-container font-bold active:opacity-70"
              >
                去重合并
              </button>
            </div>

            {viewMode === 'card' ? (
              <div className="px-4 space-y-3">
                {contacts.map(c => (
                  <div
                    key={c.id}
                    onClick={() => navigate(`/contacts/${c.id}`, { state: { transition: 'push' } })}
                    className="bg-white rounded-2xl border border-border-light p-4 active:scale-[0.98] transition-transform cursor-pointer"
                  >
                    <div className="flex items-start gap-3">
                      <div className="w-12 h-12 rounded-full bg-sky-50 flex items-center justify-center shrink-0 overflow-hidden">
                        {c.avatar ? (
                          <img src={c.avatar} className="w-full h-full object-cover" />
                        ) : (
                          <User className="w-6 h-6 text-primary-container" />
                        )}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between">
                          <h3 className="font-bold text-sm truncate">{c.name}</h3>
                          <div className="flex items-center gap-1 shrink-0">
                            <button
                              onClick={e => { e.stopPropagation(); navigate(`/contacts/${c.id}?edit=1`, { state: { transition: 'push' } }); }}
                              className="p-1.5 rounded-lg text-slate-400 hover:bg-slate-100 active:scale-90 transition-all"
                            >
                              <Edit3 className="w-4 h-4" />
                            </button>
                            <button
                              onClick={e => { e.stopPropagation(); handleDelete(c.id); }}
                              className="p-1.5 rounded-lg text-slate-400 hover:bg-red-50 hover:text-red-500 active:scale-90 transition-all"
                            >
                              <Trash2 className="w-4 h-4" />
                            </button>
                          </div>
                        </div>
                        <div className="mt-1.5 space-y-1">
                          {c.phone && (
                            <div className="flex items-center gap-1.5 text-xs text-slate-500">
                              <Phone className="w-3.5 h-3.5" />
                              {c.phone}
                            </div>
                          )}
                          {c.company && (
                            <div className="flex items-center gap-1.5 text-xs text-slate-500">
                              <Building2 className="w-3.5 h-3.5" />
                              {c.company}{c.position ? ` · ${c.position}` : ''}
                            </div>
                          )}
                        </div>
                        {c.tags && c.tags.length > 0 && (
                          <div className="mt-2 flex flex-wrap gap-1.5">
                            {c.tags.map((tag, i) => (
                              <span key={i} className="text-[10px] bg-sky-50 text-primary-container px-2 py-0.5 rounded-full font-medium">
                                {tag}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="px-4">
                <div className="bg-white rounded-2xl border border-border-light overflow-hidden">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-border-light bg-slate-50">
                        <th className="text-left py-3 px-4 text-xs font-bold text-text-muted">姓名</th>
                        <th className="text-left py-3 px-4 text-xs font-bold text-text-muted">电话</th>
                        <th className="text-left py-3 px-4 text-xs font-bold text-text-muted hidden sm:table-cell">公司</th>
                        <th className="text-left py-3 px-4 text-xs font-bold text-text-muted hidden md:table-cell">标签</th>
                        <th className="text-right py-3 px-4 text-xs font-bold text-text-muted">操作</th>
                      </tr>
                    </thead>
                    <tbody>
                      {contacts.map(c => (
                        <tr
                          key={c.id}
                          onClick={() => navigate(`/contacts/${c.id}`, { state: { transition: 'push' } })}
                          className="border-b border-border-light last:border-b-0 cursor-pointer active:bg-slate-50"
                        >
                          <td className="py-3 px-4">
                            <div className="flex items-center gap-2">
                              <div className="w-8 h-8 rounded-full bg-sky-50 flex items-center justify-center text-xs font-bold text-primary-container shrink-0">
                                {c.name[0]}
                              </div>
                              <span className="font-medium">{c.name}</span>
                            </div>
                          </td>
                          <td className="py-3 px-4 text-slate-500 text-xs">{c.phone || '-'}</td>
                          <td className="py-3 px-4 text-slate-500 text-xs hidden sm:table-cell">{c.company || '-'}</td>
                          <td className="py-3 px-4 hidden md:table-cell">
                            {c.tags?.slice(0, 2).map((t, i) => (
                              <span key={i} className="text-[10px] bg-sky-50 text-primary-container px-1.5 py-0.5 rounded mr-1">{t}</span>
                            ))}
                          </td>
                          <td className="py-3 px-4 text-right">
                            <button
                              onClick={e => { e.stopPropagation(); handleDelete(c.id); }}
                              className="p-1 rounded text-slate-400 hover:text-red-500"
                            >
                              <Trash2 className="w-4 h-4" />
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="flex items-center justify-center gap-4 py-6">
                <button
                  onClick={() => setPage(p => Math.max(1, p - 1))}
                  disabled={page <= 1}
                  className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-white border border-border-light text-xs font-bold disabled:opacity-30 active:scale-95 transition-all"
                >
                  <ChevronLeft className="w-4 h-4" />
                  上一页
                </button>
                <span className="text-xs text-text-muted">
                  {page} / {totalPages}
                </span>
                <button
                  onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                  disabled={page >= totalPages}
                  className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-white border border-border-light text-xs font-bold disabled:opacity-30 active:scale-95 transition-all"
                >
                  下一页
                  <ChevronRight className="w-4 h-4" />
                </button>
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}
