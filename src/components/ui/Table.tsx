import React, { useState, useMemo } from 'react';
import { ChevronUp, ChevronDown, Loader2 } from 'lucide-react';

export interface Column<T> {
  key: string;
  title: string;
  dataIndex?: string;
  render?: (value: any, record: T, index: number) => React.ReactNode;
  sortable?: boolean;
  width?: string;
  align?: 'left' | 'center' | 'right';
}

interface TableProps<T> {
  columns: Column<T>[];
  data: T[];
  rowKey?: string | ((record: T) => string);
  loading?: boolean;
  emptyText?: string;
  className?: string;
  defaultSortKey?: string;
  defaultSortDir?: 'asc' | 'desc';
  onRowClick?: (record: T, index: number) => void;
}

export function Table<T extends Record<string, any>>({
  columns,
  data,
  rowKey = 'id',
  loading = false,
  emptyText = '暂无数据',
  className = '',
  defaultSortKey,
  defaultSortDir = 'asc',
  onRowClick,
}: TableProps<T>) {
  const [sortKey, setSortKey] = useState<string | undefined>(defaultSortKey);
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>(defaultSortDir);

  const getRowKey = (record: T, index: number): string => {
    if (typeof rowKey === 'function') return rowKey(record);
    return String(record[rowKey] ?? index);
  };

  const handleSort = (key: string) => {
    if (sortKey === key) {
      setSortDir((prev) => (prev === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortDir('asc');
    }
  };

  const sortedData = useMemo(() => {
    if (!sortKey) return data;
    return [...data].sort((a, b) => {
      const aVal = a[sortKey];
      const bVal = b[sortKey];
      if (aVal == null) return 1;
      if (bVal == null) return -1;
      let cmp = 0;
      if (typeof aVal === 'number' && typeof bVal === 'number') {
        cmp = aVal - bVal;
      } else {
        cmp = String(aVal).localeCompare(String(bVal));
      }
      return sortDir === 'asc' ? cmp : -cmp;
    });
  }, [data, sortKey, sortDir]);

  return (
    <div className={`overflow-x-auto rounded-xl border border-border-light ${className}`}>
      <table className="w-full text-sm">
        {/* Header */}
        <thead>
          <tr className="bg-slate-50 border-b border-border-light">
            {columns.map((col) => (
              <th
                key={col.key}
                className={`px-4 py-3 text-xs font-bold text-text-muted uppercase tracking-wider ${
                  col.sortable ? 'cursor-pointer select-none hover:bg-slate-100' : ''
                } ${col.align === 'center' ? 'text-center' : col.align === 'right' ? 'text-right' : 'text-left'}`}
                style={col.width ? { width: col.width } : undefined}
                onClick={() => col.sortable && handleSort(col.key)}
              >
                <div className="inline-flex items-center gap-1">
                  {col.title}
                  {col.sortable && (
                    <span className="inline-flex flex-col -space-y-1 opacity-40">
                      <ChevronUp
                        className={`w-3 h-3 ${
                          sortKey === col.key && sortDir === 'asc' ? 'text-primary opacity-100' : ''
                        }`}
                      />
                      <ChevronDown
                        className={`w-3 h-3 ${
                          sortKey === col.key && sortDir === 'desc' ? 'text-primary opacity-100' : ''
                        }`}
                      />
                    </span>
                  )}
                </div>
              </th>
            ))}
          </tr>
        </thead>

        {/* Body */}
        <tbody>
          {loading ? (
            <tr>
              <td
                colSpan={columns.length}
                className="px-4 py-12 text-center text-text-muted"
              >
                <div className="flex items-center justify-center gap-2">
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span className="text-sm">加载中...</span>
                </div>
              </td>
            </tr>
          ) : sortedData.length === 0 ? (
            <tr>
              <td
                colSpan={columns.length}
                className="px-4 py-12 text-center text-text-muted text-sm"
              >
                {emptyText}
              </td>
            </tr>
          ) : (
            sortedData.map((record, index) => (
              <tr
                key={getRowKey(record, index)}
                className={`border-b border-border-light last:border-b-0 transition-colors ${
                  onRowClick ? 'cursor-pointer hover:bg-slate-50' : 'hover:bg-slate-50/50'
                }`}
                onClick={() => onRowClick?.(record, index)}
              >
                {columns.map((col) => {
                  const value = col.dataIndex ? record[col.dataIndex] : record[col.key];
                  return (
                    <td
                      key={col.key}
                      className={`px-4 py-3 text-sm text-on-surface ${
                        col.align === 'center'
                          ? 'text-center'
                          : col.align === 'right'
                          ? 'text-right'
                          : 'text-left'
                      }`}
                    >
                      {col.render ? col.render(value, record, index) : (value ?? '-')}
                    </td>
                  );
                })}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
