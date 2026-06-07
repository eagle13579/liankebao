import { ChevronLeft, ChevronRight } from 'lucide-react';
import AlbumPageContent from './AlbumPageContent';
import type { AlbumPage, CardData } from '../types';
interface Props { pages: AlbumPage[]; currentPage: number; totalPages: number; cardData: CardData; onPageChange: (n:number)=>void; }
export default function FlipBook({ pages, currentPage, totalPages, cardData, onPageChange }: Props) {
  if(!pages.length) return <div className="text-center py-20 text-gray-400">暂无内容</div>;
  return (
    <div className="relative mx-4 mb-4">
      <div className="bg-white rounded-2xl shadow-lg overflow-hidden min-h-[400px] border border-gray-100">
        {currentPage < pages.length ? <AlbumPageContent page={pages[currentPage]} /> : (
          <div className="flex flex-col items-center justify-center h-[400px] text-gray-400">
            <p className="text-lg">名片已生成</p>
            <p className="text-sm">点击智能匹配寻找商业机会</p>
          </div>
        )}
      </div>
      <div className="flex items-center justify-between mt-4 px-2">
        <button onClick={()=>onPageChange(currentPage-1)} disabled={currentPage===0}
          className="p-2 rounded-full hover:bg-gray-100 disabled:opacity-30 disabled:cursor-not-allowed transition-colors">
          <ChevronLeft className="w-5 h-5" />
        </button>
        <span className="text-sm text-gray-500">{currentPage+1} / {totalPages||1}</span>
        <button onClick={()=>onPageChange(currentPage+1)} disabled={currentPage>=totalPages-1}
          className="p-2 rounded-full hover:bg-gray-100 disabled:opacity-30 disabled:cursor-not-allowed transition-colors">
          <ChevronRight className="w-5 h-5" />
        </button>
      </div>
      <div className="flex justify-center gap-1.5 mt-2">{Array.from({length:totalPages||1}).map((_,i)=>(
        <button key={i} onClick={()=>onPageChange(i)} className={'w-2 h-2 rounded-full transition-colors '+(i===currentPage?'bg-blue-600':'bg-gray-300')} />
      ))}</div>
    </div>
  );
}
