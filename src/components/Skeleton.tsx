import React from 'react';

interface SkeletonProps {
  className?: string;
  variant?: 'text' | 'rect' | 'circle' | 'card';
  width?: string | number;
  height?: string | number;
  count?: number;
}

export function Skeleton({ className = '', variant = 'text', width, height, count = 1 }: SkeletonProps) {
  const baseClass = 'animate-pulse bg-slate-200 dark:bg-dark-surface rounded';
  
  const variants: Record<string, string> = {
    text: 'h-4 w-full',
    rect: 'h-24 w-full rounded-xl',
    circle: 'h-10 w-10 rounded-full',
    card: 'h-40 w-full rounded-2xl',
  };

  const style: React.CSSProperties = {};
  if (width) style.width = typeof width === 'number' ? `${width}px` : width;
  if (height) style.height = typeof height === 'number' ? `${height}px` : height;

  const items = Array.from({ length: count }, (_, i) => i);

  return (
    <>
      {items.map((i) => (
        <div
          key={i}
          className={`${baseClass} ${variants[variant] || variants.text} ${className}`}
          style={style}
          role="status"
          aria-label="加载中"
        />
      ))}
    </>
  );
}

export function ProductCardSkeleton() {
  return (
    <div className="bg-white dark:bg-dark-surface rounded-xl border border-slate-100 dark:border-dark-border overflow-hidden shadow-sm">
      <Skeleton variant="rect" className="w-full aspect-square" />
      <div className="p-3 space-y-2">
        <Skeleton variant="text" className="w-3/4" />
        <Skeleton variant="text" className="w-1/2 h-3" />
        <Skeleton variant="text" className="w-1/3 h-4 mt-2" />
        <Skeleton variant="rect" className="w-full h-8 rounded-full" />
      </div>
    </div>
  );
}

export function ProfileSkeleton() {
  return (
    <div className="space-y-4 p-4">
      <div className="flex items-center gap-4">
        <Skeleton variant="circle" className="w-16 h-16" />
        <div className="flex-1 space-y-2">
          <Skeleton variant="text" className="w-1/3 h-5" />
          <Skeleton variant="text" className="w-1/2 h-3" />
        </div>
      </div>
      <Skeleton variant="rect" className="w-full h-24" />
      <Skeleton variant="rect" className="w-full h-20" />
      <Skeleton variant="card" className="w-full" />
    </div>
  );
}
