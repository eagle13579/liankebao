export default function Dashboard() {
  return (
    <div>
      <h1 className="text-2xl font-semibold text-gray-800 mb-4">仪表盘</h1>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-white rounded-lg shadow p-4">欢迎使用链客宝</div>
        <div className="bg-white rounded-lg shadow p-4">数据概览</div>
        <div className="bg-white rounded-lg shadow p-4">快捷操作</div>
      </div>
    </div>
  );
}
