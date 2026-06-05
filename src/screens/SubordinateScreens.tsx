import { useNavigate } from 'react-router-dom';
import { ChevronLeft, TrendingUp, Calendar, ShoppingBag, CheckCircle, Clock, DollarSign } from 'lucide-react';
import { useState } from 'react';

interface PromotionOrder {
  id: number;
  productName: string;
  price: number;
  earnRate: number;
  earnAmount: number;
  status: string;
  createdAt: string;
}

const mockOrders: PromotionOrder[] = [
  {
    id: 1001,
    productName: '旗舰版智能健康手表 S3',
    price: 1299,
    earnRate: 10,
    earnAmount: 129.90,
    status: '已完成',
    createdAt: '2024-06-15',
  },
  {
    id: 1002,
    productName: '高端商务茶礼套装·臻选',
    price: 688,
    earnRate: 8,
    earnAmount: 55.04,
    status: '已完成',
    createdAt: '2024-06-14',
  },
  {
    id: 1003,
    productName: '企业数字化管理平台 Pro',
    price: 9800,
    earnRate: 5,
    earnAmount: 490.00,
    status: '已完成',
    createdAt: '2024-06-12',
  },
  {
    id: 1004,
    productName: '高级护肝综合营养片',
    price: 298,
    earnRate: 7,
    earnAmount: 20.86,
    status: '处理中',
    createdAt: '2024-06-16',
  },
  {
    id: 1005,
    productName: '智能办公解决方案套装',
    price: 3580,
    earnRate: 6,
    earnAmount: 214.80,
    status: '已完成',
    createdAt: '2024-06-10',
  },
];

export function SubordinatePage() {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<'all' | 'completed' | 'pending'>('all');

  const totalEarn = mockOrders.reduce((sum, o) => sum + o.earnAmount, 0);
  const totalOrders = mockOrders.length;

  const filteredOrders = mockOrders.filter((o) => {
    if (activeTab === 'completed') return o.status === '已完成';
    if (activeTab === 'pending') return o.status === '处理中';
    return true;
  });

  return (
    <div className="flex flex-col min-h-screen bg-gradient-to-b from-sky-50/30 via-white to-white font-sans pb-8">
      <header className="sticky top-0 z-50 bg-white/80 backdrop-blur-xl border-b border-sky-100/50 flex items-center gap-3 px-4 h-16">
        <button
          onClick={() => navigate(-1)}
          className="w-8 h-8 rounded-full bg-slate-50 flex items-center justify-center text-slate-500 hover:bg-sky-50 hover:text-sky-600 active:scale-90 transition-all"
        >
          <ChevronLeft className="w-5 h-5" />
        </button>
        <h1 className="font-manrope text-lg font-extrabold bg-gradient-to-r from-sky-500 to-indigo-500 bg-clip-text text-transparent">
          推广统计
        </h1>
      </header>

      <main className="max-w-3xl mx-auto w-full p-4 space-y-5">
        {/* Summary Card */}
        <section className="bg-white rounded-2xl border border-slate-100 p-5 shadow-sm">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-sky-500 to-blue-600 flex items-center justify-center shadow-sm">
              <TrendingUp className="w-5 h-5 text-white" />
            </div>
            <div>
              <p className="text-sm font-bold text-slate-800">收益概览</p>
              <p className="text-xs text-slate-400">推广订单与分润统计</p>
            </div>
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div className="bg-sky-50 rounded-xl p-3 text-center">
              <p className="text-2xl font-extrabold text-sky-600">{totalOrders}</p>
              <p className="text-[10px] text-slate-500 mt-0.5">推广订单</p>
            </div>
            <div className="bg-emerald-50 rounded-xl p-3 text-center">
              <p className="text-2xl font-extrabold text-emerald-600">¥{totalEarn.toFixed(2)}</p>
              <p className="text-[10px] text-slate-500 mt-0.5">累计收益</p>
            </div>
            <div className="bg-amber-50 rounded-xl p-3 text-center">
              <p className="text-2xl font-extrabold text-amber-600">¥{(totalEarn / totalOrders).toFixed(2)}</p>
              <p className="text-[10px] text-slate-500 mt-0.5">平均每单</p>
            </div>
          </div>
        </section>

        {/* Tabs */}
        <div className="flex gap-2">
          {[
            { id: 'all' as const, label: '全部订单' },
            { id: 'completed' as const, label: '已完成' },
            { id: 'pending' as const, label: '处理中' },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-4 py-1.5 rounded-full text-xs font-bold transition-all ${
                activeTab === tab.id
                  ? 'bg-sky-500 text-white shadow-sm'
                  : 'bg-white text-slate-500 border border-slate-200 hover:border-sky-200 hover:text-sky-600'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Order List */}
        <section className="space-y-3">
          <div className="flex items-center gap-2">
            <div className="w-1 h-4 bg-gradient-to-b from-sky-500 to-blue-600 rounded-full" />
            <h2 className="font-extrabold text-slate-800 text-sm">推广订单明细</h2>
            <span className="text-[10px] text-slate-400">（{filteredOrders.length}条）</span>
          </div>

          {filteredOrders.map((order) => (
            <div
              key={order.id}
              className="bg-white rounded-2xl border border-slate-100 p-4 shadow-sm hover:shadow-md transition-all"
            >
              <div className="flex items-start gap-3">
                <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-sky-50 to-blue-50 flex items-center justify-center shrink-0 border border-sky-100">
                  <ShoppingBag className="w-6 h-6 text-sky-500" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <h3 className="font-bold text-slate-800 text-sm truncate">{order.productName}</h3>
                    <span
                      className={`text-[8px] px-1.5 py-0.5 rounded-full font-bold shrink-0 ${
                        order.status === '已完成'
                          ? 'bg-emerald-50 text-emerald-600'
                          : 'bg-amber-50 text-amber-600'
                      }`}
                    >
                      {order.status}
                    </span>
                  </div>
                  <div className="flex flex-wrap items-center gap-x-4 gap-y-1 mt-1.5">
                    <div className="flex items-center gap-1">
                      <DollarSign className="w-3 h-3 text-sky-500" />
                      <span className="text-[10px] text-slate-500">
                        售价 <span className="font-bold text-slate-700">¥{order.price.toFixed(2)}</span>
                      </span>
                    </div>
                    <div className="flex items-center gap-1">
                      <TrendingUp className="w-3 h-3 text-emerald-500" />
                      <span className="text-[10px] text-slate-500">
                        分润比例 <span className="font-bold text-emerald-700">{order.earnRate}%</span>
                      </span>
                    </div>
                    <div className="flex items-center gap-1">
                      <CheckCircle className="w-3 h-3 text-green-500" />
                      <span className="text-[10px] text-slate-500">
                        佣金 <span className="font-bold text-green-700">+¥{order.earnAmount.toFixed(2)}</span>
                      </span>
                    </div>
                    <div className="flex items-center gap-1">
                      <Calendar className="w-3 h-3 text-slate-400" />
                      <span className="text-[10px] text-slate-400">{order.createdAt}</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          ))}

          {filteredOrders.length === 0 && (
            <div className="text-center py-12">
              <ShoppingBag className="w-12 h-12 text-slate-200 mx-auto mb-3" />
              <p className="text-sm text-slate-400">暂无推广订单</p>
              <p className="text-xs text-slate-300 mt-1">推广产品赚取分润佣金</p>
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
