import { Upload, Loader2, Sparkles, Camera } from 'lucide-react';

interface UploadZoneProps {
  loading: boolean;
  dragOver: boolean;
  onDrop: (e: React.DragEvent) => void;
  onDragOver: (e: React.DragEvent) => void;
  onDragLeave: () => void;
  onClick: () => void;
}

export default function UploadZone({
  loading,
  dragOver,
  onDrop,
  onDragOver,
  onDragLeave,
  onClick,
}: UploadZoneProps) {
  return (
    <div className="space-y-6">
      <div className="text-center">
        <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-primary/10 mb-4">
          <Camera className="w-8 h-8 text-primary" />
        </div>
        <h2 className="text-xl font-bold text-on-surface">AI 名片扫描</h2>
        <p className="text-sm text-text-muted mt-1">
          上传名片图片或 PDF，AI 自动提取信息
        </p>
      </div>

      <div
        className={`relative border-2 border-dashed rounded-2xl p-12 text-center cursor-pointer transition-all duration-200 ${
          dragOver
            ? 'border-primary bg-primary/5'
            : 'border-border-light hover:border-primary/50 hover:bg-slate-50'
        }`}
        onDrop={onDrop}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onClick={onClick}
      >
        {loading ? (
          <div className="flex flex-col items-center gap-3">
            <Loader2 className="w-10 h-10 text-primary animate-spin" />
            <p className="text-sm text-text-muted">正在识别名片文字...</p>
            <div className="w-48 h-1.5 bg-slate-200 rounded-full overflow-hidden">
              <div className="h-full bg-primary rounded-full animate-pulse" style={{ width: '60%' }} />
            </div>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-3">
            <Upload className="w-10 h-10 text-text-muted" />
            <div>
              <p className="text-sm font-medium text-on-surface">点击上传或拖拽文件到此处</p>
              <p className="text-xs text-text-muted mt-1">支持 PDF、JPG、PNG、BMP、WebP 格式</p>
            </div>
          </div>
        )}
      </div>

      <div className="text-center">
        <p className="text-xs text-text-muted">
          <Sparkles className="w-3 h-3 inline mr-1" />
          AI 自动识别姓名、职位、公司、联系方式等信息
        </p>
      </div>
    </div>
  );
}
