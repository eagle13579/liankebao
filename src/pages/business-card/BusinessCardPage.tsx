import { useState, useCallback, useRef } from 'react';
import { useI18n } from '../../i18n/I18nContext';

interface CardResult {
  name: string;
  phone: string;
  email: string;
  company: string;
  position: string;
  address: string;
  raw: string;
}

function parseOCRText(text: string): CardResult {
  const lines = text.split('\n').map(l => l.trim()).filter(Boolean);
  const result: CardResult = { name: '', phone: '', email: '', company: '', position: '', address: '', raw: text };

  // 提取电话（支持国内外格式）
  const phoneRegex = /(?:电话|tel|mobile|phone|T|t)?\s*[:：]?\s*((?:\+?\d{1,4}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4})/i;
  const phoneMatch = text.match(phoneRegex);
  if (phoneMatch) result.phone = phoneMatch[1].trim();

  // 提取邮箱
  const emailRegex = /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/;
  const emailMatch = text.match(emailRegex);
  if (emailMatch) result.email = emailMatch[0];

  // 提取姓名（通常在名片前几行，不包含@和http）
  for (const line of lines.slice(0, 4)) {
    if (
      line.length >= 2 &&
      line.length <= 8 &&
      !line.includes('@') &&
      !line.includes('http') &&
      !line.includes('公司') &&
      !line.includes('有限') &&
      !line.includes('集团') &&
      !line.match(/^[\d\s\-+()]+$/)
    ) {
      result.name = line;
      break;
    }
  }

  // 提取公司
  for (const line of lines) {
    if (line.includes('公司') || line.includes('有限') || line.includes('集团') || line.includes('企业')) {
      result.company = line;
      break;
    }
  }

  // 提取职位
  for (const line of lines.slice(0, 6)) {
    if (
      line.includes('经理') || line.includes('总监') || line.includes('总裁') ||
      line.includes('CEO') || line.includes('CTO') || line.includes('VP') ||
      line.includes('director') || line.includes('manager') || line.includes('engineer')
    ) {
      result.position = line;
      break;
    }
  }

  return result;
}

export default function BusinessCardPage() {
  const { t } = useI18n();
  const [image, setImage] = useState<string | null>(null);
  const [scanning, setScanning] = useState(false);
  const [result, setResult] = useState<CardResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const processImage = useCallback(async (file: File) => {
    if (!file) return;

    // 显示预览
    const reader = new FileReader();
    reader.onload = (e) => {
      setImage(e.target?.result as string);
    };
    reader.readAsDataURL(file);

    // OCR 识别
    setScanning(true);
    setError(null);
    setResult(null);

    try {
      // 动态加载 Tesseract（按需加载，不增加首屏体积）
      const Tesseract = await import('tesseract.js');
      const { data } = await Tesseract.recognize(file, 'chi_sim+eng', {
        logger: (m) => {
          if (m.status === 'recognizing text') {
            // 可在这里加进度条
          }
        },
      });

      const parsed = parseOCRText(data.text);
      setResult(parsed);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('business_card.scan_fail'));
    } finally {
      setScanning(false);
    }
  }, [t]);

  const handleFile = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) processImage(file);
  }, [processImage]);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files?.[0];
    if (file && file.type.startsWith('image/')) {
      processImage(file);
    }
  }, [processImage]);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(true);
  }, []);

  const handleDragLeave = useCallback(() => setDragOver(false), []);

  const reset = useCallback(() => {
    setImage(null);
    setResult(null);
    setError(null);
    setScanning(false);
  }, []);

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <h1 className="text-2xl font-bold text-gray-800">{t('business_card.title')}</h1>

      {/* 上传区域 */}
      {!image && (
        <div
          onDrop={handleDrop}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onClick={() => fileRef.current?.click()}
          className={`
            border-2 border-dashed rounded-xl p-12 text-center cursor-pointer
            transition-all duration-200
            ${dragOver
              ? 'border-blue-500 bg-blue-50'
              : 'border-gray-300 hover:border-blue-400 hover:bg-gray-50'}
          `}
        >
          <div className="text-5xl mb-4">📇</div>
          <p className="text-gray-600 mb-2">{t('business_card.drop_hint')}</p>
          <p className="text-sm text-gray-400">{t('business_card.supported_formats')}</p>
          <input
            ref={fileRef}
            type="file"
            accept="image/jpeg,image/png,image/webp"
            onChange={handleFile}
            className="hidden"
          />
        </div>
      )}

      {/* 预览 */}
      {image && (
        <div className="space-y-4">
          <div className="relative rounded-xl overflow-hidden border border-gray-200 bg-gray-50">
            <img src={image} alt="名片" className="w-full object-contain max-h-80" />
            {scanning && (
              <div className="absolute inset-0 bg-black/40 flex items-center justify-center">
                <div className="bg-white rounded-xl p-6 text-center shadow-xl">
                  <div className="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
                  <p className="text-sm text-gray-600">{t('business_card.scanning')}</p>
                </div>
              </div>
            )}
          </div>

          <div className="flex gap-2">
            <button
              onClick={reset}
              disabled={scanning}
              className="px-4 py-2 rounded-lg border border-gray-300 text-gray-600
                         hover:bg-gray-50 disabled:opacity-50 transition-colors text-sm"
            >
              {t('business_card.retry')}
            </button>
          </div>
        </div>
      )}

      {/* 错误提示 */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-red-600 text-sm">
          {error}
        </div>
      )}

      {/* 识别结果 */}
      {result && (
        <div className="bg-white border border-gray-200 rounded-xl p-6 space-y-4">
          <h2 className="text-lg font-semibold text-gray-800 flex items-center gap-2">
            <span>✅</span> {t('business_card.scan_success')}
          </h2>

          <div className="grid grid-cols-1 gap-3">
            {[
              { label: t('business_card.name'), value: result.name },
              { label: t('business_card.phone'), value: result.phone, href: `tel:${result.phone}` },
              { label: t('business_card.email'), value: result.email, href: `mailto:${result.email}` },
              { label: t('business_card.company'), value: result.company },
              { label: t('business_card.position'), value: result.position },
              { label: t('business_card.address'), value: result.address },
            ].map(({ label, value, href }) => (
              value ? (
                <div key={label} className="flex items-center gap-3">
                  <span className="text-sm text-gray-400 w-16 flex-shrink-0">{label}</span>
                  {href ? (
                    <a
                      href={href}
                      className="text-blue-600 hover:underline text-sm break-all"
                    >
                      {value}
                    </a>
                  ) : (
                    <span className="text-sm text-gray-800">{value}</span>
                  )}
                </div>
              ) : null
            ))}
          </div>

          <details className="text-sm text-gray-400">
            <summary className="cursor-pointer hover:text-gray-600">OCR 原始文本</summary>
            <pre className="mt-2 p-3 bg-gray-50 rounded-lg text-xs whitespace-pre-wrap font-mono">
              {result.raw}
            </pre>
          </details>
        </div>
      )}
    </div>
  );
}
