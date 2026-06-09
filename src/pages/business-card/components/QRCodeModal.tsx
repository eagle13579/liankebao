import { Loader2, Download } from 'lucide-react';

interface QRCodeModalProps {
  show: boolean;
  onClose: () => void;
  onDownload: () => void;
  qrCodeUrl: string;
  qrLoading: boolean;
}

export default function QRCodeModal({
  show,
  onClose,
  onDownload,
  qrCodeUrl,
  qrLoading,
}: QRCodeModalProps) {
  if (!show) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-2xl p-6 mx-4 max-w-xs w-full shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="text-base font-bold text-center text-on-surface mb-1">
          分享画册二维码
        </h3>
        <p className="text-xs text-text-muted text-center mb-4">
          扫码即可查看您的数字名片画册
        </p>

        <div className="flex justify-center mb-4">
          {qrLoading ? (
            <div className="w-48 h-48 flex items-center justify-center">
              <Loader2 className="w-8 h-8 text-primary animate-spin" />
            </div>
          ) : qrCodeUrl ? (
            <img
              src={qrCodeUrl}
              alt="名片二维码"
              className="w-48 h-48 rounded-xl"
            />
          ) : (
            <div className="w-48 h-48 flex items-center justify-center bg-slate-50 rounded-xl">
              <p className="text-xs text-text-muted">加载失败</p>
            </div>
          )}
        </div>

        <div className="flex gap-2">
          <button
            onClick={onClose}
            className="flex-1 py-2.5 rounded-xl border border-border-light text-sm text-on-surface font-medium hover:bg-slate-50 transition-colors"
          >
            关闭
          </button>
          <button
            onClick={onDownload}
            disabled={!qrCodeUrl}
            className="flex-1 py-2.5 rounded-xl bg-primary text-white text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50 flex items-center justify-center gap-1.5"
          >
            <Download className="w-4 h-4" />
            保存图片
          </button>
        </div>

        <p className="text-[10px] text-text-muted text-center mt-3">
          长按或点击「保存图片」即可保存到相册分享
        </p>
      </div>
    </div>
  );
}
