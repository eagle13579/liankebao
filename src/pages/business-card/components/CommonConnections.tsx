import { Users } from 'lucide-react';

interface CommonConnectionsProps {
  count: number;
  names: string[];
  onViewNetwork: () => void;
}

export default function CommonConnections({
  count,
  names,
  onViewNetwork,
}: CommonConnectionsProps) {
  if (count === 0) return null;

  return (
    <div className="bg-blue-50 border border-blue-200 rounded-xl p-3">
      <div className="flex items-start gap-2">
        <Users className="w-4 h-4 text-blue-500 mt-0.5 shrink-0" />
        <div className="flex-1 min-w-0">
          <p className="text-xs font-medium text-blue-800">
            共同好友 ({count})
          </p>
          {names.length > 0 && (
            <p className="text-xs text-blue-600 mt-0.5 truncate">
              {names.join('、')}{names.length < count && `等${count}人`}
            </p>
          )}
          <button
            onClick={onViewNetwork}
            className="text-xs text-blue-700 font-medium mt-1 underline hover:no-underline"
          >
            查看人脉网络
          </button>
        </div>
      </div>
    </div>
  );
}
