/**
 * 三步冷启动引导 — 主页面
 *
 * i18n: 所有 text content / placeholder / aria-label 走 useTranslation()
 *
 * 使用 StepIndicator 展示三步骤进度：
 *   步骤1: 企业基本信息（公司名/行业/规模/地区）
 *   步骤2: 需求偏好（合作类型/目标/预算范围）
 *   步骤3: 模板选择 + 预览
 */
import React, { useState, useEffect, useCallback } from 'react';
import { useTranslation } from '../../i18n';
import StepIndicator from '../../components/onboarding/StepIndicator';
import TemplateSelector from '../../components/onboarding/TemplateSelector';
import DefaultFillPreview from '../../components/onboarding/DefaultFillPreview';
import type { Template } from '../../components/onboarding/TemplateSelector';
import { fetchTemplates, fetchOnboardingDefaults } from './api';
import {
  ONBOARDING_STEPS,
  INDUSTRY_OPTIONS,
  SCALE_OPTIONS,
  REGION_OPTIONS,
  COOPERATION_TYPE_OPTIONS,
  GOAL_OPTIONS,
  BUDGET_OPTIONS,
} from './types';
import type {
  EnterpriseInfo,
  DemandPreference,
  OnboardingDefaults,
} from './types';

// ── 步骤 1 表单组件 ──
interface Step1FormProps {
  value: EnterpriseInfo;
  onChange: (val: EnterpriseInfo) => void;
}

function Step1Form({ value, onChange }: Step1FormProps) {
  const { t } = useTranslation();
  const update = (field: keyof EnterpriseInfo, v: string) =>
    onChange({ ...value, [field]: v });

  return (
    <div className="space-y-5">
      {/* 公司名称 */}
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1.5">
          {t('onboarding_company_name_required', '公司名称 *')}
        </label>
        <input
          type="text"
          value={value.companyName}
          onChange={(e) => update('companyName', e.target.value)}
          placeholder={t('onboarding_company_name_placeholder', '请输入公司全称')}
          className="w-full px-3 py-2.5 rounded-lg border border-gray-300
                     text-sm text-gray-800 placeholder-gray-400
                     focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500
                     transition-colors"
        />
      </div>

      {/* 所属行业 */}
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1.5">
          {t('onboarding_industry_required', '所属行业 *')}
        </label>
        <select
          value={value.industry}
          onChange={(e) => update('industry', e.target.value)}
          className="w-full px-3 py-2.5 rounded-lg border border-gray-300
                     text-sm text-gray-800
                     focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500
                     transition-colors bg-white"
        >
          <option value="">{t('onboarding_industry_placeholder', '请选择行业')}</option>
          {INDUSTRY_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>{t(`industry_${opt.value}`, opt.label)}</option>
          ))}
        </select>
      </div>

      {/* 企业规模 + 地区（并排） */}
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1.5">
            {t('onboarding_scale', '企业规模')}
          </label>
          <select
            value={value.scale}
            onChange={(e) => update('scale', e.target.value)}
            className="w-full px-3 py-2.5 rounded-lg border border-gray-300
                       text-sm text-gray-800
                       focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500
                       transition-colors bg-white"
          >
            <option value="">{t('onboarding_scale_placeholder', '请选择')}</option>
            {SCALE_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>{t(`scale_${opt.value.replace(/-|\+/g, '_')}`, opt.label)}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1.5">
            {t('onboarding_region', '所在地区')}
          </label>
          <select
            value={value.region}
            onChange={(e) => update('region', e.target.value)}
            className="w-full px-3 py-2.5 rounded-lg border border-gray-300
                       text-sm text-gray-800
                       focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500
                       transition-colors bg-white"
          >
            <option value="">{t('onboarding_region_placeholder', '请选择')}</option>
            {REGION_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>{t(`region_${opt.value}`, opt.label)}</option>
            ))}
          </select>
        </div>
      </div>
    </div>
  );
}

// ── 步骤 2 表单组件 ──
interface Step2FormProps {
  value: DemandPreference;
  onChange: (val: DemandPreference) => void;
}

function Step2Form({ value, onChange }: Step2FormProps) {
  const { t } = useTranslation();
  const update = (field: keyof DemandPreference, v: string) =>
    onChange({ ...value, [field]: v });

  return (
    <div className="space-y-5">
      {/* 合作类型 */}
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1.5">
          {t('onboarding_cooperation_type_required', '合作类型 *')}
        </label>
        <select
          value={value.cooperationType}
          onChange={(e) => update('cooperationType', e.target.value)}
          className="w-full px-3 py-2.5 rounded-lg border border-gray-300
                     text-sm text-gray-800
                     focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500
                     transition-colors bg-white"
        >
          <option value="">{t('onboarding_cooperation_type_placeholder', '请选择合作类型')}</option>
          {COOPERATION_TYPE_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>{t(`coop_${opt.value}`, opt.label)}</option>
          ))}
        </select>
      </div>

      {/* 合作目标 */}
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1.5">
          {t('onboarding_goal', '合作目标')}
        </label>
        <select
          value={value.goal}
          onChange={(e) => update('goal', e.target.value)}
          className="w-full px-3 py-2.5 rounded-lg border border-gray-300
                     text-sm text-gray-800
                     focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500
                     transition-colors bg-white"
        >
          <option value="">{t('onboarding_goal_placeholder', '请选择目标')}</option>
          {GOAL_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>{t(`goal_${opt.value}`, opt.label)}</option>
          ))}
        </select>
      </div>

      {/* 预算范围 */}
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1.5">
          {t('onboarding_budget', '预算范围')}
        </label>
        <select
          value={value.budgetRange}
          onChange={(e) => update('budgetRange', e.target.value)}
          className="w-full px-3 py-2.5 rounded-lg border border-gray-300
                     text-sm text-gray-800
                     focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500
                     transition-colors bg-white"
        >
          <option value="">{t('onboarding_budget_placeholder', '请选择预算')}</option>
          {BUDGET_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>{t(`budget_${opt.value}`, opt.label)}</option>
          ))}
        </select>
      </div>
    </div>
  );
}

// ── 步骤 3 模板选择 + 预览 ──
interface Step3PanelProps {
  templates: Template[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  enterpriseInfo: EnterpriseInfo;
}

function Step3Panel({ templates, selectedId, onSelect, enterpriseInfo }: Step3PanelProps) {
  const { t } = useTranslation();

  // 构建预览用户信息（从步骤1的企业信息推导）
  const previewUserInfo = {
    name: enterpriseInfo.companyName || t('onboarding_preview_company_placeholder', '您的企业'),
    company: enterpriseInfo.companyName || undefined,
    position: enterpriseInfo.industry ? `${enterpriseInfo.industry} · ${enterpriseInfo.scale || ''}`.trim() : undefined,
    address: enterpriseInfo.region || undefined,
  };

  return (
    <div className="space-y-6">
      {/* 模板选择 */}
      <div>
        <h3 className="text-sm font-semibold text-gray-700 mb-3">{t('onboarding_template_title', '选择名片模板')}</h3>
        <TemplateSelector
          templates={templates}
          selectedId={selectedId}
          onSelect={onSelect}
        />
      </div>

      {/* 预览 */}
      {selectedId && (
        <div>
          <h3 className="text-sm font-semibold text-gray-700 mb-3">{t('onboarding_preview_title', '自动填充预览')}</h3>
          <DefaultFillPreview
            userInfo={previewUserInfo}
            templateId={selectedId}
          />
        </div>
      )}

      {!selectedId && (
        <div className="text-center py-8">
          <p className="text-sm text-gray-400">{t('onboarding_preview_hint', '请先选择一个名片模板')}</p>
        </div>
      )}
    </div>
  );
}

// ── 验证辅助 ──
function validateStep1(info: EnterpriseInfo, t: (key: string, fallback?: string) => string): string | null {
  if (!info.companyName.trim()) return t('onboarding_error_company_name', '请填写公司名称');
  if (!info.industry) return t('onboarding_error_industry', '请选择所属行业');
  return null;
}

function validateStep2(pref: DemandPreference, t: (key: string, fallback?: string) => string): string | null {
  if (!pref.cooperationType) return t('onboarding_error_cooperation_type', '请选择合作类型');
  return null;
}

// ── 主页面 ──
export default function OnboardingPage() {
  const { t, currentLang } = useTranslation();
  const [currentStep, setCurrentStep] = useState(1);
  const [enterpriseInfo, setEnterpriseInfo] = useState<EnterpriseInfo>({
    companyName: '',
    industry: '',
    scale: '',
    region: '',
  });
  const [demandPreference, setDemandPreference] = useState<DemandPreference>({
    cooperationType: '',
    goal: '',
    budgetRange: '',
  });
  const [selectedTemplateId, setSelectedTemplateId] = useState<string | null>(null);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 加载模板 & 默认配置
  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const [tmplList, defaults] = await Promise.all([
          fetchTemplates(),
          fetchOnboardingDefaults(),
        ]);

        if (cancelled) return;

        setTemplates(tmplList);

        // 如果后端返回了默认配置，填充步骤1/2
        if (defaults) {
          fillDefaults(defaults);
        }
      } catch (err) {
        if (!cancelled) {
          console.warn(t('onboarding_error_load_failed', '[Onboarding] 数据加载失败，使用本地默认值'), err);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    function fillDefaults(d: OnboardingDefaults) {
      if (d.enterpriseInfo) {
        setEnterpriseInfo((prev) => ({
          ...prev,
          ...d.enterpriseInfo,
        }));
      }
      if (d.demandPreference) {
        setDemandPreference((prev) => ({
          ...prev,
          ...d.demandPreference,
        }));
      }
    }

    load();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentLang]);

  // 步骤导航
  const goToStep = useCallback((stepId: number) => {
    setError(null);
    setCurrentStep(stepId);
  }, []);

  const handleNext = useCallback(() => {
    setError(null);

    // 步骤校验
    if (currentStep === 1) {
      const err = validateStep1(enterpriseInfo, t);
      if (err) { setError(err); return; }
    }
    if (currentStep === 2) {
      const err = validateStep2(demandPreference, t);
      if (err) { setError(err); return; }
    }

    if (currentStep < 3) {
      setCurrentStep((s) => s + 1);
    }
  }, [currentStep, enterpriseInfo, demandPreference, t]);

  const handlePrev = useCallback(() => {
    setError(null);
    if (currentStep > 1) setCurrentStep((s) => s - 1);
  }, [currentStep]);

  const handleSubmit = useCallback(async () => {
    setSubmitting(true);
    setError(null);

    try {
      // 提交三步引导结果
      const payload = {
        enterpriseInfo,
        demandPreference,
        selectedTemplateId,
      };
      const resp = await fetch('/api/v1/onboarding/complete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!resp.ok) {
        throw new Error(`${t('onboarding_error_submit_failed', '提交失败')} (${resp.status})`);
      }

      // 引导完成后可跳转到名片主页或仪表盘
      window.location.href = '/dashboard';
    } catch (err) {
      setError(err instanceof Error ? err.message : t('onboarding_error_submit_failed', '提交失败，请重试'));
    } finally {
      setSubmitting(false);
    }
  }, [enterpriseInfo, demandPreference, selectedTemplateId, t]);

  // 渲染当前步骤内容
  const renderStepContent = () => {
    switch (currentStep) {
      case 1:
        return (
          <div className="max-w-lg mx-auto">
            <div className="mb-6">
              <h2 className="text-lg font-semibold text-gray-800">{t('onboarding_step1_title', '企业基本信息')}</h2>
              <p className="text-sm text-gray-500 mt-1">
                {t('onboarding_step1_desc', '请填写您的企业信息，我们将据此为您个性化推荐服务')}
              </p>
            </div>
            <Step1Form value={enterpriseInfo} onChange={setEnterpriseInfo} />
          </div>
        );

      case 2:
        return (
          <div className="max-w-lg mx-auto">
            <div className="mb-6">
              <h2 className="text-lg font-semibold text-gray-800">{t('onboarding_step2_title', '需求偏好')}</h2>
              <p className="text-sm text-gray-500 mt-1">
                {t('onboarding_step2_desc', '告诉我们您的合作意向与预算范围，以便我们匹配最合适的方案')}
              </p>
            </div>
            <Step2Form value={demandPreference} onChange={setDemandPreference} />
          </div>
        );

      case 3:
        return (
          <div className="max-w-2xl mx-auto">
            <div className="mb-6">
              <h2 className="text-lg font-semibold text-gray-800">{t('onboarding_template_title', '模板选择与预览')}</h2>
              <p className="text-sm text-gray-500 mt-1">
                {t('onboarding_template_desc', '选择一个符合企业形象的名片模板，系统将自动填充信息')}
              </p>
            </div>
            <Step3Panel
              templates={templates}
              selectedId={selectedTemplateId}
              onSelect={setSelectedTemplateId}
              enterpriseInfo={enterpriseInfo}
            />
          </div>
        );

      default:
        return null;
    }
  };

  // ── 骨架屏加载态 ──
  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-b from-gray-50 to-white flex items-center justify-center">
        <div className="text-center space-y-4">
          <div className="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin mx-auto" />
          <p className="text-sm text-gray-400">{t('onboarding_loading', '加载引导配置中...')}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-b from-gray-50 to-white">
      <div className="max-w-4xl mx-auto px-4 py-8">
        {/* 标题 */}
        <div className="text-center mb-8">
          <h1 className="text-2xl font-bold text-gray-900">{t('onboarding_title', '三步冷启动')}</h1>
          <p className="text-sm text-gray-500 mt-1">
            {t('onboarding_subtitle', '快速完成企业配置，开启数字化名片之旅')}
          </p>
        </div>

        {/* 步骤指示器 (使用 i18n 翻译后的步骤标签) */}
        <div className="mb-10 px-2">
          <StepIndicator
            steps={[
              { id: 1, label: t('onboarding_step_1', '企业信息'), description: t('onboarding_step_1_desc', '填写企业基本信息') },
              { id: 2, label: t('onboarding_step_2', '需求偏好'), description: t('onboarding_step_2_desc', '设置合作偏好与目标') },
              { id: 3, label: t('onboarding_step_3', '模板选择'), description: t('onboarding_step_3_desc', '选择名片模板并预览') },
            ]}
            currentStep={currentStep}
            onStepClick={(stepId) => {
              // 只允许回退到已完成的步骤
              if (stepId < currentStep) goToStep(stepId);
            }}
          />
        </div>

        {/* 错误提示 */}
        {error && (
          <div className="max-w-lg mx-auto mb-6 px-4 py-3 rounded-lg bg-red-50 border border-red-200 text-sm text-red-700 flex items-start gap-2">
            <svg className="w-4 h-4 mt-0.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <span>{error}</span>
          </div>
        )}

        {/* 步骤内容 */}
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6 sm:p-8 mb-6">
          {renderStepContent()}
        </div>

        {/* 操作按钮 */}
        <div className="flex items-center justify-between max-w-lg mx-auto">
          <div>
            {currentStep > 1 && (
              <button
                type="button"
                onClick={handlePrev}
                className="inline-flex items-center gap-1.5 px-4 py-2.5 rounded-lg
                           text-sm font-medium text-gray-600 bg-white border border-gray-300
                           hover:bg-gray-50 hover:text-gray-800
                           focus:outline-none focus:ring-2 focus:ring-gray-300
                           transition-colors"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
                </svg>
                {t('onboarding_prev', '上一步')}
              </button>
            )}
          </div>

          <div>
            {currentStep < 3 ? (
              <button
                type="button"
                onClick={handleNext}
                className="inline-flex items-center gap-1.5 px-5 py-2.5 rounded-lg
                           text-sm font-medium text-white bg-blue-600
                           hover:bg-blue-700 active:bg-blue-800
                           focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2
                           transition-colors shadow-sm shadow-blue-200"
              >
                {t('onboarding_next', '下一步')}
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                </svg>
              </button>
            ) : (
              <button
                type="button"
                onClick={handleSubmit}
                disabled={submitting || !selectedTemplateId}
                className="inline-flex items-center gap-1.5 px-6 py-2.5 rounded-lg
                           text-sm font-medium text-white bg-green-600
                           hover:bg-green-700 active:bg-green-800
                           focus:outline-none focus:ring-2 focus:ring-green-500 focus:ring-offset-2
                           transition-colors shadow-sm shadow-green-200
                           disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {submitting ? (
                  <>
                    <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                    {t('onboarding_submitting', '提交中...')}
                  </>
                ) : (
                  <>
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                    </svg>
                    {t('onboarding_submit', '完成引导')}
                  </>
                )}
              </button>
            )}
          </div>
        </div>

        {/* 步骤提示 */}
        <div className="text-center mt-6">
          <p className="text-xs text-gray-400">
            {t('onboarding_step_of', '步骤 {current} / {total}')
              .replace('{current}', String(currentStep))
              .replace('{total}', '3')}
          </p>
        </div>

        {/* 语言切换 (调试/设置用) */}
        {currentLang !== 'ko' && (
          <div className="text-center mt-4">
            <button
              type="button"
              onClick={() => {
                const { setLang } = require('../../i18n');
                // 使用全局方式切换 — 但 setLang 是 hook 内部
                // 由 Provider 提供，此处通过 cookie 直接切换
                document.cookie = 'lang=ko; path=/; max-age=31536000';
                window.location.reload();
              }}
              className="text-xs text-gray-400 hover:text-gray-600 underline underline-offset-2"
            >
              한국어로 전환
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
