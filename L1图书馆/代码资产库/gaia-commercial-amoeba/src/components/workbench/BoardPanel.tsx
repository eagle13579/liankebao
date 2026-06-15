"use client";

import { useState, useEffect } from "react";
import type { Department } from "@/lib/data";
import { departments as deptData } from "@/lib/data";

interface Topic {
  title: string;
  content: string;
  departmentId: string;
  tags: string[];
}

interface BoardPanelProps {
  selectedDept: string | null;
}

export default function BoardPanel({ selectedDept }: BoardPanelProps) {
  const [topics, setTopics] = useState<Topic[]>([]);
  const [loading, setLoading] = useState(false);
  const [aiMode, setAiMode] = useState(false);

  const loadTopics = async (force = false) => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (selectedDept) params.set("department", selectedDept);
      if (force) params.set("force", "true");

      const res = await fetch(`/api/board?${params}`);
      const data = await res.json();
      setTopics(data.topics ?? []);
      if (force) setAiMode(true);
    } catch {
      setTopics([]);
    }
    setLoading(false);
  };

  useEffect(() => {
    loadTopics();
  }, [selectedDept]);

  const filteredTopics = selectedDept
    ? topics.filter((t) => t.departmentId === selectedDept)
    : topics;

  return (
    <aside className="w-80 bg-slate-800/40 flex-shrink-0 border-l border-slate-700/30 overflow-y-auto hidden lg:block">
      <div className="px-5 py-4 border-b border-slate-700/30">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-slate-300 flex items-center gap-2">
            <span>📋</span> 公告板
          </h3>
          <button
            onClick={() => loadTopics(true)}
            disabled={loading}
            className="text-[10px] px-2 py-1 bg-slate-700 hover:bg-slate-600 text-slate-300 rounded-lg transition disabled:opacity-50"
            title="AI生成新话题"
          >
            {loading ? "⏳" : "🔄 AI刷新"}
          </button>
        </div>
        <p className="text-[10px] text-slate-500 mt-1">
          {selectedDept
            ? `${deptData.find((d) => d.id === selectedDept)?.name} 热点话题`
            : "全部热点话题"}
          {aiMode && <span className="text-green-400 ml-1">· AI生成</span>}
        </p>
      </div>

      <div className="px-4 py-3 space-y-3">
        {loading ? (
          <div className="text-center text-slate-500 text-sm py-8">
            <div className="animate-spin w-5 h-5 border-2 border-blue-400 border-t-transparent rounded-full mx-auto mb-2" />
            <span>AI生成中...</span>
          </div>
        ) : filteredTopics.length === 0 ? (
          <div className="text-center text-slate-500 text-sm py-8">
            <p>暂无话题</p>
            <button
              onClick={() => loadTopics(true)}
              className="text-blue-400 hover:text-blue-300 text-xs mt-2"
            >
              AI生成新话题 →
            </button>
          </div>
        ) : (
          filteredTopics.map((topic, i) => {
            const dept = deptData.find((d) => d.id === topic.departmentId);
            return (
              <div
                key={i}
                className="bg-slate-800/60 rounded-xl p-4 border border-slate-700/30 hover:border-slate-600/50 transition cursor-pointer"
              >
                <div className="flex flex-wrap gap-1.5 mb-2">
                  <span className="text-[10px] px-2 py-0.5 rounded-full bg-slate-700 text-slate-400">
                    {dept?.icon} {dept?.name ?? topic.departmentId}
                  </span>
                  {topic.tags?.slice(0, 2).map((tag) => (
                    <span
                      key={tag}
                      className="text-[10px] px-2 py-0.5 rounded-full bg-blue-900/30 text-blue-400"
                    >
                      {tag}
                    </span>
                  ))}
                </div>

                <h4 className="text-sm font-medium text-slate-200 leading-snug mb-2">
                  {topic.title}
                </h4>

                <p className="text-xs text-slate-400 leading-relaxed line-clamp-3">
                  {topic.content}
                </p>
              </div>
            );
          })
        )}
      </div>

      <div className="px-5 py-4 border-t border-slate-700/30 mt-4">
        <h3 className="text-xs font-semibold text-slate-400 flex items-center gap-2 mb-3">
          <span>📜</span> 政策简述
        </h3>
        <div className="space-y-2">
          <div className="text-xs text-slate-400 bg-slate-800/40 rounded-lg p-3">
            <p className="text-slate-300 font-medium mb-1">新规速递</p>
            <p className="text-slate-500 leading-relaxed">
              7月1日起实施《网络数据安全管理条例》，数据处理者需在30日内完成合规自查。
            </p>
          </div>
          <div className="text-xs text-slate-400 bg-slate-800/40 rounded-lg p-3">
            <p className="text-slate-300 font-medium mb-1">行业动态</p>
            <p className="text-slate-500 leading-relaxed">
              工信部发布《AI大模型备案指引》，提供公众服务的模型需通过安全评估。
            </p>
          </div>
        </div>
      </div>
    </aside>
  );
}
