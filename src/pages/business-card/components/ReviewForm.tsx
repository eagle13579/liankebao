import { ArrowLeft, Sparkles, Loader2 } from 'lucide-react';
import FieldInput from './FieldInput';
import type { CardFields } from '../types';

interface ReviewFormProps {
  fields: CardFields;
  suggestions: string[];
  rawText: string;
  onUpdateField: (key: keyof CardFields, value: string) => void;
  onGenerate: () => void;
  onReset: () => void;
  onBack: () => void;
  loading: boolean;
  error: string;
}

const FIELD_GROUPS: { key: keyof CardFields; label: string; placeholder: string; type?: string; colSpan?: 'full' | 'half' }[] = [
  { key: 'name', label: '姓名 *', placeholder: '请输入姓名', colSpan: 'half' },
  { key: 'position', label: '职位', placeholder: '请输入职位', colSpan: 'half' },
  { key: 'company', label: '公司', placeholder: '请输入公司名称', colSpan: 'full' },
  { key: 'phone', label: '手机', placeholder: '请输入手机号', type: 'tel', colSpan: 'half' },
  { key: 'email', label: '邮箱', placeholder: '请输入邮箱', type: 'email', colSpan: 'half' },
  { key: 'wechat', label: '微信', placeholder: '请输入微信号', colSpan: 'half' },
  { key: 'website', label: '官网', placeholder: '请输入网址', colSpan: 'half' },
  { key: 'address', label: '地址', placeholder: '请输入地址', colSpan: 'full' },
];

export default function ReviewForm({
  fields, suggestions, rawText, onUpdateField, onGenerate, onReset, onBack, loading, error,
}: ReviewFormProps) {
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <button onClick={onBack} className="p-2 rounded-lg hover:bg-slate-100 transition-colors">
          <ArrowLeft className="w-5 h-5" />
        </button>
        <div>
          <h2 className="text-lg font-bold text-on-surface">确认名片信息</h2>
          <p className="text-xs text-text-muted">请核对 AI 提取的信息，可手动修改</p>
        </div>
      </div>

      {suggestions.length > 0 && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-3">
          <div className="flex gap-2">
            <Sparkles className="w-4 h-4 text-amber-500 mt-0.5 shrink-0" />
            <div className="text-xs text-amber-800 space-y-1">
              {suggestions.map((s, i) => <p key={i}>{s}</p>)}
            </div>
          </div>
        </div>
      )}

      {rawText && (
        <details className="bg-slate-50 rounded-xl p-3">
          <summary className="text-xs text-text-muted cursor-pointer select-none">OCR 原始识别文字</summary>
          <p className="text-xs text-text-muted mt-2 whitespace-pre-wrap">{rawText}</p>
        </details>
      )}

      {error && (
        <div className="bg-rose-50 border border-rose-200 rounded-xl p-3 text-xs text-rose-700">{error}</div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {FIELD_GROUPS.map((f) => (
          <div key={f.key} className={f.colSpan === 'full' ? 'sm:col-span-2' : ''}>
            <FieldInput
              label={f.label}
              value={fields[f.key] || ''}
              onChange={(v) => onUpdateField(f.key, v)}
              placeholder={f.placeholder}
              type={f.type}
            />
          </div>
        ))}
      </div>

      <div className="flex gap-3">
        <button onClick={onReset} className="flex-1 py-3 px-4 rounded-xl border border-border-light text-on-surface font-medium text-sm hover:bg-slate-50 transition-colors">
          重新上传
        </button>
        <button onClick={onGenerate} disabled={loading || !fields.name?.trim()}
          className="flex-1 py-3 px-4 rounded-xl bg-primary text-white font-medium text-sm hover:bg-primary-container transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2">
          {loading ? (
            <><Loader2 className="w-4 h-4 animate-spin" />生成中...</>
          ) : (
            <><Sparkles className="w-4 h-4" />生成数字名片</>
          )}
        </button>
      </div>
    </div>
  );
}
