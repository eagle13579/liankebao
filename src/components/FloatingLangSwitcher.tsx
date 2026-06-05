import { useState, useRef, useCallback, useEffect } from 'react';
import { useLocale } from '../i18n';

export default function FloatingLangSwitcher() {
  const { locale, setLocale } = useLocale();
  const [pos, setPos] = useState({ x: window.innerWidth - 80, y: 120 });
  const [dragging, setDragging] = useState(false);
  const dragRef = useRef<{ sx: number; sy: number; ex: number; ey: number } | null>(null);

  const onDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    setDragging(true);
    dragRef.current = { sx: e.clientX, sy: e.clientY, ex: pos.x, ey: pos.y };
  }, [pos]);

  useEffect(() => {
    if (!dragging) return;
    const onMove = (e: MouseEvent) => {
      if (!dragRef.current) return;
      setPos({
        x: Math.max(0, Math.min(window.innerWidth - 60, dragRef.current.ex + (e.clientX - dragRef.current.sx))),
        y: Math.max(0, Math.min(window.innerHeight - 60, dragRef.current.ey + (e.clientY - dragRef.current.sy))),
      });
    };
    const onUp = () => setDragging(false);
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    return () => { window.removeEventListener('mousemove', onMove); window.removeEventListener('mouseup', onUp); };
  }, [dragging]);

  return (
    <div
      onMouseDown={onDown}
      onClick={() => setLocale(locale === 'zh' ? 'en' : 'zh')}
      style={{
        position: 'fixed', left: pos.x, top: pos.y, zIndex: 9999,
        cursor: dragging ? 'grabbing' : 'grab', userSelect: 'none',
      }}
      className="flex items-center justify-center w-12 h-12 rounded-full text-sm font-bold tracking-wider shadow-lg hover:shadow-xl bg-white/90 backdrop-blur-sm border border-gray-200 text-gray-700 transition-all duration-150 hover:scale-105 active:scale-110"
      title={locale === 'zh' ? 'Switch to English' : '切换到中文'}
    >
      {locale === 'zh' ? 'EN' : '中'}
    </div>
  );
}
