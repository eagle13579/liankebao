import type { AlbumPage } from '../types';
interface Props { page: AlbumPage; }
export default function AlbumPageContent({ page }: Props) {
  const c = page.content;
  switch(page.type) {
    case 'cover': return (
      <div className="flex flex-col items-center justify-center h-full p-8 text-center">
        <div className="w-24 h-24 rounded-full bg-gradient-to-br from-blue-400 to-purple-500 flex items-center justify-center text-white text-3xl font-bold mb-4">
          {(c.name||'?')[0]}
        </div>
        <h2 className="text-2xl font-bold text-gray-800 mb-1">{c.name||'姓名'}</h2>
        <p className="text-gray-500 mb-2">{c.position||'职位'} {c.company ? ' @ '+c.company : ''}</p>
      </div>
    );
    case 'contact': return (
      <div className="p-6 space-y-4">
        <h3 className="text-lg font-semibold text-gray-800 mb-4">联系方式</h3>
        {c.phone && <div className="flex items-center gap-3"><span className="text-gray-600">电话:</span><span>{c.phone}</span></div>}
        {c.email && <div className="flex items-center gap-3"><span className="text-gray-600">邮箱:</span><span>{c.email}</span></div>}
        {c.wechat && <div className="flex items-center gap-3"><span className="text-gray-600">微信:</span><span>{c.wechat}</span></div>}
        {c.address && <div className="flex items-center gap-3"><span className="text-gray-600">地址:</span><span>{c.address}</span></div>}
      </div>
    );
    case 'company': return (
      <div className="p-6 space-y-4">
        <h3 className="text-lg font-semibold text-gray-800 mb-4">企业信息</h3>
        {c.company && <div className="flex items-center gap-3"><span className="text-gray-600">公司:</span><span className="font-medium">{c.company}</span></div>}
        {c.website && <div className="flex items-center gap-3"><span className="text-gray-600">官网:</span><a href={c.website} target="_blank" className="text-blue-600 underline">{c.website}</a></div>}
      </div>
    );
    case 'qrcode': return (
      <div className="flex flex-col items-center justify-center h-full p-8">
        <h3 className="text-lg font-semibold text-gray-800 mb-4">扫码查看名片</h3>
        <div className="w-48 h-48 bg-gray-200 rounded-lg flex items-center justify-center text-gray-400">二维码区域</div>
      </div>
    );
    default: return null;
  }
}
