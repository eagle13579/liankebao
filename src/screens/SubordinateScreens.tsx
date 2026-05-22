import { useNavigate } from 'react-router-dom';
import { Users, ChevronLeft, TrendingUp, Calendar, Award } from 'lucide-react';

interface Subordinate {
  id: number;
  avatar: string;
  nickname: string;
  performance: number;   // 推广业绩 (元)
  registered_at: string; // 注册时间
  level: string;         // 等级
}

const mockSubordinates: Subordinate[] = [
  {
    id: 1,
    avatar: 'https://api.dicebear.com/7.x/avataaars/svg?seed=Alice',
    nickname: '张经理',
    performance: 28500,
    registered_at: '2024-03-15',
    level: '高级推广员',
  },
  {
    id: 2,
    avatar: 'https://api.dicebear.com/7.x/avataaars/svg?seed=Bob',
    nickname: '李明',
    performance: 12300,
    registered_at: '2024-04-02',
    level: '中级推广员',
  },
  {
    id: 3,
    avatar: 'https://api.dicebear.com/7.x/avataaars/svg?seed=Charlie',
    nickname: '王芳',
    performance: 8900,
    registered_at: '2024-05-18',
    level: '初级推广员',
  },
  {
    id: 4,
    avatar: 'https://api.dicebear.com/7.x/avataaars/svg?seed=Diana',
    nickname: '赵强',
    performance: 6700,
    registered_at: '2024-06-10',
    level: '初级推广员',
  },
  {
    id: 5,
    avatar: 'https://api.dicebear.com/7.x/avataaars/svg?seed=Eve',
    nickname: '刘洋',
    performance: 15200,
    registered_at: '2024-03-28',
    level: '中级推广员',
  },
];

export function SubordinatePage() {
  const navigate = useNavigate();

  const totalPerformance = mockSubordinates.reduce((sum, s) => sum + s.performance, 0);

  return (
    <div className="flex flex-col min-h-screen bg-gradient-to-b from-sky-50/30 via-white to-white font-sans pb-8">
      <header className="sticky top-0 z-50 bg-white/80 backdrop-blur-xl border-b border-sky-100/50 flex items-center gap-3 px-4 h-16">
        <button
          onClick={() => navigate(-1)}
          className="w-8 h-8 rounded-full bg-slate-50 flex items-center justify-center text-slate-500 hover:bg-sky-50 hover:text-sky-600 active:scale-90 transition-all"
        >
          <ChevronLeft className="w-5 h-5" />
        </button>
        <h1 className="font-manrope text-lg font-extrabold bg-gradient-to-r from-sky-600 to-blue-600 bg-clip-text text-transparent">
          我的下级
        </h1>
      </header>

      <main className="max-w-3xl mx-auto w-full p-4 space-y-5">
        {/* Summary Card */}
        <section className="bg-white rounded-2xl border border-slate-100 p-5 shadow-sm">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-sky-500 to-blue-600 flex items-center justify-center shadow-sm">
              <Users className="w-5 h-5 text-white" />
            </div>
            <div>
              <p className="text-sm font-bold text-slate-800">团队概览</p>
              <p className="text-xs text-slate-400">下级推广团队数据</p>
            </div>
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div className="bg-sky-50 rounded-xl p-3 text-center">
              <p className="text-2xl font-extrabold text-sky-600">{mockSubordinates.length}</p>
              <p className="text-[10px] text-slate-500 mt-0.5">下级总人数</p>
            </div>
            <div className="bg-emerald-50 rounded-xl p-3 text-center">
              <p className="text-2xl font-extrabold text-emerald-600">¥{totalPerformance.toLocaleString()}</p>
              <p className="text-[10px] text-slate-500 mt-0.5">团队总业绩</p>
            </div>
            <div className="bg-amber-50 rounded-xl p-3 text-center">
              <p className="text-2xl font-extrabold text-amber-600">¥{(totalPerformance / mockSubordinates.length).toFixed(0)}</p>
              <p className="text-[10px] text-slate-500 mt-0.5">人均业绩</p>
            </div>
          </div>
        </section>

        {/* Subordinate List */}
        <section className="space-y-3">
          <div className="flex items-center gap-2">
            <div className="w-1 h-4 bg-gradient-to-b from-sky-500 to-blue-600 rounded-full" />
            <h2 className="font-extrabold text-slate-800 text-sm">下级成员</h2>
            <span className="text-[10px] text-slate-400">（{mockSubordinates.length}人）</span>
          </div>

          {mockSubordinates.map((sub) => (
            <div
              key={sub.id}
              className="bg-white rounded-2xl border border-slate-100 p-4 shadow-sm hover:shadow-md transition-all"
            >
              <div className="flex items-center gap-3">
                <img
                  src={sub.avatar}
                  className="w-12 h-12 rounded-full bg-slate-100 border-2 border-sky-100 object-cover"
                  alt={sub.nickname}
                />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <h3 className="font-bold text-slate-800 text-sm truncate">{sub.nickname}</h3>
                    <span className="bg-gradient-to-r from-amber-400 to-amber-500 text-[8px] text-white px-1.5 py-0.5 rounded-full font-bold shrink-0">
                      {sub.level}
                    </span>
                  </div>
                  <div className="flex items-center gap-4 mt-1.5">
                    <div className="flex items-center gap-1">
                      <TrendingUp className="w-3 h-3 text-emerald-500" />
                      <span className="text-[10px] text-slate-500">
                        业绩: <span className="font-bold text-emerald-700">¥{sub.performance.toLocaleString()}</span>
                      </span>
                    </div>
                    <div className="flex items-center gap-1">
                      <Calendar className="w-3 h-3 text-slate-400" />
                      <span className="text-[10px] text-slate-400">{sub.registered_at}</span>
                    </div>
                  </div>
                </div>
                <div className="shrink-0">
                  <div className="w-8 h-8 rounded-full bg-sky-50 flex items-center justify-center">
                    <Award className="w-4 h-4 text-sky-500" />
                  </div>
                </div>
              </div>
            </div>
          ))}
        </section>

        {mockSubordinates.length === 0 && (
          <div className="text-center py-12">
            <Users className="w-12 h-12 text-slate-200 mx-auto mb-3" />
            <p className="text-sm text-slate-400">暂无下级成员</p>
            <p className="text-xs text-slate-300 mt-1">推广产品邀请好友加入</p>
          </div>
        )}
      </main>
    </div>
  );
}
