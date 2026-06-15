import { useState, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Upload, FileText, ChevronLeft, AlertTriangle, CheckCircle2, XCircle, ArrowRight, RefreshCw } from 'lucide-react';
import { api } from '../api/client';
import { ImportPreview, DuplicateGroup, Contact } from '../types';

type UploadStatus = 'idle' | 'uploading' | 'preview' | 'confirming' | 'importing' | 'done' | 'error';

export default function ContactsImportPage() {
  const navigate = useNavigate();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [status, setStatus] = useState<UploadStatus>('idle');
  const [fileName, setFileName] = useState('');
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [progress, setProgress] = useState(0);
  const [importResult, setImportResult] = useState<{ imported: number; skipped: number; merged: number } | null>(null);
  const [errorMsg, setErrorMsg] = useState('');
  const [pendingDuplicates, setPendingDuplicates] = useState<Record<number, 'skip' | 'merge' | 'update'>>({});
  const [duplicateResolved, setDuplicateResolved] = useState(false);

  const handleFileDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  }, []);

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
  };

  const handleFile = async (file: File) => {
    const ext = file.name.split('.').pop()?.toLowerCase();
    if (!['csv', 'vcf'].includes(ext || '')) {
      alert('仅支持 CSV 或 VCF 格式文件');
      return;
    }
    setFileName(file.name);
    setStatus('uploading');

    try {
      const formData = new FormData();
      formData.append('file', file);

      const res = await api.request<ImportPreview>('/api/contacts/import/preview', {
        method: 'POST',
        body: formData,
      });
      if (res.code === 0 && res.data) {
        setPreview(res.data);
        setMapping(res.data.column_mapping || {});
        const dups: Record<number, 'skip' | 'merge' | 'update'> = {};
        (res.data.duplicates || []).forEach((_: any, idx: number) => { dups[idx] = 'skip'; });
        setPendingDuplicates(dups);
        setStatus('preview');
      } else {
        setErrorMsg(res.message || '文件解析失败');
        setStatus('error');
      }
    } catch (e: any) {
      setErrorMsg(e.message || '上传失败');
      setStatus('error');
    }
  };

  const handleMappingChange = (header: string, field: string) => {
    setMapping(prev => ({ ...prev, [header]: field }));
  };

  const handleDuplicateAction = (idx: number, action: 'skip' | 'merge' | 'update') => {
    setPendingDuplicates(prev => ({ ...prev, [idx]: action }));
  };

  const resolveAllDuplicates = () => {
    setDuplicateResolved(true);
  };

  const handleImport = async () => {
    if (!preview) return;
    setStatus('importing');
    setProgress(0);

    try {
      // Simulate progress
      const interval = setInterval(() => {
        setProgress(p => Math.min(p + 10, 90));
      }, 300);

      const res = await api.post<{ imported: number; skipped: number; merged: number }>('/api/contacts/import', {
        column_mapping: mapping,
        duplicates: pendingDuplicates,
      });

      clearInterval(interval);
      setProgress(100);

      if (res.data) {
        setImportResult(res.data);
        setStatus('done');
      } else {
        setErrorMsg(res.message || '导入失败');
        setStatus('error');
      }
    } catch (e: any) {
      setErrorMsg(e.message || '导入失败');
      setStatus('error');
    }
  };

  // Field options
  const fieldOptions = [
    { value: 'name', label: '姓名' },
    { value: 'phone', label: '电话' },
    { value: 'wechat_id', label: '微信' },
    { value: 'company', label: '公司' },
    { value: 'position', label: '职位' },
    { value: 'email', label: '邮箱' },
    { value: 'tags', label: '标签' },
    { value: 'notes', label: '备注' },
    { value: 'source', label: '来源' },
    { value: '_skip', label: '跳过此列' },
  ];

  return (
    <div className="flex flex-col min-h-screen bg-neutral-bg font-sans">
      <header className="fixed top-0 w-full z-50 bg-neutral-bg border-b border-border-light flex items-center justify-between px-4 h-16">
        <div className="flex items-center gap-3">
          <button onClick={() => navigate(-1)} className="text-slate-600">
            <ChevronLeft className="w-6 h-6" />
          </button>
          <h1 className="font-manrope text-lg font-bold text-primary-container">导入联系人</h1>
        </div>
      </header>

      <main className="pt-16 p-4 space-y-4">
        {/* Idle: Upload area */}
        {status === 'idle' && (
          <>
            <div
              onDrop={handleFileDrop}
              onDragOver={e => e.preventDefault()}
              onClick={() => fileInputRef.current?.click()}
              className="border-2 border-dashed border-border-light rounded-2xl p-12 text-center cursor-pointer active:border-primary-container transition-colors bg-white"
            >
              <div className="flex flex-col items-center gap-4">
                <div className="w-16 h-16 bg-sky-50 rounded-full flex items-center justify-center">
                  <Upload className="w-8 h-8 text-primary-container" />
                </div>
                <div>
                  <p className="text-sm font-bold text-on-surface">点击或拖拽文件到此处</p>
                  <p className="text-xs text-text-muted mt-1">支持 CSV、VCF 格式</p>
                </div>
              </div>
            </div>
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv,.vcf"
              className="hidden"
              onChange={handleFileSelect}
            />

            <div className="bg-white rounded-2xl border border-border-light p-4 space-y-2">
              <h3 className="text-xs font-bold text-slate-600 flex items-center gap-1">
                <FileText className="w-4 h-4" />
                格式说明
              </h3>
              <ul className="text-xs text-text-muted space-y-1 list-disc list-inside">
                <li>CSV 文件：首行为表头，支持 UTF-8/GBK 编码</li>
                <li>VCF 文件：标准 vCard 格式，支持多联系人</li>
                <li>系统会自动识别字段映射，可手动调整</li>
                <li>重复联系人会自动检测并合并</li>
              </ul>
            </div>
          </>
        )}

        {/* Uploading */}
        {status === 'uploading' && (
          <div className="flex flex-col items-center justify-center py-16">
            <RefreshCw className="w-10 h-10 text-primary-container animate-spin mb-4" />
            <p className="text-sm text-text-muted">正在解析文件...</p>
            <p className="text-xs text-slate-400 mt-1">{fileName}</p>
          </div>
        )}

        {/* Preview */}
        {status === 'preview' && preview && (
          <div className="space-y-4">
            {/* Summary */}
            <div className="bg-white rounded-2xl border border-border-light p-4 space-y-2">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-bold">文件预览</h3>
                <span className="text-xs text-text-muted">{fileName}</span>
              </div>
              <p className="text-xs text-text-muted">
                共 {preview.total_rows} 条记录
                {preview.duplicates.length > 0 && `，检测到 ${preview.duplicates.length} 组重复`}
              </p>
            </div>

            {/* Field Mapping */}
            <div className="bg-white rounded-2xl border border-border-light p-4 space-y-3">
              <h3 className="text-sm font-bold">字段映射</h3>
              {preview.headers.map(header => (
                <div key={header} className="flex items-center gap-2">
                  <span className="text-xs text-slate-500 w-28 truncate shrink-0">{header}</span>
                  <ArrowRight className="w-4 h-4 text-slate-300 shrink-0" />
                  <select
                    value={mapping[header] || ''}
                    onChange={e => handleMappingChange(header, e.target.value)}
                    className="flex-1 text-xs border border-border-light rounded-lg px-2 py-1.5 bg-white outline-none focus:ring-1 focus:ring-primary-container"
                  >
                    <option value="">请选择...</option>
                    {fieldOptions.map(opt => (
                      <option key={opt.value} value={opt.value}>{opt.label}</option>
                    ))}
                  </select>
                </div>
              ))}
            </div>

            {/* Preview Table */}
            <div className="bg-white rounded-2xl border border-border-light overflow-hidden">
              <div className="p-4 border-b border-border-light">
                <h3 className="text-sm font-bold">数据预览</h3>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="bg-slate-50 border-b border-border-light">
                      <th className="text-left py-2 px-3 text-text-muted font-bold">#</th>
                      {preview.headers.map(h => (
                        <th key={h} className="text-left py-2 px-3 text-text-muted font-bold whitespace-nowrap">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {preview.rows.slice(0, 5).map((row, i) => (
                      <tr key={i} className="border-b border-border-light last:border-b-0">
                        <td className="py-2 px-3 text-slate-400">{i + 1}</td>
                        {preview.headers.map(h => (
                          <td key={h} className="py-2 px-3 text-slate-600 whitespace-nowrap max-w-[120px] truncate">{row[h] || '-'}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {preview.rows.length > 5 && (
                <div className="p-3 text-center text-xs text-text-muted border-t border-border-light">
                  共 {preview.rows.length} 行，仅显示前 5 行
                </div>
              )}
            </div>

            {/* Duplicates */}
            {preview.duplicates.length > 0 && (
              <div className="bg-white rounded-2xl border border-amber-200 p-4 space-y-3">
                <div className="flex items-center gap-2 text-amber-600">
                  <AlertTriangle className="w-5 h-5" />
                  <h3 className="text-sm font-bold">检测到重复联系人</h3>
                </div>
                <p className="text-xs text-text-muted">请为每组重复选择处理方式</p>
                {preview.duplicates.map((dup, idx) => (
                  <div key={idx} className="border border-border-light rounded-xl p-3 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-bold text-slate-600">重复组 #{idx + 1}</span>
                      <span className="text-[10px] bg-amber-50 text-amber-600 px-2 py-0.5 rounded-full">
                        相似度 {(dup.score * 100).toFixed(0)}%
                      </span>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                      <div className="bg-sky-50 rounded-lg p-2">
                        <p className="text-[10px] text-primary-container font-bold mb-1">新记录 (第 {dup.new_row + 1} 行)</p>
                        <p className="text-xs">{preview.rows[dup.new_row]?.['姓名'] || preview.rows[dup.new_row]?.['name'] || `行 #${dup.new_row + 1}`}</p>
                      </div>
                      <div className="bg-slate-50 rounded-lg p-2">
                        <p className="text-[10px] text-text-muted font-bold mb-1">已有联系人</p>
                        <p className="text-xs">{dup.existing.name}</p>
                        {dup.existing.phone && <p className="text-[10px] text-slate-400">{dup.existing.phone}</p>}
                      </div>
                    </div>
                    <div className="flex gap-2">
                      {(['skip', 'merge', 'update'] as const).map(action => (
                        <button
                          key={action}
                          onClick={() => handleDuplicateAction(idx, action)}
                          className={`flex-1 py-1.5 rounded-lg text-[10px] font-bold border transition-all ${
                            pendingDuplicates[idx] === action
                              ? action === 'skip' ? 'bg-slate-100 border-slate-300 text-slate-600'
                                : action === 'merge' ? 'bg-primary-container border-primary-container text-white'
                                : 'bg-amber-50 border-amber-300 text-amber-700'
                              : 'bg-white border-border-light text-slate-400'
                          }`}
                        >
                          {action === 'skip' ? '跳过' : action === 'merge' ? '合并' : '更新'}
                        </button>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Confirm */}
            <button
              onClick={handleImport}
              className="w-full py-3 bg-primary-container text-white rounded-xl font-bold text-sm active:scale-95 transition-transform shadow-lg"
            >
              确认导入 ({preview.total_rows} 条)
            </button>
          </div>
        )}

        {/* Importing */}
        {status === 'importing' && (
          <div className="flex flex-col items-center justify-center py-16">
            <RefreshCw className="w-10 h-10 text-primary-container animate-spin mb-4" />
            <p className="text-sm font-bold text-on-surface mb-2">正在导入...</p>
            <div className="w-48 h-2 bg-slate-200 rounded-full overflow-hidden">
              <div
                className="h-full bg-primary-container rounded-full transition-all duration-300"
                style={{ width: `${progress}%` }}
              />
            </div>
            <p className="text-xs text-text-muted mt-2">{progress}%</p>
          </div>
        )}

        {/* Done */}
        {status === 'done' && importResult && (
          <div className="flex flex-col items-center justify-center py-16 px-6">
            <div className="w-16 h-16 bg-green-50 rounded-full flex items-center justify-center mb-4">
              <CheckCircle2 className="w-8 h-8 text-emerald-500" />
            </div>
            <h2 className="text-lg font-bold text-on-surface mb-2">导入完成</h2>
            <div className="bg-white rounded-2xl border border-border-light p-4 w-full max-w-xs space-y-2 mb-6">
              <div className="flex justify-between text-sm">
                <span className="text-slate-500">成功导入</span>
                <span className="font-bold text-emerald-600">{importResult.imported} 条</span>
              </div>
              {importResult.merged > 0 && (
                <div className="flex justify-between text-sm">
                  <span className="text-slate-500">合并去重</span>
                  <span className="font-bold text-amber-600">{importResult.merged} 条</span>
                </div>
              )}
              {importResult.skipped > 0 && (
                <div className="flex justify-between text-sm">
                  <span className="text-slate-500">已跳过</span>
                  <span className="font-bold text-slate-400">{importResult.skipped} 条</span>
                </div>
              )}
            </div>
            <button
              onClick={() => navigate('/contacts', { state: { transition: 'push_back' } })}
              className="w-full max-w-xs py-3 bg-primary-container text-white rounded-xl font-bold text-sm active:scale-95 transition-transform shadow-lg"
            >
              返回人脉列表
            </button>
          </div>
        )}

        {/* Error */}
        {status === 'error' && (
          <div className="flex flex-col items-center justify-center py-16 px-6">
            <div className="w-16 h-16 bg-red-50 rounded-full flex items-center justify-center mb-4">
              <XCircle className="w-8 h-8 text-red-500" />
            </div>
            <h2 className="text-lg font-bold text-on-surface mb-2">导入失败</h2>
            <p className="text-sm text-red-500 mb-6 text-center">{errorMsg}</p>
            <div className="flex gap-3">
              <button
                onClick={() => setStatus('idle')}
                className="px-6 py-2.5 bg-white border border-border-light text-on-surface rounded-xl font-bold text-sm active:scale-95 transition-transform"
              >
                重新上传
              </button>
              <button
                onClick={() => navigate(-1)}
                className="px-6 py-2.5 bg-primary-container text-white rounded-xl font-bold text-sm active:scale-95 transition-transform"
              >
                返回
              </button>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
