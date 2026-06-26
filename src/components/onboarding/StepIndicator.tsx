/**
 * 三步冷启动引导 — 步骤指示器
 * 展示当前所处步骤及整体进度，支持点击跳转已完成步骤
 *
 * i18n: 标签/描述由父组件传入、aria-label 走 useTranslation()
 */
import React from 'react';
import { useTranslation } from '../../i18n';

export interface Step {
  id: number;
  label: string;
  description?: string;
}

export interface StepIndicatorProps {
  steps: Step[];
  currentStep: number; // 1-based index
  onStepClick?: (stepId: number) => void;
  className?: string;
}

const STATUS_ICONS: Record<string, string> = {
  completed: '✓',
  active: '',
  pending: '',
};

export default function StepIndicator({
  steps,
  currentStep,
  onStepClick,
  className = '',
}: StepIndicatorProps) {
  const { t } = useTranslation();

  return (
    <nav className={`w-full ${className}`} aria-label={t('onboarding_step_indicator_aria', '三步引导进度')}>
      <ol className="flex items-center justify-between w-full">
        {steps.map((step, index) => {
          const stepNumber = index + 1;
          const isCompleted = stepNumber < currentStep;
          const isActive = stepNumber === currentStep;
          const isPending = stepNumber > currentStep;

          const barVisible = index < steps.length - 1;

          return (
            <li key={step.id} className="flex items-center flex-1">
              <button
                type="button"
                disabled={isPending && !onStepClick}
                onClick={() => {
                  if ((isCompleted || isActive) && onStepClick) {
                    onStepClick(step.id);
                  }
                }}
                className={`
                  flex items-center gap-2 group transition-all duration-300
                  ${isPending ? 'cursor-not-allowed' : 'cursor-pointer'}
                `}
                aria-current={isActive ? 'step' : undefined}
              >
                {/* Step circle */}
                <span
                  className={`
                    inline-flex items-center justify-center w-9 h-9 rounded-full
                    text-sm font-bold shrink-0 transition-all duration-300
                    ${
                      isCompleted
                        ? 'bg-blue-600 text-white shadow-md shadow-blue-200'
                        : ''
                    }
                    ${
                      isActive
                        ? 'bg-blue-600 text-white ring-4 ring-blue-100 shadow-md shadow-blue-200'
                        : ''
                    }
                    ${
                      isPending
                        ? 'bg-gray-100 text-gray-400 border-2 border-dashed border-gray-300'
                        : ''
                    }
                  `}
                >
                  {isCompleted ? STATUS_ICONS.completed : stepNumber}
                </span>

                {/* Label + description */}
                <div className="hidden sm:block text-left">
                  <p
                    className={`
                      text-sm font-medium leading-tight transition-colors duration-300
                      ${isCompleted ? 'text-blue-600' : ''}
                      ${isActive ? 'text-gray-900' : ''}
                      ${isPending ? 'text-gray-400' : ''}
                    `}
                  >
                    {step.label}
                  </p>
                  {step.description && (
                    <p
                      className={`
                        text-xs leading-tight mt-0.5 transition-colors duration-300
                        ${isActive ? 'text-gray-500' : ''}
                        ${isPending ? 'text-gray-300' : ''}
                      `}
                    >
                      {step.description}
                    </p>
                  )}
                </div>
              </button>

              {/* Connector line */}
              {barVisible && (
                <div className="flex-1 mx-3 sm:mx-4">
                  <div className="h-0.5 w-full rounded-full bg-gray-200 overflow-hidden">
                    <div
                      className={`
                        h-full rounded-full transition-all duration-500 ease-out
                        ${stepNumber < currentStep ? 'w-full bg-blue-500' : ''}
                        ${stepNumber === currentStep ? 'w-1/2 bg-blue-500 animate-pulse' : ''}
                        ${stepNumber > currentStep ? 'w-0' : ''}
                      `}
                    />
                  </div>
                </div>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
