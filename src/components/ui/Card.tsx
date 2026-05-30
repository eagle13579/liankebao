import React from 'react';

interface CardProps {
  title?: React.ReactNode;
  subtitle?: React.ReactNode;
  children?: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
  padding?: boolean;
}

export function Card({
  title,
  subtitle,
  children,
  actions,
  className = '',
  padding = true,
}: CardProps) {
  return (
    <div
      className={`bg-surface rounded-2xl border border-border-light shadow-sm ${className}`}
    >
      {/* Header */}
      {(title || subtitle) && (
        <div className={`flex items-start justify-between ${padding ? 'px-5 pt-5 pb-3' : 'p-0 mb-3'}`}>
          <div className="min-w-0">
            {title && (
              <h3 className="text-base font-bold text-on-surface truncate">
                {title}
              </h3>
            )}
            {subtitle && (
              <p className="text-xs text-text-muted mt-0.5">{subtitle}</p>
            )}
          </div>
          {actions && (
            <div className="flex items-center gap-2 ml-4 shrink-0">{actions}</div>
          )}
        </div>
      )}

      {/* Content */}
      {children && (
        <div className={padding ? 'px-5 pb-5' : ''}>
          {actions && !title && !subtitle && (
            <div className="flex items-center justify-end gap-2 mb-3">{actions}</div>
          )}
          {children}
        </div>
      )}

      {/* Actions below (no title) */}
      {!title && !subtitle && actions && !children && (
        <div className={`flex items-center gap-2 ${padding ? 'px-5 py-4' : ''}`}>
          {actions}
        </div>
      )}
    </div>
  );
}
