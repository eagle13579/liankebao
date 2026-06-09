import type { Step } from '../types';

interface StepIndicatorProps {
  currentStep: Step;
}

const STEPS: Step[] = ['upload', 'review', 'preview'];

const STEP_LABELS: Record<Step, string> = {
  upload: '上传',
  review: '编辑',
  preview: '预览',
  matched: '匹配',
};

export default function StepIndicator({ currentStep }: StepIndicatorProps) {
  const idx = STEPS.indexOf(currentStep);

  return (
    <div className="flex items-center gap-2 mb-6">
      {STEPS.map((s, i) => {
        const isActive = i <= idx;
        return (
          <div key={s} className="flex items-center gap-2">
            <div className={`w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-bold transition-colors ${
              isActive ? 'bg-primary text-white' : 'bg-slate-200 text-slate-400'
            }`}>
              {i + 1}
            </div>
            {i < STEPS.length - 1 && (
              <div className={`w-8 h-0.5 transition-colors ${
                i < idx ? 'bg-primary' : 'bg-slate-200'
              }`} />
            )}
          </div>
        );
      })}
    </div>
  );
}
