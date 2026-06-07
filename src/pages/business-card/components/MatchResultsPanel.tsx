import { Users, Loader2 } from 'lucide-react';
import type { MatchItem } from '../types';
interface Props { items: MatchItem[]; loading: boolean; }
export default function MatchResultsPanel({ items, loading }: Props) {
  if(loading) return <div className="flex justify-center p-8"><Loader2 className="w-8 h-8 animate-spin text-blue-500" /></div>;
  if(items.length===0) return null;
  return (
    <div className="mx-4 mb-4">
      <h3 className="text-lg font-semibold text-gray-800 mb-3 flex items-center gap-2"><Users className="w-5 h-5" />匹配推荐 ({items.length})</h3>
      <div className="space-y-3">{items.map(item=>(
        <div key={item.id} className="p-4 bg-white border border-gray-200 rounded-xl hover:shadow-md transition-shadow">
          <div className="flex justify-between items-start">
            <div><h4 className="font-medium text-gray-800">{item.name}</h4><p className="text-sm text-gray-500">{item.position} @ {item.company}</p></div>
            <div className="text-sm font-medium text-blue-600">{Math.round(item.match_score*100)}% 匹配</div>
          </div>
          {item.tags.length>0 && <div className="flex flex-wrap gap-1 mt-2">{item.tags.map((t,i)=><span key={i} className="px-2 py-0.5 bg-blue-50 text-blue-600 text-xs rounded-full">{t}</span>)}</div>}
          {item.common_contacts>0 && <p className="text-xs text-green-600 mt-1">{item.common_contacts} 个共同联系人</p>}
        </div>
      ))}</div>
    </div>
  );
}
