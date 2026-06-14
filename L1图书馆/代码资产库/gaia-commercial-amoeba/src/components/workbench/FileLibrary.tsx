"use client";

import { useState, useEffect } from "react";
import type { Department } from "@/lib/data";

interface FileItem {
  id: string;
  name: string;
  type: "report" | "document" | "image";
  departmentId: string;
  departmentName: string;
  createdAt: string;
  downloaded: boolean;
  tags: string[];
}

interface FileLibraryProps {
  departments: Department[];
  selectedDept: string | null;
  isOpen: boolean;
  onClose: () => void;
}

export default function FileLibrary({
  departments,
  selectedDept,
  isOpen,
  onClose,
}: FileLibraryProps) {
  const [files, setFiles] = useState<FileItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [filterDept, setFilterDept] = useState<string | null>(selectedDept);

  useEffect(() => {
    if (!isOpen) return;

    const load = async () => {
      setLoading(true);
      try {
        const params = filterDept ? `?department=${filterDept}` : "";
        const res = await fetch(`/api/files${params}`);
        const data = await res.json();
        setFiles(data.files ?? []);
      } catch {
        setFiles([]);
      }
      setLoading(false);
    };
    load();
  }, [isOpen, filterDept]);

  if (!isOpen) return null;

  const filteredCount = filterDept
    ? files.length
    : departments.reduce((acc, d) => acc + files.filter((f) => f.departmentId === d.id).length, 0);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="bg-slate-800 rounded-2xl border border-slate-700/50 w-[680px] max-w-[90vw] max-h-[80vh] shadow-2xl overflow-hidden flex flex-col">
        <div className="px-6 py-4 border-b border-slate-700/30 flex items-center justify-between flex-shrink-0">
          <div className="flex items-center gap-3">
            <span className="text-xl">📁</span>
            <div>
              <h3 className="font-semibold text-slate-200 text-sm">文件库</h3>
              <p className="text-[10px] text-slate-500">{filteredCount} 个文件</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 flex items-center justify-center rounded-lg hover:bg-slate-700 text-slate-400 hover:text-slate-200 transition"
          >
            ✕
          </button>
        </div>

        <div className="px-6 py-3 border-b border-slate-700/20 flex gap-2 overflow-x-auto flex-shrink-0">
          <button
            onClick={() => setFilterDept(null)}
            className={`px-3 py-1.5 rounded-lg text-xs whitespace-nowrap transition ${
              !filterDept
                ? "bg-blue-600/30 text-blue-300 border border-blue-500/30"
                : "bg-slate-700/50 text-slate-400 hover:text-slate-200"
            }`}
          >
            全部
          </button>
          {departments.map((d) => (
            <button
              key={d.id}
              onClick={() => setFilterDept(d.id)}
              className={`px-3 py-1.5 rounded-lg text-xs whitespace-nowrap transition flex items-center gap-1 ${
                filterDept === d.id
                  ? "bg-blue-600/30 text-blue-300 border border-blue-500/30"
                  : "bg-slate-700/50 text-slate-400 hover:text-slate-200"
              }`}
            >
              <span>{d.icon}</span>
              <span>{d.name}</span>
              <span className="text-[10px] text-slate-500">
                ({files.filter((f) => f.departmentId === d.id).length})
              </span>
            </button>
          ))}
        </div>

        <div className="flex-1 overflow-y-auto p-4">
          {loading ? (
            <div className="text-center text-slate-500 py-12">
              <div className="animate-spin w-6 h-6 border-2 border-blue-400 border-t-transparent rounded-full mx-auto mb-2" />
              <span className="text-sm">加载中...</span>
            </div>
          ) : files.length === 0 ? (
            <div className="text-center text-slate-500 py-12">
              <div className="text-3xl mb-3">📂</div>
              <p className="text-sm">暂无文件</p>
              <p className="text-xs text-slate-600 mt-1">购买报告后自动保存到文件库</p>
            </div>
          ) : (
            <div className="space-y-2">
              {files.map((file) => (
                <div
                  key={file.id}
                  className="flex items-center gap-4 bg-slate-700/30 rounded-xl px-4 py-3 border border-slate-700/20 hover:border-slate-600/40 transition"
                >
                  <span className="text-xl">
                    {file.type === "report" ? "📄" : file.type === "document" ? "📝" : "🖼️"}
                  </span>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-slate-200 truncate">{file.name}</p>
                    <p className="text-[10px] text-slate-500 mt-0.5">
                      {file.departmentName} · {new Date(file.createdAt).toLocaleDateString("zh-CN")}
                    </p>
                  </div>
                  <div className="flex gap-1">
                    {file.tags.slice(0, 2).map((tag) => (
                      <span
                        key={tag}
                        className="text-[10px] px-2 py-0.5 rounded-full bg-slate-700 text-slate-400"
                      >
                        {tag}
                      </span>
                    ))}
                  </div>
                  <button
                    className="px-3 py-1.5 text-xs bg-slate-700 hover:bg-slate-600 text-slate-300 rounded-lg transition"
                    title="下载"
                  >
                    ⬇️
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
