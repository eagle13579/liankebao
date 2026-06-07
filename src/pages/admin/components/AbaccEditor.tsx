/**
 * 链客宝 - ABACC五步话术编辑器组件
 * 注入点：话术模板编辑器的ABACC五步框架编辑区域
 * 规则：纯新增，不修改现有业务逻辑
 */

import React, { useState } from 'react';
import type { AbaccStep } from '../salesScriptTypes';
import { ABACC_STEPS_META } from '../salesScriptTypes';

interface Props {
  steps: AbaccStep[];
  onChange: (steps: AbaccStep[]) => void;
}

const STEP_IDS: AbaccStep['step_id'][] = ['attention', 'before', 'after', 'curiosity', 'call_action'];

export default function AbaccEditor({ steps, onChange }: Props) {
  const [activeStep, setActiveStep] = useState(0);

  const handleStepChange = (index: number, field: keyof AbaccStep, value: string | string[]) => {
    const updated = steps.map((s, i) => (i === index ? { ...s, [field]: value } : s));
    onChange(updated);
  };

  const handleExampleChange = (stepIndex: number, exampleIndex: number, value: string) => {
    const step = steps[stepIndex];
    const examples = [...step.examples];
    examples[exampleIndex] = value;
    handleStepChange(stepIndex, 'examples', examples);
  };

  const addExample = (stepIndex: number) => {
    const step = steps[stepIndex];
    handleStepChange(stepIndex, 'examples', [...step.examples, '']);
  };

  const removeExample = (stepIndex: number, exampleIndex: number) => {
    const step = steps[stepIndex];
    handleStepChange(stepIndex, 'examples', step.examples.filter((_, i) => i !== exampleIndex));
  };

  if (!steps || steps.length === 0) {
    return (
      <div className="p-6 text-center text-gray-400">
        暂无ABACC话术步骤，请先选择或创建模板
      </div>
    );
  }

  const currentStep = steps[activeStep];
  const meta = ABACC_STEPS_META[currentStep?.step_id] || {};

  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
      {/* ABACC五步导航条 */}
      <div className="flex border-b border-gray-200 bg-gray-50 overflow-x-auto">
        {steps.map((step, index) => {
          const m = ABACC_STEPS_META[step.step_id] || {};
          const isActive = index === activeStep;
          return (
            <button
              key={step.step_id}
              onClick={() => setActiveStep(index)}
              className={`
                flex items-center gap-1.5 px-4 py-3 text-sm font-medium whitespace-nowrap border-b-2 transition-colors
                ${isActive
                  ? 'border-blue-500 text-blue-700 bg-white'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:bg-gray-100'
                }
              `}
            >
              <span>{m.icon}</span>
              <span>{m.label}</span>
            </button>
          );
        })}
      </div>

      {/* 当前步骤编辑区 */}
      <div className="p-5 space-y-4">
        {/* 标题 */}
        <div>
          <label className="block text-xs font-medium text-gray-500 mb-1">步骤标题</label>
          <input
            type="text"
            value={currentStep.title}
            onChange={(e) => handleStepChange(activeStep, 'title', e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            style={{ borderLeft: `4px solid ${meta.color || '#3B82F6'}` }}
          />
        </div>

        {/* 话术模板 */}
        <div>
          <label className="block text-xs font-medium text-gray-500 mb-1">
            话术模板 ({currentStep.step_id === 'attention' ? '破冰开场' :
              currentStep.step_id === 'before' ? '痛点唤醒' :
              currentStep.step_id === 'after' ? '愿景描绘' :
              currentStep.step_id === 'curiosity' ? '差异化卖点' : '行动引导'})
          </label>
          <textarea
            value={currentStep.template}
            onChange={(e) => handleStepChange(activeStep, 'template', e.target.value)}
            rows={3}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm resize-y focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            placeholder="输入话术模板，使用[占位符]标记可变部分"
          />
        </div>

        {/* 示例话术 */}
        <div>
          <div className="flex items-center justify-between mb-1">
            <label className="text-xs font-medium text-gray-500">示例话术</label>
            <button
              onClick={() => addExample(activeStep)}
              className="text-xs text-blue-600 hover:text-blue-700"
            >
              + 添加示例
            </button>
          </div>
          <div className="space-y-2">
            {currentStep.examples.map((ex, ei) => (
              <div key={ei} className="flex gap-2">
                <input
                  type="text"
                  value={ex}
                  onChange={(e) => handleExampleChange(activeStep, ei, e.target.value)}
                  className="flex-1 px-3 py-1.5 border border-gray-300 rounded-lg text-sm"
                  placeholder="示例话术..."
                />
                <button
                  onClick={() => removeExample(activeStep, ei)}
                  className="px-2 text-red-400 hover:text-red-600 text-sm"
                  title="删除"
                >
                  x
                </button>
              </div>
            ))}
          </div>
        </div>

        {/* 技巧提示 */}
        <div>
          <label className="block text-xs font-medium text-gray-500 mb-1">使用技巧</label>
          <div className="flex flex-wrap gap-2">
            {currentStep.tips.map((tip, ti) => (
              <span
                key={ti}
                className="px-2.5 py-1 bg-blue-50 text-blue-700 text-xs rounded-full border border-blue-100"
              >
                {tip}
              </span>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
