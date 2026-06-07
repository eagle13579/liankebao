import { Sparkles, RefreshCw } from 'lucide-react';
import FieldInput from './FieldInput';
import type { CardFields } from '../types';
interface Props { fields: CardFields; suggestions: string[]; rawText: string; onUpdateField: (k:string,v:string)=>void; onGenerate: ()=>void; onReset: ()=>void; loading: boolean; error: string|null; }
const FIELD_CONFIG = [
  {key:'name',label:'姓名',placeholder:'输入姓名',icon:'\ud83d\udc64'},
  {key:'position',label:'职位',placeholder:'输入职位',icon:'\ud83d\udcbc'},
  {key:'company',label:'公司',placeholder:'输入公司名称',icon:'\ud83c\udfe2'},
  {key:'phone',label:'手机',placeholder:'输入手机号',icon:'\ud83d\udcf1'},
  {key:'email',label:'邮箱',placeholder:'输入邮箱',icon:'\ud83d\udce7'},
  {key:'wechat',label:'微信',placeholder:'输入微信号',icon:'\ud83d\udcac'},
  {key:'address',label:'地址',placeholder:'输入地址',icon:'\ud83d\udccd'},
  {key:'website',label:'官网',placeholder:'https://',icon:'\ud83c\udf10'},
];
export default function ReviewForm({fields,suggestions,rawText,onUpdateField,onGenerate,onReset,loading,error}:Props) {
  return (
    <div className="max-w-2xl mx-auto p-6">
      {suggestions.length>0 && (
        <div className="mb-6 p-4 bg-blue-50 rounded-xl border border-blue-200">
          <div className="flex items-center gap-2 text-blue-700 font-medium mb-2"><Sparkles className="w-4 h-4" />AI 建议</div>
          <ul className="text-sm text-blue-600 space-y-1">{suggestions.map((s,i)=><li key={i}>{s}</li>)}</ul>
        </div>
      )}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-x-4">{FIELD_CONFIG.map(f=>
        <FieldInput key={f.key} label={f.label} value={fields[f.key]} onChange={v=>onUpdateField(f.key,v)} placeholder={f.placeholder} icon={<span>{f.icon}</span>} />
      )}</div>
      {rawText && <details className="mt-4"><summary className="text-sm text-gray-500 cursor-pointer">原始识别文本</summary><pre className="mt-2 p-3 bg-gray-50 rounded-lg text-xs text-gray-600 whitespace-pre-wrap max-h-32 overflow-y-auto">{rawText}</pre></details>}
      {error && <div className="mt-4 p-3 bg-red-50 text-red-600 rounded-lg text-sm">{error}</div>}
      <div className="flex gap-3 mt-6">
        <button onClick={onGenerate} disabled={loading} className="flex-1 px-6 py-3 bg-blue-600 text-white rounded-xl hover:bg-blue-700 disabled:opacity-50 transition-colors">
          {loading ? '生成中...' : '生成数字名片'}
        </button>
        <button onClick={onReset} className="px-4 py-3 border border-gray-300 rounded-xl text-gray-600 hover:bg-gray-50 transition-colors">
          <RefreshCw className="w-5 h-5" />
        </button>
      </div>
    </div>
  );
}
