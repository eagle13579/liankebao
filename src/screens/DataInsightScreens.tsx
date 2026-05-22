import { useNavigate } from 'react-router-dom';
import {
  ChevronLeft, BarChart3, TrendingUp, Users, ShoppingBag,
  DollarSign, Calendar, ArrowUp, ArrowDown, Activity
} from 'lucide-react';

const insights = [
  { icon: ShoppingBag, label: '总产品数', value: '128', change: '+12', up: true, color: 'text-sky-600', bg: 'bg-sky-50' },
  { icon: Users, label: '客户总数', value: '356', change: '+28', up: true, color: 'text-emerald-600', bg: 'bg-emerald-50' },
  { icon: DollarSign, label: '本月成交额', value: '¥46,800', change: '+15.2%', up: true, color: 'text-amber-600', bg: 'bg-amber-50' },
  { icon: TrendingUp, label: '推广收益', value: '¥3,420', change: '+8.5%', up: true, color: 'text-violet-600', bg: 'bg-violet-50' },
];

const trendData = [
  { month: '1月', amount: 12000 },
  { month: '2月', amount: 15000 },
  { month: '3月', amount: 13500 },
  { month: '4月', amount: 18000 },
  { month: '5月', amount: 22000 },
  { month: '6月', amount: 25000 },
];

export function DataInsight() {
  const navigate = useNavigate();
  const maxAmount = Math.max(...trendData.map(d => d.amount));

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
          数据洞察
        </h1>
      </header>

      <main className="max-w-3xl mx-auto w-full p-4 space-y-5">
        {/* Summary Cards */}
        <div className="grid grid-cols-2 gap-3">
          {insights.map((item, i) => {
            const Icon = item.icon;
            return (
              <div key={i} className="bg-white rounded-2xl border border-slate-100 p-4 shadow-sm">
                <div className="flex items-center gap-2 mb-2">
                  <div className={`w-8 h-8 rounded-lg ${item.bg} flex items-center justify-center`}>
                    <Icon className={`w-4 h-4 ${item.color}`} />
                  </div>
                  <span className="text-[10px] text-slate-400 font-medium">{item.label}</span>
                </div>
                <p className="text-xl font-extrabold text-slate-800">{item.value}</p>
                <div className="flex items-center gap-0.5 mt-1">
                  {item.up ? (
                    <ArrowUp className="w-3 h-3 text-emerald-500" />
                  ) : (
                    <ArrowDown className="w-3 h-3 text-red-500" />
                  )}
                  <span className={`text-[10px] font-bold ${item.up ? 'text-emerald-600' : 'text-red-500'}`}>
                    {item.change}
                  </span>
                  <span className="text-[9px] text-slate-400 ml-1">较上月</span>
                </div>
              </div>
            );
          })}
        </div>

        {/* Trend Chart (Simplified Bar) */}
        <section className="bg-white rounded-2xl border border-slate-100 p-5 shadow-sm">
          <div className="flex items-center gap-2 mb-4">
            <Activity className="w-4 h-4 text-sky-600" />
            <h2 className="font-manrope font-extrabold text-slate-800 text-base">成交趋势</h2>
            <span className="text-[9px] text-slate-400 ml-auto font-medium flex items-center gap-1">
              <Calendar className="w-3 h-3" /> 近6个月
            </span>
          </div>
          <div className="flex items-end gap-2 h-32">
            {trendData.map((d, i) => (
              <div key={i} className="flex-1 flex flex-col items-center gap-1">
                <div
                  className="w-full bg-gradient-to-t from-sky-500 to-blue-500 rounded-t-lg transition-all hover:opacity-80"
                  style={{ height: `${(d.amount / maxAmount) * 100}%` }}
                />
                <span className="text-[8px] text-slate-400 font-medium">{d.month}</span>
              </div>
            ))}
          </div>
        </section>

        {/* Placeholder for more insights */}
        <section className="bg-gradient-to-r from-sky-50 to-blue-50 rounded-2xl border border-sky-100 p-5 text-center">
          <BarChart3 className="w-8 h-8 text-sky-400 mx-auto mb-2" />
          <h3 className="font-bold text-sky-800 text-sm">更多数据维度即将上线</h3>
          <p className="text-[11px] text-sky-600/70 mt-1">客户画像分析、产品热度排行、推广效果评估等更多功能正在开发中</p>
        </section>
      </main>
    </div>
  );
}
