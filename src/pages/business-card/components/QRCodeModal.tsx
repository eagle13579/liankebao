import { X, Download } from 'lucide-react';
interface Props { show: boolean; onClose: ()=>void; onDownload: ()=>void; qrCodeUrl: string; qrLoading: boolean; }
export default function QRCodeModal({ show, onClose, onDownload, qrCodeUrl, qrLoading }: Props) {
  if(!show) return null;
  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={onClose}>
      <div className="bg-white rounded-2xl p-8 max-w-sm w-full mx-4" onClick={e=>e.stopPropagation()}>
        <div className="flex justify-between items-center mb-4">
          <h3 className="text-lg font-semibold">名片二维码</h3>
          <button onClick={onClose} className="p-1 hover:bg-gray-100 rounded-lg"><X className="w-5 h-5" /></button>
        </div>
        <div className="flex justify-center mb-4">
          {qrLoading ? <div className="w-48 h-48 bg-gray-100 animate-pulse rounded-lg" /> : (
            <div className="w-48 h-48 bg-gray-100 rounded-lg flex items-center justify-center text-gray-400">
              {qrCodeUrl ? <img src={qrCodeUrl} alt="QR Code" className="w-48 h-48" /> : "二维码区域"}
            </div>
          )}
        </div>
        <button onClick={onDownload} className="w-full px-4 py-2 bg-blue-600 text-white rounded-xl hover:bg-blue-700 transition-colors flex items-center justify-center gap-2">
          <Download className="w-4 h-4" />下载二维码
        </button>
      </div>
    </div>
  );
}
