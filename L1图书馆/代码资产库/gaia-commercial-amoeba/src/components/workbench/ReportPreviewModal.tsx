"use client";

import type { Report, Department } from "@/lib/data";

interface ReportPreviewModalProps {
  report: Report | null;
  department: Department | undefined;
  onClose: () => void;
  onPurchase: (reportId: string) => void;
  isOpen: boolean;
  paying?: boolean;
  paymentUrl?: string;
}

export default function ReportPreviewModal({
  report,
  department,
  onClose,
  onPurchase,
  isOpen,
  paying = false,
  paymentUrl,
}: ReportPreviewModalProps) {
  if (!isOpen || !report) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="bg-slate-800 rounded-2xl border border-slate-700/50 w-[520px] max-w-[90vw] shadow-2xl overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-700/30 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="text-2xl">{department?.icon ?? "📄"}</span>
            <div>
              <h3 className="font-semibold text-slate-200 text-sm">{report.title}</h3>
              <p className="text-[10px] text-slate-500">{department?.name} · 专业报告</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 flex items-center justify-center rounded-lg hover:bg-slate-700 text-slate-400 hover:text-slate-200 transition"
          >
            ✕
          </button>
        </div>

        <div className="px-6 py-5">
          <div className="bg-slate-900/50 rounded-xl p-5 mb-5 border border-slate-700/30">
            <div className="flex items-center gap-2 mb-3">
              <span className="text-blue-400">🔒</span>
              <span className="text-xs text-blue-400/80 font-medium">报告预览</span>
            </div>
            <p className="text-sm text-slate-300 leading-relaxed">
              {report.preview}
            </p>
            <div className="mt-4 space-y-2">
              {[1, 2, 3].map((i) => (
                <div
                  key={i}
                  className="h-3 bg-slate-700/50 rounded-full blur-[2px]"
                  style={{ width: `${60 + i * 10}%` }}
                />
              ))}
            </div>
          </div>

          {paying ? (
            <div className="bg-gradient-to-r from-blue-500/10 to-indigo-500/10 border border-blue-500/20 rounded-xl p-6 text-center">
              <div className="animate-spin w-8 h-8 border-2 border-blue-400 border-t-transparent rounded-full mx-auto mb-3" />
              <p className="text-sm text-slate-300">正在跳转到支付页面...</p>
              {paymentUrl && (
                <a
                  href={paymentUrl}
                  className="mt-3 inline-block text-xs text-blue-400 hover:text-blue-300 underline"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  如果未自动跳转，请点击此处
                </a>
              )}
            </div>
          ) : (
            <div className="bg-gradient-to-r from-amber-500/10 to-orange-500/10 border border-amber-500/20 rounded-xl p-4">
              <div className="flex items-start gap-3">
                <span className="text-2xl">🔐</span>
                <div>
                  <p className="text-sm font-medium text-slate-200">
                    解锁完整报告 · ¥{report.price}
                  </p>
                  <p className="text-xs text-slate-400 mt-1">
                    支付后即可查看完整12页报告，含数据图表和可执行建议清单
                  </p>
                  <div className="flex gap-2 mt-3">
                    <button
                      onClick={() => onPurchase(report.id)}
                      className="flex-1 py-2 bg-gradient-to-r from-amber-500 to-orange-500 text-white text-sm font-medium rounded-xl hover:opacity-90 transition shadow-lg shadow-amber-500/20"
                    >
                      立即解锁 · ¥{report.price}
                    </button>
                    <button
                      onClick={onClose}
                      className="px-4 py-2 border border-slate-600 text-slate-400 text-sm rounded-xl hover:bg-slate-700 transition"
                    >
                      稍后
                    </button>
                  </div>
                  <p className="text-[10px] text-slate-500 mt-2">
                    💡 成为会员可免费查看所有报告 · 月费¥299起
                  </p>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
