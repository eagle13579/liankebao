"use client";

import type { Employee } from "@/lib/data";

interface EmployeeAvatarProps {
  employee: Employee;
  size?: "sm" | "md" | "lg";
  showStatus?: boolean;
  showName?: boolean;
  onClick?: () => void;
}

export default function EmployeeAvatar({
  employee,
  size = "md",
  showStatus = true,
  showName = false,
  onClick,
}: EmployeeAvatarProps) {
  const sizeClasses = {
    sm: "w-8 h-8 text-sm",
    md: "w-12 h-12 text-lg",
    lg: "w-16 h-16 text-2xl",
  };

  return (
    <button
      onClick={onClick}
      className={`relative flex-shrink-0 ${sizeClasses[size]} rounded-xl flex items-center justify-center transition-all ${
        onClick ? "cursor-pointer hover:ring-2 hover:ring-blue-400/50" : "cursor-default"
      } ${
        employee.status === "working"
          ? "bg-gradient-to-br from-blue-500/20 to-purple-500/20 ring-2 ring-blue-400/40"
          : "bg-slate-700/50"
      }`}
      title={`${employee.name} - ${employee.title}`}
    >
      <span>{employee.avatar}</span>

      {showStatus && (
        <span
          className={`absolute -bottom-0.5 -right-0.5 w-3.5 h-3.5 rounded-full border-2 border-slate-900 ${
            employee.status === "working"
              ? "bg-green-500 animate-pulse"
              : employee.status === "idle"
              ? "bg-slate-400"
              : "bg-yellow-400"
          }`}
        />
      )}

      {showName && (
        <div className="absolute -bottom-5 left-1/2 -translate-x-1/2 text-[10px] text-slate-400 whitespace-nowrap">
          {employee.name}
        </div>
      )}
    </button>
  );
}
