import { useState } from 'react';
import { Save, User } from 'lucide-react';

interface ManualFormProps {
  onSubmit: (fields: Record<string, string>) => void;
  loading?: boolean;
  error?: string | null;
}

interface FieldError {
  [key: string]: string;
}

const FIELDS = [
  { key: 'name', label: '姓名', placeholder: '请输入姓名', required: true },
  { key: 'company', label: '公司', placeholder: '请输入公司名称', required: true },
  { key: 'position', label: '职位', placeholder: '请输入职位', required: true },
  { key: 'phone', label: '电话', placeholder: '请输入手机号', required: true },
  { key: 'wechat', label: '微信', placeholder: '请输入微信号', required: true },
  { key: 'bio', label: '简介', placeholder: '请输入个人简介', required: true, multiline: true },
];

const FIELD_LABELS: Record<string, string> = {
  name: '姓名',
  company: '公司',
  position: '职位',
  phone: '电话',
  wechat: '微信',
  bio: '简介',
};

export default function ManualForm({ onSubmit, loading, error }: ManualFormProps) {
  const [formData, setFormData] = useState<Record<string, string>>({});
  const [errors, setErrors] = useState<FieldError>({});
  const [touched, setTouched] = useState<Record<string, boolean>>({});

  const handleChange = (key: string, value: string) => {
    setFormData(prev => ({ ...prev, [key]: value }));
    if (touched[key]) {
      if (!value.trim()) {
        setErrors(prev => ({ ...prev, [key]: `${FIELD_LABELS[key] || key}不能为空` }));
      } else {
        setErrors(prev => {
          const next = { ...prev };
          delete next[key];
          return next;
        });
      }
    }
  };

  const handleBlur = (key: string) => {
    setTouched(prev => ({ ...prev, [key]: true }));
    if (!formData[key]?.trim()) {
      setErrors(prev => ({ ...prev, [key]: `${FIELD_LABELS[key] || key}不能为空` }));
    }
  };

  const validate = (): boolean => {
    const newErrors: FieldError = {};
    let valid = true;
    for (const field of FIELDS) {
      if (field.required && !formData[field.key]?.trim()) {
        newErrors[field.key] = `${FIELD_LABELS[field.key] || field.key}不能为空`;
        valid = false;
      }
    }
    setErrors(newErrors);
    setTouched(Object.fromEntries(FIELDS.map(f => [f.key, true])));
    return valid;
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (validate()) {
      onSubmit(formData);
    }
  };

  const allTouched = Object.keys(touched).length === FIELDS.length;
  const allFilled = FIELDS.every(f => formData[f.key]?.trim());
  const hasErrors = Object.keys(errors).length > 0;

  return (
    <div className="max-w-2xl mx-auto p-6">
      {/* Avatar placeholder - SVG only, no image upload */}
      <div className="flex flex-col items-center mb-8">
        <div className="w-24 h-24 rounded-full bg-gradient-to-br from-blue-100 to-blue-200 flex items-center justify-center border-2 border-blue-300">
          <User className="w-12 h-12 text-blue-400" />
        </div>
        <p className="mt-3 text-sm text-gray-500">头像将由系统自动生成</p>
      </div>

      <form onSubmit={handleSubmit} noValidate>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-x-4">
          {FIELDS.filter(f => !f.multiline).map(field => (
            <div key={field.key} className="mb-3">
              <label className="block text-sm font-medium text-gray-700 mb-1">
                {field.label}
                {field.required && <span className="text-red-500 ml-0.5">*</span>}
              </label>
              <input
                className={`w-full px-3 py-2 border rounded-lg outline-none transition-all ${
                  errors[field.key]
                    ? 'border-red-400 focus:ring-2 focus:ring-red-500'
                    : 'border-gray-300 focus:ring-2 focus:ring-blue-500 focus:border-blue-500'
                }`}
                value={formData[field.key] || ''}
                onChange={e => handleChange(field.key, e.target.value)}
                onBlur={() => handleBlur(field.key)}
                placeholder={field.placeholder}
              />
              {errors[field.key] && (
                <p className="mt-1 text-xs text-red-500">{errors[field.key]}</p>
              )}
            </div>
          ))}
        </div>

        {/* Bio (full width) */}
        <div className="mb-3">
          <label className="block text-sm font-medium text-gray-700 mb-1">
            简介
            <span className="text-red-500 ml-0.5">*</span>
          </label>
          <textarea
            className={`w-full px-3 py-2 border rounded-lg outline-none resize-none transition-all ${
              errors.bio
                ? 'border-red-400 focus:ring-2 focus:ring-red-500'
                : 'border-gray-300 focus:ring-2 focus:ring-blue-500 focus:border-blue-500'
            }`}
            rows={4}
            value={formData.bio || ''}
            onChange={e => handleChange('bio', e.target.value)}
            onBlur={() => handleBlur('bio')}
            placeholder="请输入个人简介"
          />
          {errors.bio && (
            <p className="mt-1 text-xs text-red-500">{errors.bio}</p>
          )}
        </div>

        {error && (
          <div className="mt-4 p-3 bg-red-50 text-red-600 rounded-lg text-sm border border-red-200">{error}</div>
        )}

        <div className="flex gap-3 mt-6">
          <button
            type="submit"
            disabled={loading || (allTouched && hasErrors)}
            className="flex-1 inline-flex items-center justify-center gap-2 px-6 py-3 bg-blue-600 text-white rounded-xl hover:bg-blue-700 disabled:opacity-50 transition-colors"
          >
            <Save className="w-5 h-5" />
            {loading ? '提交中...' : '保存名片'}
          </button>
        </div>
      </form>
    </div>
  );
}
