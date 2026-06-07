/**
 * 链客宝 - 张力武器库组件
 * 注入点：话术模板编辑器的张力武器面板（数据增强器+引导词+自检评分）
 * 规则：纯新增，不修改现有业务逻辑
 */

import React, { useState, useEffect } from 'react';
import type { AugmenterMode, MagicWords, TensionAnalysis, AugmenterData } from '../salesScriptTypes';
import * as api from '../salesScriptApi';

type Tab = 'augmenter' | 'magic-words' | 'tension-check';

export default function TensionWeaponLibrary() {
  const [activeTab, setActiveTab] = useState<Tab>('augmenter');
  const [augmenterMode, setAugmenterMode] = useState<AugmenterMode>('analogy');
  const [augmenterData, setAugmenterData] = useState<Record<string, AugmenterData> | null>(null);
  const [magicWords, setMagicWords] = useState<MagicWords | null>(null);
  const [analysisText, setAnalysisText] = useState('');
  const [analysis, setAnalysis] = useState<TensionAnalysis | null>(null);
  const [loading, setLoading] = useState(false);

  // 加载数据增强器
  useEffect(() => {
    api.fetchDataAugmenter().then(setAugmenterData).catch(() => {});
    api.fetchMagicWords().then(setMagicWords).catch(() => {});
  }, []);

  const currentAugmenter = augmenterData?.[augmenterMode];

  const handleAnalyze = async () => {
    if (!analysisText.trim()) return;
    setLoading(true);
    try {
      const result = await api.analyzeTension(analysisText);
      setAnalysis(result);
    } catch (e) {
      setAnalysis({
        score: 0,
        level: 'low',
        label: '分析失败',
        description: '请检查网络连接或稍后重试',
        symptoms: [],
        fixes: [],
      });
    } finally {
      setLoading(false);
    }
  };

  const tabs: { key: Tab; label: string; icon: string }[] = [
    { key: 'augmenter', label: '数据增强器', icon: '📊' },
    { key: 'magic-words', label: '话术引导词', icon: '✨' },
    { key: 'tension-check', label: '张力自检评分', icon: '📏' },
  ];

  const levelColors: Record<string, string> = {
    low: 'bg-red-50 border-red-200 text-red-700',
    medium: 'bg-yellow-50 border-yellow-200 text-yellow-700',
    high: 'bg-green-50 border-green-200 text-green-700',
  };

  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
      {/* Tab导航 */}
      <div className="flex border-b border-gray-200 bg-gray-50">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`
              flex items-center gap-1.5 px-4 py-3 text-sm font-medium whitespace-nowrap border-b-2 transition-colors
              ${activeTab === tab.key
                ? 'border-purple-500 text-purple-700 bg-white'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:bg-gray-100'
              }
            `}
          >
            <span>{tab.icon}</span>
            <span>{tab.label}</span>
          </button>
        ))}
      </div>

      <div className="p-5">
        {/* ===== 数据增强器 ===== */}
        {activeTab === 'augmenter' && (
          <div className="space-y-4">
            <p className="text-xs text-gray-500 mb-3">
              将平淡数据转化成有冲击力的说服语言。选择增强模式，参考示例改写您的话术。
            </p>

            {/* 模式切换 */}
            <div className="flex gap-2 flex-wrap">
              {(['analogy', 'unit_transform', 'comparison'] as AugmenterMode[]).map((mode) => {
                const labels: Record<AugmenterMode, string> = {
                  analogy: '类比模式',
                  unit_transform: '单位变换',
                  comparison: '对比模式',
                };
                return (
                  <button
                    key={mode}
                    onClick={() => setAugmenterMode(mode)}
                    className={`
                      px-3 py-1.5 text-sm rounded-lg border transition-colors
                      ${augmenterMode === mode
                        ? 'bg-purple-50 border-purple-300 text-purple-700 font-medium'
                        : 'bg-white border-gray-200 text-gray-600 hover:border-gray-300'
                      }
                    `}
                  >
                    {labels[mode]}
                  </button>
                );
              })}
            </div>

            {/* 示例列表 */}
            {currentAugmenter && (
              <div className="space-y-2">
                <p className="text-sm font-medium text-gray-700">{currentAugmenter.description}</p>
                {currentAugmenter.examples.map((ex, i) => (
                  <div key={i} className="p-3 bg-purple-50 rounded-lg border border-purple-100">
                    <div className="text-xs text-gray-500 mb-1">
                      <span className="font-medium text-gray-700">输入：</span>{ex.input}
                    </div>
                    <div className="text-sm text-purple-800">
                      <span className="font-medium">输出：</span>{ex.output}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* ===== 话术引导词 ===== */}
        {activeTab === 'magic-words' && magicWords && (
          <div className="space-y-4">
            <p className="text-xs text-gray-500 mb-3">
              在话术中嵌入引导词能显著提升说服力。按分类查看推荐词汇。
            </p>
            {Object.entries(magicWords).map(([key, category]) => (
              <div key={key} className="p-3 bg-amber-50 rounded-lg border border-amber-100">
                <h4 className="text-sm font-medium text-amber-800 mb-2">{category.name}</h4>
                <div className="flex flex-wrap gap-1.5">
                  {category.words.map((word, wi) => (
                    <span
                      key={wi}
                      onClick={() => {
                        // 点击复制到剪贴板
                        navigator.clipboard.writeText(word).catch(() => {});
                      }}
                      className="px-2.5 py-1 bg-white text-amber-700 text-xs rounded-full border border-amber-200 cursor-pointer hover:bg-amber-100 transition-colors"
                      title="点击复制"
                    >
                      {word}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* ===== 张力自检评分 ===== */}
        {activeTab === 'tension-check' && (
          <div className="space-y-4">
            <p className="text-xs text-gray-500 mb-3">
              将您的话术粘贴到下方，系统会自动分析张力等级并提供改进建议。
            </p>

            {/* 输入区 */}
            <div>
              <textarea
                value={analysisText}
                onChange={(e) => setAnalysisText(e.target.value)}
                rows={4}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm resize-y focus:ring-2 focus:ring-purple-500 focus:border-purple-500"
                placeholder="粘贴您的话术文本，点击'分析张力'获取评分..."
              />
              <button
                onClick={handleAnalyze}
                disabled={loading || !analysisText.trim()}
                className={`
                  mt-2 px-4 py-2 text-sm font-medium rounded-lg transition-colors
                  ${loading || !analysisText.trim()
                    ? 'bg-gray-200 text-gray-400 cursor-not-allowed'
                    : 'bg-purple-600 text-white hover:bg-purple-700'
                  }
                `}
              >
                {loading ? '分析中...' : '分析张力'}
              </button>
            </div>

            {/* 分析结果 */}
            {analysis && (
              <div className={`p-4 rounded-lg border ${levelColors[analysis.level] || 'bg-gray-50 border-gray-200'}`}>
                {/* 分数 + 等级 */}
                <div className="flex items-center gap-4 mb-3">
                  <div className="text-center">
                    <div className="text-3xl font-bold">{analysis.score}</div>
                    <div className="text-xs mt-0.5">/ 100</div>
                  </div>
                  <div>
                    <div className="text-sm font-semibold">{analysis.label}</div>
                    <div className="text-xs opacity-75">{analysis.description}</div>
                  </div>
                </div>

                {/* 症状 */}
                {analysis.symptoms.length > 0 && (
                  <div className="mb-2">
                    <div className="text-xs font-medium mb-1">发现的问题：</div>
                    <ul className="text-xs space-y-0.5 list-disc list-inside opacity-80">
                      {analysis.symptoms.map((s, i) => <li key={i}>{s}</li>)}
                    </ul>
                  </div>
                )}

                {/* 改进建议 */}
                {analysis.fixes.length > 0 && (
                  <div>
                    <div className="text-xs font-medium mb-1">改进建议：</div>
                    <ul className="text-xs space-y-0.5 list-disc list-inside opacity-80">
                      {analysis.fixes.map((f, i) => <li key={i}>{f}</li>)}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
