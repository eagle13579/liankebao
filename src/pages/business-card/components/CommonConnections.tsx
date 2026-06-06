import { Users } from 'lucide-react';
interface Props { count: number; names: string[]; onViewNetwork?: ()=>void; }
export default function CommonConnections({ count, names, onViewNetwork }: Props) {
  if(count===0) return null;
  return (
    <div className="mx-4 mb-4 p-3 bg-green-50 border border-green-200 rounded-xl">
      <div className="flex items-center gap-2 text-green-700 text-sm">
        <Users className="w-4 h-4" />
        <span>你们有 <strong>{count}</strong> 个共同联系人</span>
        {names.length>0 && <span className="text-green-500">（{names.slice(0,3).join("、")}{names.length>3?"等":""}）</span>}
        {onViewNetwork && <button onClick={onViewNetwork} className="ml-auto text-blue-600 underline text-xs">查看</button>}
      </div>
    </div>
  );
}
