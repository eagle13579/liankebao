import { useState, useRef, useCallback, useEffect } from 'react';
import { useI18n } from '../i18n/I18nContext';
import type { Lang } from '../i18n/translations';

export default function FloatingLangSwitcher() {
  const { lang, setLang } = useI18n();
  const [position, setPosition] = useState({ x: window.innerWidth - 80, y: 120 });
  const [dragging, setDragging] = useState(false);
  const dragRef = useRef<{ startX: number; startY: number; elX: number; elY: number } | null>(null);

  const onMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    setDragging(true);
    dragRef.current = {
      startX: e.clientX,
      startY: e.clientY,
      elX: position.x,
      elY: position.y,
    };
  }, [position]);

  const onTouchStart = useCallback((e: React.TouchEvent) => {
    const touch = e.touches[0];
    setDragging(true);
    dragRef.current = {
      startX: touch.clientX,
      startY: touch.clientY,
      elX: position.x,
      elY: position.y,
    };
  }, [position]);

  useEffect(() => {
    if (!dragging) return;

    const onMove = (e: MouseEvent | TouchEvent) => {
      if (!dragRef.current) return;
      const clientX = 'touches' in e ? e.touches[0].clientX : e.clientX;
      const clientY = 'touches' in e ? e.touches[0].clientY : e.clientY;

      setPosition({
        x: Math.max(0, Math.min(window.innerWidth - 60, dragRef.current.elX + (clientX - dragRef.current.startX))),
        y: Math.max(0, Math.min(window.innerHeight - 60, dragRef.current.elY + (clientY - dragRef.current.startY))),
      });
    };

    const onUp = () => setDragging(false);

    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    window.addEventListener('touchmove', onMove, { passive: true });
    window.addEventListener('touchend', onUp);

    return () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
      window.removeEventListener('touchmove', onMove);
      window.removeEventListener('touchend', onUp);
    };
  }, [dragging]);

  const toggleLang = useCallback(() => {
    const next: Lang = lang === 'zh' ? 'en' : 'zh';
    setLang(next);
  }, [lang, setLang]);

  return (
    <div
      onMouseDown={onMouseDown}
      onTouchStart={onTouchStart}
      onClick={toggleLang}
      style={{
        position: 'fixed',
        left: position.x,
        top: position.y,
        zIndex: 9999,
        cursor: dragging ? 'grabbing' : 'grab',
        userSelect: 'none',
        touchAction: 'none',
        transition: dragging ? 'none' : 'box-shadow 0.2s',
      }}
      className={`
        flex items-center justify-center
        w-12 h-12 rounded-full
        text-sm font-bold tracking-wider
        shadow-lg hover:shadow-xl
        bg-white/90 backdrop-blur-sm
        border border-gray-200
        text-gray-700
        ${dragging ? 'scale-110 shadow-2xl' : 'hover:scale-105'}
        transition-transform duration-150
      `}
      title={lang === 'zh' ? '切换英文' : 'Switch to Chinese'}
    >
      {lang === 'zh' ? 'EN' : '中'}
    </div>
  );
}
