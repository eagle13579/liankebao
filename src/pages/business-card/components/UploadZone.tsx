import { Upload, Camera, Loader2 } from 'lucide-react';
interface Props { loading: boolean; dragOver: boolean; onDrop: (e: React.DragEvent)=>void; onDragOver: (e: React.DragEvent)=>void; onDragLeave: (e: React.DragEvent)=>void; onClick: ()=>void; }
export default function UploadZone({ loading, dragOver, onDrop, onDragOver, onDragLeave, onClick }: Props) {
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] p-8"
      onDrop={onDrop} onDragOver={onDragOver} onDragLeave={onDragLeave} onClick={onClick}>
      <div className={"w-full max-w-md p-12 border-2 border-dashed rounded-2xl text-center cursor-pointer " + (dragOver ? "border-blue-500 bg-blue-50" : "border-gray-300 hover:border-blue-400")}>
        {loading ? <Loader2 className="w-12 h-12 mx-auto mb-4 text-blue-500 animate-spin" /> : (
          <><Upload className="w-12 h-12 mx-auto mb-4 text-gray-400" />
          <p className="text-lg font-medium text-gray-700 mb-2">上传名片图片或PDF</p>
          <p className="text-sm text-gray-500 mb-4">拖拽文件到此处，或点击选择文件</p>
          <label className="inline-flex items-center gap-2 px-6 py-3 bg-blue-600 text-white rounded-xl cursor-pointer hover:bg-blue-700 transition-colors">
            <Camera className="w-5 h-5" /><span>拍照/选择文件</span>
            <input type="file" className="hidden" accept="image/*,.pdf" onChange={e => { const f=e.target.files?.[0]; if(f) onClick(); }} />
          </label></>
        )}
      </div>
      <p className="mt-4 text-xs text-gray-400">支持 JPG / PNG / PDF 格式</p>
    </div>
  );
}
