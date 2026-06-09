import { User, QrCode } from 'lucide-react';
import type { AlbumPage } from '../types';

interface AlbumPageContentProps {
  page: AlbumPage;
}

export default function AlbumPageContent({ page }: AlbumPageContentProps) {
  switch (page.type) {
    case 'cover':
      return (
        <div className="flex flex-col items-center justify-center h-full text-center">
          <div className="w-20 h-20 rounded-full bg-white/20 flex items-center justify-center mb-4">
            <User className="w-10 h-10 text-white" />
          </div>
          <h3 className="text-2xl font-bold mb-1">{page.title}</h3>
          {page.subtitle && <p className="text-sm opacity-80">{page.subtitle}</p>}
          <div className="mt-6 px-4 py-1.5 rounded-full text-xs font-medium"
            style={{ background: page.style.accentColor, color: '#ffffff' }}>
            Powered by 链客宝 AI
          </div>
        </div>
      );

    case 'contact':
      return (
        <div className="flex flex-col h-full">
          <h3 className="text-base font-bold mb-4" style={{ color: page.style.accentColor }}>{page.title}</h3>
          <div className="flex-1 space-y-3">
            {(page.fields || []).map((f, i) => (
              <div key={i} className="flex items-start gap-2">
                <span className="text-xs opacity-60 w-10 shrink-0">{f.label.split(' ')[0]}</span>
                <span className="text-sm font-medium">{f.value}</span>
              </div>
            ))}
            {(!page.fields || page.fields.length === 0) && <p className="text-sm opacity-60">暂无联系方式</p>}
          </div>
        </div>
      );

    case 'company':
      return (
        <div className="flex flex-col h-full">
          <h3 className="text-base font-bold mb-4" style={{ color: page.style.accentColor }}>{page.title}</h3>
          <div className="flex-1 space-y-3">
            {page.content?.company && <div><p className="text-xs opacity-60 mb-0.5">公司</p><p className="text-sm font-medium">{page.content.company}</p></div>}
            {page.content?.position && <div><p className="text-xs opacity-60 mb-0.5">职位</p><p className="text-sm font-medium">{page.content.position}</p></div>}
            {page.content?.address && <div><p className="text-xs opacity-60 mb-0.5">地址</p><p className="text-sm">{page.content.address}</p></div>}
            {page.content?.website && <div><p className="text-xs opacity-60 mb-0.5">官网</p><p className="text-sm text-blue-600 truncate">{page.content.website}</p></div>}
          </div>
        </div>
      );

    case 'qrcode':
      return (
        <div className="flex flex-col items-center justify-center h-full text-center">
          <div className="w-40 h-40 rounded-2xl flex items-center justify-center mb-4"
            style={{ background: page.style.accentColor + '15' }}>
            <QrCode className="w-24 h-24" style={{ color: page.style.accentColor }} />
          </div>
          <h3 className="text-base font-bold">{page.title}</h3>
          {page.subtitle && <p className="text-xs opacity-60 mt-1">{page.subtitle}</p>}
        </div>
      );

    default:
      return <div className="flex items-center justify-center h-full"><p className="text-sm opacity-60">{page.title}</p></div>;
  }
}
