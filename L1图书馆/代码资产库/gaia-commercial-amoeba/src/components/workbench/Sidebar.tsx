"use client";

import { useState } from "react";
import type { Department, Employee } from "@/lib/data";

interface SidebarProps {
  departments: Department[];
  employees: Employee[];
  selectedDept: string | null;
  onSelectDept: (id: string) => void;
  onSelectEmployee: (id: string) => void;
  onOpenFileLibrary?: () => void;
  fileCount: number;
}

export default function Sidebar({
  departments,
  employees,
  selectedDept,
  onSelectDept,
  onSelectEmployee,
  onOpenFileLibrary,
  fileCount,
}: SidebarProps) {
  const [collapsed, setCollapsed] = useState(false);
  const [expandedDepts, setExpandedDepts] = useState<string[]>([]);
  const [showDeptList, setShowDeptList] = useState(true);

  const toggleExpand = (deptId: string) => {
    onSelectDept(deptId);
    setExpandedDepts((prev) =>
      prev.includes(deptId)
        ? prev.filter((id) => id !== deptId)
        : [...prev, deptId]
    );
  };

  return (
    <aside
      className={`bg-slate-900 text-slate-300 flex flex-col transition-all duration-300 ${
        collapsed ? "w-16" : "w-64"
      } flex-shrink-0 border-r border-slate-700/50`}
    >
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="p-3 text-slate-400 hover:text-white hover:bg-slate-800 transition text-sm text-left"
      >
        {collapsed ? "▶ 展开" : "◀ 收起"}
      </button>

      {!collapsed && (
        <>
          <div className="flex-1 overflow-y-auto">
            <div
              className="px-4 py-2 text-xs font-semibold text-slate-500 uppercase tracking-wider cursor-pointer hover:text-slate-300 flex items-center justify-between"
              onClick={() => setShowDeptList(!showDeptList)}
            >
              <span>🏢 部门蜂巢</span>
              <span className="text-slate-600">{showDeptList ? "▾" : "▸"}</span>
            </div>

            {showDeptList && (
              <div className="space-y-0.5 px-2 mb-4">
                {departments.map((dept) => {
                  const isExpanded = expandedDepts.includes(dept.id);
                  const deptEmployees = employees.filter((e) => e.department === dept.id);

                  return (
                    <div key={dept.id}>
                      <button
                        onClick={() => toggleExpand(dept.id)}
                        className={`w-full text-left px-3 py-2 rounded-lg text-sm flex items-center gap-2 transition ${
                          selectedDept === dept.id
                            ? "bg-blue-600/20 text-blue-300 border border-blue-500/30"
                            : "hover:bg-slate-800 text-slate-400 hover:text-slate-200"
                        }`}
                      >
                        <span className="text-xs text-slate-500 w-4 flex-shrink-0">
                          {isExpanded ? "▾" : "▸"}
                        </span>
                        <span>{dept.icon}</span>
                        <span className="flex-1">{dept.name}</span>
                        <span
                          className={`text-[10px] px-1.5 py-0.5 rounded-full ${
                            dept.tier === "free"
                              ? "bg-green-900/50 text-green-400"
                              : dept.tier === "standard"
                              ? "bg-blue-900/50 text-blue-400"
                              : "bg-purple-900/50 text-purple-400"
                          }`}
                        >
                          {dept.tier === "free" ? "免费" : dept.tier === "standard" ? "标准" : "专业"}
                        </span>
                      </button>

                      {isExpanded && (
                        <div className="ml-6 mt-0.5 space-y-0.5 border-l-2 border-slate-700/50 pl-2">
                          {deptEmployees.length === 0 && (
                            <div className="px-3 py-2 text-xs text-slate-500">暂无成员</div>
                          )}
                          {deptEmployees.map((emp) => (
                            <button
                              key={emp.id}
                              onClick={(e) => {
                                e.stopPropagation();
                                onSelectEmployee(emp.id);
                              }}
                              className="w-full text-left px-3 py-1.5 rounded-lg text-sm flex items-center gap-2 hover:bg-slate-800 text-slate-400 hover:text-slate-200 transition group"
                            >
                              <span className="text-base">{emp.avatar}</span>
                              <div className="flex-1 min-w-0">
                                <div className="text-slate-300 truncate text-xs">{emp.name}</div>
                                <div className="text-[10px] text-slate-500 truncate">{emp.title}</div>
                              </div>
                              <span
                                className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${
                                  emp.status === "working"
                                    ? "bg-green-500 animate-pulse"
                                    : emp.status === "idle"
                                    ? "bg-slate-500"
                                    : "bg-yellow-500"
                                }`}
                              />
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}

            <div className="mt-4 px-4 py-2 border-t border-slate-700/50">
              <button
                onClick={onOpenFileLibrary}
                className="w-full text-left px-3 py-2 rounded-lg text-sm flex items-center gap-2 hover:bg-slate-800 text-slate-400 hover:text-slate-200 transition"
              >
                <span>📁</span>
                <span className="flex-1">文件库</span>
                <span className="text-[10px] bg-slate-700 text-slate-400 px-1.5 py-0.5 rounded-full">
                  {fileCount}
                </span>
              </button>
            </div>
          </div>
        </>
      )}
    </aside>
  );
}
