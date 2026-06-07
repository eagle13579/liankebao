/**
 * 链客宝 - 销售话术模板编辑器主页面
 * 注入点：后台管理的话术模板页面（ABACC五步框架+张力武器库）
 * 规则：纯新增，不修改现有业务逻辑
 */

import React, { useState, useEffect } from 'react';
import type { SalesScript, AbaccStep } from './salesScriptTypes';
import { ABACC_STEPS_META } from './salesScriptTypes';
import * as api from './salesScriptApi';
import AbaccEditor from './components/AbaccEditor';
import TensionWeaponLibrary from './components/TensionWeaponLibrary';
import TensionScoreGauge from './components/TensionScoreGauge';

/** 空ABACC步骤模板 */
function createEmptySteps(): AbaccStep[] {
  const ids: AbaccStep['step_id'][] = ['attention', 'before', 'after', 'curiosity', 'call_action'];
  return ids.map((step_id) => ({
    step_id,
    title: ABACC_STEPS_META[step_id].label,
    template: '',
    examples: [],
    tips: [],
  }));
}

export default function SalesScriptPage() {
  const [presets, setPresets] = useState<SalesScript[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [editScript, setEditScript] = useState<SalesScript | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [showWeaponLib, setShowWeaponLib] = useState(false);

  // 加载预设模板
  useEffect(() => {
    setLoading(true);
    api.fetchPresets()
      .then((data) => setPresets(data.presets || []))
      .catch((e) => showMsg('error', '加载失败: ' + e.message))
      .finally(() => setLoading(false));
  }, []);

  const showMsg = (type: 'success' | 'error', text: string) => {
    setMessage({ type, text });
    setTimeout(() => setMessage(null), 3000);
  };

  /** 选择预设模板 */
  const handleSelectPreset = async (id: number) => {
    setLoading(true);
    try {
      const script = await api.fetchPreset(id);
      setSelectedId(id);
      setEditScript(JSON.parse(JSON.stringify(script))); // deep clone
    } catch (e: any) {
      showMsg('error', '加载模板失败: ' + e.message);
    } finally {
      setLoading(false);
    }
  };

  /** 新建模板 */
  const handleNew = () => {
    setSelectedId(null);
    setEditScript({
      name: '',
      scenario: '',
      target_role: '',
      abacc: createEmptySteps(),
      tags: [],
      tension_score: 50,
    });
  };

  /** 保存模板 */
  const handleSave = async () => {
    if (!editScript) return;
    if (!editScript.name.trim()) {
      showMsg('error', '请输入话术模板名称');
      return;
    }
    setSaving(true);
    try {
      if (selectedId) {
        await api.updateScript(selectedId, editScript);
        showMsg('success', '更新成功');
      } else {
        const res = await api.createScript(editScript);
        setSelectedId(res.id);
        showMsg('success', '创建成功');
      }
      // 刷新列表
      const data = await api.fetchPresets();
      setPresets(data.presets || []);
    } catch (e: any) {
      showMsg('error', '保存失败: ' + e.message);
    } finally {
      setSaving(false);
    }
  };

  /** 删除模板 */
  const handleDelete = async () => {
    if (!selectedId) return;
    if (!confirm('确定删除此话术模板？')) return;
    setSaving(true);
    try {
      await api.deleteScript(selectedId);
      setSelectedId(null);
      setEditScript(null);
      showMsg('success', '删除成功');
      const data = await api.fetchPresets();
      setPresets(data.presets || []);
    } catch (e: any) {
      showMsg('error', '删除失败: ' + e.message);
    } finally {
      setSaving(false);
    }
  };

  /** 更新ABACC步骤 */
  const handleAbaccChange = (steps: AbaccStep[]) => {
    if (!editScript) return;
    setEditScript({ ...editScript, abacc: steps });
  };

  /** 更新字段 */
  const updateField = (field: string, value: any) => {
    if (!editScript) return;
    setEditScript({ ...editScript, [field]: value });
  };

  /** 更新标签 */
  const handleTagsChange = (value: string) => {
    if (!editScript) return;
    updateField('tags', value.split(',').map((t) => t.trim()).filter(Boolean));
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* 顶部提示 */}
      {message && (
        <div className={`fixed top-4 right-4 z-50 px-4 py-2 rounded-lg shadow-lg text-sm font-medium ${
          message.type === 'success' ? 'bg-green-600 text-white' : 'bg-red-600 text-white'
        }`}>
          {message.text}
        </div>
      )}

      <div className="max-w-7xl mx-auto px-4 py-6">
        {/* 页面标题 */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-gray-800">ABACC 销售话术模板</h1>
            <p className="text-sm text-gray-500 mt-1">
              基于ABACC五步说服逻辑（Attention-Before-After-Curiosity-CallAction）构建高效话术
            </p>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => setShowWeaponLib(!showWeaponLib)}
              className="px-3 py-2 text-sm font-medium rounded-lg border border-gray-300 text-gray-700 bg-white hover:bg-gray-50 transition-colors"
            >
              {showWeaponLib ? '收起武器库' : '打开张力武器库'}
            </button>
            <button
              onClick={handleNew}
              className="px-3 py-2 text-sm font-medium rounded-lg border border-blue-300 text-blue-700 bg-white hover:bg-blue-50 transition-colors"
            >
              + 新建模板
            </button>
          </div>
        </div>

        <div className="flex gap-6">
          {/* 左侧 - 模板列表 */}
          <div className="w-64 flex-shrink-0">
            <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
              <div className="px-4 py-3 border-b border-gray-100 bg-gray-50">
                <h2 className="text-sm font-semibold text-gray-700">话术模板库</h2>
              </div>
              <div className="divide-y divide-gray-100 max-h-[600px] overflow-y-auto">
                {loading && !presets.length ? (
                  <div className="px-4 py-8 text-center text-gray-400 text-sm">加载中...</div>
                ) : presets.length === 0 ? (
                  <div className="px-4 py-8 text-center text-gray-400 text-sm">暂无模板</div>
                ) : (
                  presets.map((preset) => (
                    <button
                      key={preset.id}
                      onClick={() => preset.id && handleSelectPreset(preset.id)}
                      className={`w-full text-left px-4 py-3 transition-colors hover:bg-gray-50 ${
                        selectedId === preset.id ? 'bg-blue-50 border-l-2 border-blue-500' : ''
                      }`}
                    >
                      <div className="text-sm font-medium text-gray-800">{preset.name}</div>
                      <div className="text-xs text-gray-500 mt-0.5">
                        {preset.scenario} · {preset.target_role}
                      </div>
                      {preset.tension_score !== undefined && (
                        <div className="flex items-center gap-1.5 mt-1.5">
                          <div className="flex-1 h-1.5 bg-gray-200 rounded-full overflow-hidden">
                            <div
                              className="h-full rounded-full"
                              style={{
                                width: `${preset.tension_score}%`,
                                backgroundColor:
                                  preset.tension_score >= 71 ? '#10B981' :
                                  preset.tension_score >= 41 ? '#F59E0B' : '#EF4444',
                              }}
                            />
                          </div>
                          <span className="text-[10px] text-gray-400">{preset.tension_score}</span>
                        </div>
                      )}
                    </button>
                  ))
                )}
              </div>
            </div>
          </div>

          {/* 右侧 - 编辑器 */}
          <div className="flex-1 space-y-6">
            {!editScript ? (
              <div className="bg-white rounded-xl border border-gray-200 p-12 text-center text-gray-400">
                <div className="text-4xl mb-3">📝</div>
                <p>选择一个预设模板开始编辑，或点击"新建模板"</p>
              </div>
            ) : (
              <>
                {/* 基本信息 */}
                <div className="bg-white rounded-xl border border-gray-200 p-5">
                  <h2 className="text-sm font-semibold text-gray-700 mb-3">模板信息</h2>
                  <div className="grid grid-cols-3 gap-4">
                    <div>
                      <label className="block text-xs font-medium text-gray-500 mb-1">模板名称</label>
                      <input
                        type="text"
                        value={editScript.name}
                        onChange={(e) => updateField('name', e.target.value)}
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
                        placeholder="例如：B2B电销-痛点唤醒型"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-500 mb-1">适用场景</label>
                      <input
                        type="text"
                        value={editScript.scenario}
                        onChange={(e) => updateField('scenario', e.target.value)}
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
                        placeholder="例如：电销/陌拜/展会"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-500 mb-1">目标角色</label>
                      <input
                        type="text"
                        value={editScript.target_role}
                        onChange={(e) => updateField('target_role', e.target.value)}
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
                        placeholder="例如：CEO/市场总监"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-500 mb-1">标签（逗号分隔）</label>
                      <input
                        type="text"
                        value={(editScript.tags || []).join(', ')}
                        onChange={(e) => handleTagsChange(e.target.value)}
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
                        placeholder="B2B, 电销, 获客"
                      />
                    </div>
                    <div className="flex items-end gap-4">
                      <div>
                        <label className="block text-xs font-medium text-gray-500 mb-1">张力评分</label>
                        <input
                          type="number"
                          min={0}
                          max={100}
                          value={editScript.tension_score || 50}
                          onChange={(e) => updateField('tension_score', parseInt(e.target.value) || 0)}
                          className="w-20 px-3 py-2 border border-gray-300 rounded-lg text-sm"
                        />
                      </div>
                      {editScript.tension_score !== undefined && (
                        <div className="relative inline-block">
                          <TensionScoreGauge score={editScript.tension_score} size="sm" />
                        </div>
                      )}
                    </div>
                  </div>
                </div>

                {/* ABACC五步编辑器 */}
                <div>
                  <h2 className="text-sm font-semibold text-gray-700 mb-2">ABACC五步话术</h2>
                  <AbaccEditor steps={editScript.abacc} onChange={handleAbaccChange} />
                </div>

                {/* 张力武器库（可折叠） */}
                {showWeaponLib && (
                  <div>
                    <h2 className="text-sm font-semibold text-gray-700 mb-2">张力武器库</h2>
                    <TensionWeaponLibrary />
                  </div>
                )}

                {/* 操作按钮 */}
                <div className="flex gap-3">
                  <button
                    onClick={handleSave}
                    disabled={saving}
                    className={`px-5 py-2.5 text-sm font-medium rounded-lg text-white transition-colors ${
                      saving ? 'bg-blue-400 cursor-not-allowed' : 'bg-blue-600 hover:bg-blue-700'
                    }`}
                  >
                    {saving ? '保存中...' : '保存模板'}
                  </button>
                  {selectedId && (
                    <button
                      onClick={handleDelete}
                      disabled={saving}
                      className="px-5 py-2.5 text-sm font-medium rounded-lg border border-red-300 text-red-600 bg-white hover:bg-red-50 transition-colors"
                    >
                      删除模板
                    </button>
                  )}
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
