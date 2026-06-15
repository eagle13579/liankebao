interface Props { label: string; value?: string; onChange: (v:string)=>void; placeholder?: string; icon?: React.ReactNode; }
export default function FieldInput({ label, value, onChange, placeholder, icon }: Props) {
  return (
    <div className="mb-3">
      <label className="block text-sm font-medium text-gray-700 mb-1">{icon} {label}</label>
      <input className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition-all"
        value={value||""} onChange={e => onChange(e.target.value)} placeholder={placeholder} />
    </div>
  );
}
