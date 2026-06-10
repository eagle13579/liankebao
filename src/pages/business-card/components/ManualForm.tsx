import { useState } from 'react';
import { generateCard } from '../api';
import type { CardData } from '../types';
import { Loader2 } from 'lucide-react';

interface Props {
  onSubmit: (data: CardData) => void;
  loading?: boolean;
  error?: string | null;
}

interface FormErrors {
  name?: string;
  company?: string;
  position?: string;
}

export default function ManualForm({ onSubmit, error: parentError }: Props) {
  const [name, setName] = useState('');
  const [company, setCompany] = useState('');
  const [position, setPosition] = useState('');
  const [phone, setPhone] = useState('');
  const [wechat, setWechat] = useState('');
  const [bio, setBio] = useState('');
  const [errors, setErrors] = useState<FormErrors>({});
  const [loading, setLoading] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);

  const validate = (): boolean => {
    const newErrors: FormErrors = {};
    if (!name.trim()) newErrors.name = '请输入姓名';
    if (!company.trim()) newErrors.company = '请输入公司';
    if (!position.trim()) newErrors.position = '请输入职位';
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validate()) return;
    setLoading(true);
    setLocalError(null);
    try {
      const fields = {
        name: name.trim(),
        company: company.trim(),
        position: position.trim(),
        phone: phone.trim(),
        wechat: wechat.trim(),
        bio: bio.trim(),
      };
      const result = await generateCard(fields);
      onSubmit(result);
    } catch (err: any) {
      setLocalError(err?.message || '生成失败');
    } finally {
      setLoading(false);
    }
  };

  const displayError = localError || parentError;

  const inputCls = (hasError?: boolean) =>
    `w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition-all ${
      hasError ? 'border-red-300 bg-red-50' : 'border-gray-300'
    }`;

  const labelCls = 'block text-sm font-medium text-gray-700 mb-1';

  return (
    <div className="max-w-lg mx-auto">
      {/* SVG Avatar Placeholder */}
      <div className="flex justify-center mb-6">
        <div className="w-20 h-20 rounded-full bg-gray-100 flex items-center justify-center">
          <svg className="w-10 h-10 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
              d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
          </svg>
        </div>
      </div>

      {/* Error */}
      {displayError && (
        <div className="p-3 mb-4 bg-red-50 border border-red-200 rounded-xl text-red-600 text-sm">
          {displayError}
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-4">
        {/* 姓名 */}
        <div>
          <label className={labelCls}>
            姓名 <span className="text-red-500">*</span>
          </label>
          <input
            className={inputCls(!!errors.name)}
            value={name}
            onChange={e => setName(e.target.value)}
            placeholder="请输入姓名"
          />
          {errors.name && <p className="text-xs text-red-500 mt-1">{errors.name}</p>}
        </div>

        {/* 公司 */}
        <div>
          <label className={labelCls}>
            公司 <span className="text-red-500">*</span>
          </label>
          <input
            className={inputCls(!!errors.company)}
            value={company}
            onChange={e => setCompany(e.target.value)}
            placeholder="请输入公司名称"
          />
          {errors.company && <p className="text-xs text-red-500 mt-1">{errors.company}</p>}
        </div>

        {/* 职位 */}
        <div>
          <label className={labelCls}>
            职位 <span className="text-red-500">*</span>
          </label>
          <input
            className={inputCls(!!errors.position)}
            value={position}
            onChange={e => setPosition(e.target.value)}
            placeholder="请输入职位"
          />
          {errors.position && <p className="text-xs text-red-500 mt-1">{errors.position}</p>}
        </div>

        {/* 电话 */}
        <div>
          <label className={labelCls}>电话</label>
          <input
            className={inputCls()}
            value={phone}
            onChange={e => setPhone(e.target.value)}
            placeholder="请输入电话号码"
          />
        </div>

        {/* 微信 */}
        <div>
          <label className={labelCls}>微信</label>
          <input
            className={inputCls()}
            value={wechat}
            onChange={e => setWechat(e.target.value)}
            placeholder="请输入微信号"
          />
        </div>

        {/* 简介 */}
        <div>
          <label className={labelCls}>简介</label>
          <textarea
            className={inputCls() + ' min-h-[80px] resize-none'}
            value={bio}
            onChange={e => setBio(e.target.value)}
            placeholder="请输入个人简介"
            rows={3}
          />
        </div>

        {/* Submit */}
        <button
          type="submit"
          disabled={loading}
          className="w-full py-3 bg-blue-600 text-white rounded-xl font-medium hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
        >
          {loading && <Loader2 className="w-5 h-5 animate-spin" />}
          {loading ? '生成中...' : '生成电子名片'}
        </button>
      </form>
    </div>
  );
}
