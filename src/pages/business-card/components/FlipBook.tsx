import { ChevronLeft, ChevronRight } from 'lucide-react';
import AlbumPageContent from './AlbumPageContent';
import type { AlbumPage, AlbumSettings } from '../types';

interface FlipBookProps {
  pages: AlbumPage[];
  currentPage: number;
  totalPages: number;
  settings: AlbumSettings;
  onPageChange: (page: number) => void;
}

export default function FlipBook({
  pages,
  currentPage,
  totalPages,
  settings,
  onPageChange,
}: FlipBookProps) {
  const page = pages[currentPage];
  if (!page) return null;

  return (
    <div className="flex flex-col items-center">
      <div
        className="relative rounded-2xl overflow-hidden transition-all duration-500 select-none"
        style={{
          width: settings.page_width,
          height: settings.page_height,
          borderRadius: settings.corner_radius,
          boxShadow: settings.shadow
            ? '0 20px 60px rgba(0,0,0,0.15), 0 8px 20px rgba(0,0,0,0.1)'
            : 'none',
          perspective: '1500px',
        }}
      >
        <div
          className="w-full h-full p-6 flex flex-col transition-all duration-500"
          style={{
            background: page.style.background,
            color: page.style.textColor,
            transform: `rotateY(${0}deg)`,
            transformStyle: 'preserve-3d',
          }}
        >
          <AlbumPageContent page={page} />
        </div>

        <div
          className="absolute top-0 right-0 w-4 h-full pointer-events-none"
          style={{
            background: 'linear-gradient(to left, rgba(0,0,0,0.08), transparent)',
          }}
        />
        <div
          className="absolute bottom-0 right-0 w-8 h-8 pointer-events-none"
          style={{
            background: `linear-gradient(135deg, transparent 50%, rgba(0,0,0,0.04) 50%)`,
          }}
        />
      </div>

      <div className="flex items-center gap-4 mt-4">
        <button
          onClick={() => onPageChange(currentPage - 1)}
          disabled={currentPage === 0}
          className="p-2 rounded-full hover:bg-slate-100 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
        >
          <ChevronLeft className="w-5 h-5" />
        </button>

        <div className="flex gap-1.5">
          {Array.from({ length: totalPages }).map((_, i) => (
            <button
              key={i}
              onClick={() => onPageChange(i)}
              className={`w-2 h-2 rounded-full transition-all duration-300 ${
                i === currentPage
                  ? 'bg-primary w-6'
                  : 'bg-slate-300 hover:bg-slate-400'
              }`}
            />
          ))}
        </div>

        <button
          onClick={() => onPageChange(currentPage + 1)}
          disabled={currentPage === totalPages - 1}
          className="p-2 rounded-full hover:bg-slate-100 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
        >
          <ChevronRight className="w-5 h-5" />
        </button>
      </div>

      <p className="text-xs text-text-muted mt-2">
        第 {currentPage + 1} 页，共 {totalPages} 页
      </p>
    </div>
  );
}
