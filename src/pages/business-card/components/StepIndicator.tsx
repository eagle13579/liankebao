import type { Step } from '../types';
const STEPS: {key:Step;label:string}[] = [
  {key:'upload',label:'上传'}, {key:'review',label:'编辑'},
  {key:'preview',label:'预览'}, {key:'matched',label:'匹配'},
];
interface Props { currentStep: Step; }
export default function StepIndicator({ currentStep }: Props) {
  const idx = STEPS.findIndex(s => s.key === currentStep);
  return (
    <div className="flex items-center justify-center gap-2 py-4 px-4">
      {STEPS.map((s,i) => (
        <div key={s.key} className="flex items-center gap-2">
          <div className={'w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium ' + (i<=idx ? 'bg-blue-600 text-white' : 'bg-gray-200 text-gray-500')}>
            {i+1}
          </div>
          <span className={'text-sm ' + (i<=idx ? 'text-blue-600 font-medium' : 'text-gray-400')}>{s.label}</span>
          {i<STEPS.length-1 && <div className={'w-8 h-0.5 ' + (i<idx ? 'bg-blue-600' : 'bg-gray-200')} />}
        </div>
      ))}
    </div>
  );
}
