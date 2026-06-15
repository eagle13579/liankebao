/**
 * X1-X10 心智模型注入 — 科学学习中心（前端）
 * ============================================
 * 链客宝用户侧知识推送与学习路径功能。
 * 后端 API: /api/learning/*
 */
import React, { useCallback, useEffect, useState } from 'react';

const API_BASE = '/api/learning';

interface ModuleItem {
  key: string;
  name: string;
  description: string;
}

interface ArticleItem {
  id: number;
  title: string;
  summary: string | null;
  category: string;
  tags: string | null;
  difficulty: string;
  read_time_minutes: number;
  related_module: string | null;
  view_count: number;
  like_count: number;
  created_at: string;
}

interface ArticleDetail extends ArticleItem {
  content: string;
  source: string | null;
  author_name: string | null;
}

interface PathItem {
  id: number;
  name: string;
  description: string | null;
  category: string;
  difficulty: string;
  article_count: number;
  estimated_hours: number;
}

interface UserProgress {
  total_assigned: number;
  completed: number;
  in_progress: number;
  bookmarked: number;
  completion_rate: number;
  recent_articles: Array<{ article_id: number; title: string; category: string; status: string; updated_at: string | null }>;
}

interface DailyRecommend {
  id: number;
  title: string;
  summary: string | null;
  category: string;
  difficulty: string;
  read_time_minutes: number;
  related_module: string | null;
}

async function apiGet<T>(url: string): Promise<T> {
  const t = localStorage.getItem('token') || '';
  return fetch(url, { headers: { 'Content-Type': 'application/json', ...(t ? { Authorization: `Bearer ${t}` } : {}) } }).then(r => r.json());
}
async function apiPost(url: string, body?: unknown): Promise<{ code: number; message?: string }> {
  const t = localStorage.getItem('token') || '';
  return fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json', ...(t ? { Authorization: `Bearer ${t}` } : {}) }, body: body ? JSON.stringify(body) : undefined }).then(r => r.json());
}
async function apiPut(url: string, body: unknown): Promise<{ code: number }> {
  const t = localStorage.getItem('token') || '';
  return fetch(url, { method: 'PUT', headers: { 'Content-Type': 'application/json', ...(t ? { Authorization: `Bearer ${t}` } : {}) }, body: JSON.stringify(body) }).then(r => r.json());
}

const DIFFICULTY_MAP: Record<string, { label: string; cls: string }> = {
  beginner: { label: '入门', cls: 'bg-emerald-100 text-emerald-700' },
  intermediate: { label: '进阶', cls: 'bg-amber-100 text-amber-700' },
  advanced: { label: '高级', cls: 'bg-rose-100 text-rose-700' },
};

export default function LearningCenterPage() {
  const [tab, setTab] = useState<'recommend' | 'articles' | 'paths' | 'progress' | 'modules'>('recommend');
  const [modules, setModules] = useState<ModuleItem[]>([]);
  const [articles, setArticles] = useState<ArticleItem[]>([]);
  const [article, setArticle] = useState<ArticleDetail | null>(null);
  const [paths, setPaths] = useState<PathItem[]>([]);
  const [progress, setProgress] = useState<UserProgress | null>(null);
  const [recommend, setRecommend] = useState<DailyRecommend[]>([]);
  const [loading, setLoading] = useState(true);
  const [category, setCategory] = useState('');
  const [difficulty, setDifficulty] = useState('');
  const [error, setError] = useState('');

  const loadModules = useCallback(async () => {
    const res = await apiGet<{ code: number; data: { modules: ModuleItem[] } }>(`${API_BASE}/modules`);
    if (res.code === 200) setModules(res.data.modules);
  }, []);

  const loadArticles = useCallback(async () => {
    setLoading(true);
    const params = new URLSearchParams();
    if (category) params.set('category', category);
    if (difficulty) params.set('difficulty', difficulty);
    params.set('page_size', '50');
    const res = await apiGet<{ code: number; data: { items: ArticleItem[] } }>(`${API_BASE}/articles?${params}`);
    if (res.code === 200) setArticles(res.data.items);
    setLoading(false);
  }, [category, difficulty]);

  const loadPaths = useCallback(async () => {
    setLoading(true);
    const res = await apiGet<{ code: number; data: PathItem[] }>(`${API_BASE}/paths`);
    if (res.code === 200) setPaths(res.data);
    setLoading(false);
  }, []);

  const loadProgress = useCallback(async () => {
    setLoading(true);
    const res = await apiGet<{ code: number; data: UserProgress }>(`${API_BASE}/progress`);
    if (res.code === 200) setProgress(res.data);
    setLoading(false);
  }, []);

  const loadRecommend = useCallback(async () => {
    setLoading(true);
    const res = await apiGet<{ code: number; data: DailyRecommend[] }>(`${API_BASE}/daily-recommend`);
    if (res.code === 200) setRecommend(res.data);
    setLoading(false);
  }, []);

  useEffect(() => {
    loadModules();
  }, [loadModules]);

  useEffect(() => {
    if (tab === 'articles') loadArticles();
    else if (tab === 'paths') loadPaths();
    else if (tab === 'progress') loadProgress();
    else if (tab === 'recommend') loadRecommend();
  }, [tab, loadArticles, loadPaths, loadProgress, loadRecommend]);

  const loadArticleDetail = async (id: number) => {
    setLoading(true);
    const res = await apiGet<{ code: number; data: ArticleDetail }>(`${API_BASE}/articles/${id}`);
    if (res.code === 200) setArticle(res.data);
    setLoading(false);
  };

  const handleLike = async (id: number) => {
    await apiPost(`${API_BASE}/articles/${id}/like`);
    if (article && article.id === id) {
      setArticle({ ...article, like_count: article.like_count + 1 });
    }
  };

  const handleProgress = async (articleId: number, status: string, comprehension_score?: number) => {
    await apiPut(`${API_BASE}/progress/${articleId}`, { status, comprehension_score });
  };

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-800">🎓 X1-X10 科学学习中心</h1>
        <p className="text-sm text-slate-500 mt-1">问题驱动 · 间隔重复 · 主动回忆 · 费曼技巧 · 知识树 · 反馈循环 · 刻意练习 · 思维模型 · 关联迁移 · 教授他人</p>
      </div>

      {error && <div className="bg-rose-50 border border-rose-200 text-rose-700 p-3 rounded-lg mb-4 text-sm">{error}</div>}

      {/* Tabs */}
      <div className="flex gap-2 mb-6 flex-wrap">
        {(['recommend', 'articles', 'paths', 'progress', 'modules'] as const).map(t => (
          <button key={t} onClick={() => { setTab(t); setArticle(null); }}
            className={`px-4 py-2 rounded-lg text-sm font-bold transition-all ${tab === t ? 'bg-slate-800 text-white' : 'bg-white border text-slate-600 hover:bg-slate-50'}`}>
            {t === 'recommend' ? '📌 每日推荐' : t === 'articles' ? '📚 知识库' : t === 'paths' ? '🗺️ 学习路径' : t === 'progress' ? '📊 我的进度' : '🧩 X1-X10'}
          </button>
        ))}
      </div>

      {/* Tab: Modules */}
      {tab === 'modules' && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {modules.map(m => (
            <div key={m.key} className="bg-white rounded-xl border p-5 hover:shadow-md transition-shadow">
              <div className="flex items-center gap-2 mb-2">
                <span className="bg-indigo-100 text-indigo-700 px-2 py-0.5 rounded text-xs font-bold">{m.key}</span>
                <h3 className="font-bold text-slate-800">{m.name}</h3>
              </div>
              <p className="text-sm text-slate-500">{m.description}</p>
            </div>
          ))}
        </div>
      )}

      {/* Tab: Recommend */}
      {tab === 'recommend' && (
        <>
          {loading ? <div className="text-center py-12 text-slate-400">加载推荐中...</div> : recommend.length === 0 ? (
            <div className="text-center py-12 text-slate-400">暂无推荐，先去知识库看看吧</div>
          ) : (
            <div className="space-y-4">
              <p className="text-sm text-slate-500">基于你的学习记录，为你推荐以下内容：</p>
              {recommend.map(r => (
                <div key={r.id} onClick={() => loadArticleDetail(r.id)}
                  className="bg-white rounded-xl border p-5 hover:shadow-md transition-shadow cursor-pointer">
                  <div className="flex justify-between items-start">
                    <div>
                      <h3 className="font-bold text-slate-800">{r.title}</h3>
                      <div className="flex gap-2 mt-1">
                        <span className="text-[10px] text-slate-400">{r.category}</span>
                        <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${DIFFICULTY_MAP[r.difficulty]?.cls}`}>
                          {DIFFICULTY_MAP[r.difficulty]?.label}
                        </span>
                        {r.related_module && <span className="text-[10px] text-sky-600">{r.related_module}</span>}
                      </div>
                    </div>
                    <span className="text-xs text-slate-400">{r.read_time_minutes}分钟</span>
                  </div>
                  {r.summary && <p className="text-sm text-slate-500 mt-2">{r.summary}</p>}
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {/* Tab: Articles */}
      {tab === 'articles' && (
        <>
          {article ? (
            <div>
              <button onClick={() => setArticle(null)} className="text-sm text-sky-600 hover:underline mb-4">← 返回列表</button>
              <div className="bg-white rounded-xl border p-6">
                <div className="flex justify-between items-start mb-4">
                  <div>
                    <h2 className="text-xl font-bold">{article.title}</h2>
                    <div className="flex gap-2 mt-2">
                      <span className="text-xs text-slate-400">{article.category}</span>
                      <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${DIFFICULTY_MAP[article.difficulty]?.cls}`}>
                        {DIFFICULTY_MAP[article.difficulty]?.label}
                      </span>
                      {article.related_module && <span className="bg-indigo-100 text-indigo-700 px-2 py-0.5 rounded text-[10px] font-bold">{article.related_module}</span>}
                      <span className="text-xs text-slate-400">{article.read_time_minutes}分钟阅读</span>
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <button onClick={() => handleLike(article.id)} className="text-xs text-rose-500 hover:underline">❤️ {article.like_count}</button>
                    <button onClick={() => handleProgress(article.id, 'bookmarked')} className="text-xs text-amber-500 hover:underline">🔖 收藏</button>
                    <button onClick={() => handleProgress(article.id, 'completed')} className="text-xs text-emerald-500 hover:underline">✅ 标记完成</button>
                  </div>
                </div>
                <div className="prose prose-sm max-w-none border-t pt-4">
                  <div className="whitespace-pre-wrap text-sm text-slate-700 leading-relaxed">{article.content}</div>
                </div>
              </div>
            </div>
          ) : (
            <>
              <div className="flex gap-4 mb-4 flex-wrap">
                <select value={category} onChange={e => setCategory(e.target.value)} className="border rounded-lg px-3 py-2 text-sm">
                  <option value="">全部分类</option>
                  <option value="商业认知">商业认知</option>
                  <option value="产品思维">产品思维</option>
                  <option value="增长策略">增长策略</option>
                  <option value="管理方法">管理方法</option>
                  <option value="市场营销">市场营销</option>
                  <option value="思维模型">思维模型</option>
                </select>
                <select value={difficulty} onChange={e => setDifficulty(e.target.value)} className="border rounded-lg px-3 py-2 text-sm">
                  <option value="">全部难度</option>
                  <option value="beginner">入门</option>
                  <option value="intermediate">进阶</option>
                  <option value="advanced">高级</option>
                </select>
              </div>

              {loading ? <div className="text-center py-12 text-slate-400">加载中...</div> : articles.length === 0 ? (
                <div className="text-center py-12 text-slate-400">暂无知识文章</div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {articles.map(a => (
                    <div key={a.id} onClick={() => loadArticleDetail(a.id)}
                      className="bg-white rounded-xl border p-5 hover:shadow-md transition-shadow cursor-pointer">
                      <div className="flex justify-between">
                        <h3 className="font-bold text-slate-800">{a.title}</h3>
                        <span className="text-xs text-slate-400">{a.read_time_minutes}分钟</span>
                      </div>
                      <div className="flex gap-2 mt-1">
                        <span className="text-[10px] text-slate-400">{a.category}</span>
                        <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${DIFFICULTY_MAP[a.difficulty]?.cls}`}>
                          {DIFFICULTY_MAP[a.difficulty]?.label}
                        </span>
                      </div>
                      {a.summary && <p className="text-sm text-slate-500 mt-2 line-clamp-2">{a.summary}</p>}
                      <div className="flex gap-3 mt-2 text-[10px] text-slate-400">
                        <span>👁️ {a.view_count}</span>
                        <span>❤️ {a.like_count}</span>
                        {a.related_module && <span className="text-sky-600">{a.related_module}</span>}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </>
      )}

      {/* Tab: Paths */}
      {tab === 'paths' && (
        <>
          {loading ? <div className="text-center py-12 text-slate-400">加载中...</div> : paths.length === 0 ? (
            <div className="text-center py-12 text-slate-400">暂无学习路径</div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {paths.map(p => (
                <div key={p.id} className="bg-white rounded-xl border p-5 hover:shadow-md transition-shadow">
                  <div className="flex items-center gap-2 mb-2">
                    <h3 className="font-bold text-slate-800">{p.name}</h3>
                    <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${DIFFICULTY_MAP[p.difficulty]?.cls}`}>
                      {DIFFICULTY_MAP[p.difficulty]?.label}
                    </span>
                  </div>
                  <p className="text-xs text-slate-400 mb-2">{p.category}</p>
                  {p.description && <p className="text-sm text-slate-500 mb-3">{p.description}</p>}
                  <div className="flex gap-4 text-xs text-slate-400">
                    <span>📚 {p.article_count}篇文章</span>
                    <span>⏱️ 约{p.estimated_hours}小时</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {/* Tab: Progress */}
      {tab === 'progress' && (
        <>
          {loading ? <div className="text-center py-12 text-slate-400">加载中...</div> : !progress ? (
            <div className="text-center py-12 text-slate-400">暂无学习数据</div>
          ) : (
            <div className="space-y-6">
              <div className="grid grid-cols-4 gap-4">
                <div className="bg-white rounded-xl border p-4 text-center"><p className="text-2xl font-bold text-slate-800">{progress.total_assigned}</p><p className="text-xs text-slate-400">已学习</p></div>
                <div className="bg-white rounded-xl border p-4 text-center"><p className="text-2xl font-bold text-emerald-600">{progress.completed}</p><p className="text-xs text-slate-400">已完成</p></div>
                <div className="bg-white rounded-xl border p-4 text-center"><p className="text-2xl font-bold text-sky-600">{progress.in_progress}</p><p className="text-xs text-slate-400">进行中</p></div>
                <div className="bg-white rounded-xl border p-4 text-center"><p className="text-2xl font-bold text-amber-600">{progress.bookmarked}</p><p className="text-xs text-slate-400">收藏</p></div>
              </div>

              <div className="bg-white rounded-xl border p-5">
                <h3 className="font-bold mb-2">📈 学习完成率</h3>
                <div className="w-full bg-slate-100 rounded-full h-4">
                  <div className="bg-sky-500 h-4 rounded-full transition-all" style={{ width: `${progress.completion_rate}%` }} />
                </div>
                <p className="text-sm text-slate-500 mt-1">{progress.completion_rate}%</p>
              </div>

              {progress.recent_articles.length > 0 && (
                <div className="bg-white rounded-xl border p-5">
                  <h3 className="font-bold mb-3">📖 最近学习</h3>
                  <div className="space-y-2">
                    {progress.recent_articles.map(r => (
                      <div key={r.article_id} className="flex justify-between items-center p-2 hover:bg-slate-50 rounded">
                        <div>
                          <span className="text-sm font-medium">{r.title}</span>
                          <span className="text-[10px] text-slate-400 ml-2">{r.category}</span>
                        </div>
                        <span className={`text-[10px] px-2 py-0.5 rounded-full font-bold ${r.status === 'completed' ? 'bg-emerald-100 text-emerald-700' : r.status === 'in_progress' ? 'bg-sky-100 text-sky-700' : 'bg-slate-100 text-slate-600'}`}>
                          {r.status === 'completed' ? '已完成' : r.status === 'in_progress' ? '学习中' : '已收藏'}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
