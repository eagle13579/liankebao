import { useState, useRef, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Upload, Camera, Share2, Copy, Check, ArrowLeft, Loader2,
  User, Briefcase, Building2, Phone, Mail, MessageCircle, MapPin, Globe,
  Sparkles, RefreshCw, ChevronLeft, ChevronRight, QrCode,
  Eye, EyeOff, ExternalLink, Download,
} from 'lucide-react';
import { api } from '../api/client';

// ============================================================
// 类型定义
// ============================================================

interface CardFields {
  name?: string;
  position?: string;
  company?: string;
  phone?: string;
  email?: string;
  wechat?: string;
  address?: string;
  website?: string;
  cover_image?: string;
}

interface AlbumPage {
  page: number;
  type: string;
  title: string;
  subtitle?: string;
  fields?: { label: string; value: string }[];
  content?: Record<string, string>;
  style: {
    background: string;
    textColor: string;
    accentColor: string;
  };
}

interface AlbumMeta {
  total_pages: number;
  pages: AlbumPage[];
  settings: {
    turn_animation: string;
    page_width: number;
    page_height: number;
    corner_radius: number;
    shadow: boolean;
  };
}

interface CardData {
  id: number;
  share_token: string;
  share_url: string;
  name: string;
  fields: CardFields;
  cover_image?: string;
  album_meta: AlbumMeta;
  created_at: string;
  view_count: number;
}

interface MatchItem {
  type: 'need' | 'product';
  id: number;
  title: string;
  category?: string;
  score: number;
  reasons: string[];
}

// ============================================================
// 状态枚举
// ============================================================
type Step = 'upload' | 'review' | 'preview' | 'matched';

// ============================================================
// 主组件
// ============================================================

export default function BusinessCardPage() {
  const navigate = useNavigate();

  // 管线状态
  const [step, setStep] = useState<Step>('upload');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  // 扫描结果
  const [rawText, setRawText] = useState('');
  const [fields, setFields] = useState<CardFields>({});
  const [suggestions, setSuggestions] = useState<string[]>([]);

  // 生成后的名片
  const [cardData, setCardData] = useState<CardData | null>(null);

  // 匹配结果
  const [matchResults, setMatchResults] = useState<MatchItem[]>([]);
  const [matchLoading, setMatchLoading] = useState(false);

  // 翻页控制
  const [currentPage, setCurrentPage] = useState(0);

  // 分享
  const [copied, setCopied] = useState(false);

  // QR 码
  const [qrCodeUrl, setQrCodeUrl] = useState('');
  const [showQRModal, setShowQRModal] = useState(false);
  const [qrLoading, setQrLoading] = useState(false);

  // 文件上传
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);

  // ============================================================
  // 管线步骤 1: 上传并扫描
  // ============================================================

  const handleFileSelect = async (file: File) => {
    const allowedTypes = [
      'application/pdf',
      'image/jpeg', 'image/png', 'image/bmp', 'image/webp', 'image/tiff',
    ];
    if (!allowedTypes.includes(file.type)) {
      setError('不支持的文件格式。请上传 PDF 或图片文件（JPG/PNG/BMP/WebP）');
      return;
    }

    setLoading(true);
    setError('');

    try {
      const formData = new FormData();
      formData.append('file', file);

      const res = await api.request('/api/card/scan', {
        method: 'POST',
        body: formData,
      });

      if (res.code !== 200) {
        setError(res.message || '扫描失败');
        return;
      }

      const data = res.data as { raw_text: string; fields: CardFields; suggestions: string[] };
      setRawText(data.raw_text || '');
      setFields(data.fields || {});
      setSuggestions(data.suggestions || []);
      setStep('review');
    } catch (e: any) {
      setError(e.message || '上传失败，请重试');
    } finally {
      setLoading(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFileSelect(file);
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(true);
  };

  const handleDragLeave = () => setDragOver(false);

  // ============================================================
  // 管线步骤 2: 编辑字段
  // ============================================================

  const updateField = (key: keyof CardFields, value: string) => {
    setFields((prev) => ({ ...prev, [key]: value || undefined }));
  };

  // ============================================================
  // 管线步骤 2→3: 生成数字名片
  // ============================================================

  const handleGenerate = async () => {
    if (!fields.name?.trim()) {
      setError('请至少填写姓名');
      return;
    }

    setLoading(true);
    setError('');

    try {
      const res = await api.post<CardData>('/api/card/generate', { fields });

      if (res.code !== 200 || !res.data) {
        setError(res.message || '生成失败');
        return;
      }

      setCardData(res.data);
      setCurrentPage(0);
      setStep('preview');
    } catch (e: any) {
      setError(e.message || '生成失败，请重试');
    } finally {
      setLoading(false);
    }
  };

  // ============================================================
  // 管线步骤 3→4: 供需匹配
  // ============================================================

  const handleMatch = async () => {
    if (!cardData) return;

    setMatchLoading(true);

    try {
      const res = await api.post<{ total: number; items: MatchItem[] }>(
        `/api/card/${cardData.id}/match`,
        {}
      );

      if (res.code !== 200 || !res.data) {
        setMatchResults([]);
        return;
      }

      setMatchResults(res.data.items || []);
      setStep('matched');
    } catch {
      setMatchResults([]);
    } finally {
      setMatchLoading(false);
    }
  };

  // ============================================================
  // 分享功能
  // ============================================================

  const shareUrl = cardData
    ? `${window.location.origin}/app/card/${cardData.share_token}`
    : '';

  const handleCopyLink = async () => {
    try {
      await navigator.clipboard.writeText(shareUrl);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback
      const input = document.createElement('input');
      input.value = shareUrl;
      document.body.appendChild(input);
      input.select();
      document.execCommand('copy');
      document.body.removeChild(input);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  // ============================================================
  // QR码下载
  // ============================================================

  const handleShowQR = async () => {
    if (!cardData?.id) return;

    setShowQRModal(true);
    setQrLoading(true);
    setQrCodeUrl('');

    try {
      // 用 fetch 获取二维码图片（返回 blob）
      const token = localStorage.getItem('token');
      const headers: Record<string, string> = {};
      if (token) headers['Authorization'] = `Bearer ${token}`;

      const response = await fetch(`/api/card/${cardData.id}/qrcode?download=false`, { headers });
      if (!response.ok) throw new Error('获取二维码失败');

      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      setQrCodeUrl(url);
    } catch (e: any) {
      console.error('QR码获取失败:', e);
      setQrCodeUrl('');
    } finally {
      setQrLoading(false);
    }
  };

  const handleDownloadQR = async () => {
    if (!cardData?.id) return;

    try {
      const token = localStorage.getItem('token');
      const headers: Record<string, string> = {};
      if (token) headers['Authorization'] = `Bearer ${token}`;

      const response = await fetch(`/api/card/${cardData.id}/qrcode?download=true`, { headers });
      if (!response.ok) throw new Error('下载二维码失败');

      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `card_${cardData.share_token}_qrcode.png`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (e: any) {
      console.error('QR码下载失败:', e);
    }
  };

  const handleCloseQR = () => {
    if (qrCodeUrl) {
      URL.revokeObjectURL(qrCodeUrl);
    }
    setShowQRModal(false);
    setQrCodeUrl('');
  };

  // ============================================================
  // 翻页控制
  // ============================================================

  const totalPages = cardData?.album_meta?.total_pages || 0;

  const goNextPage = () => {
    if (currentPage < totalPages - 1) setCurrentPage((p) => p + 1);
  };

  const goPrevPage = () => {
    if (currentPage > 0) setCurrentPage((p) => p - 1);
  };

  // ============================================================
  // 重置
  // ============================================================

  const handleReset = () => {
    setStep('upload');
    setFields({});
    setRawText('');
    setSuggestions([]);
    setCardData(null);
    setMatchResults([]);
    setCurrentPage(0);
    setError('');
  };

  // ============================================================
  // 渲染: 上传页面
  // ============================================================

  const renderUpload = () => (
    <div className="space-y-6">
      {/* Header */}
      <div className="text-center">
        <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-primary/10 mb-4">
          <Camera className="w-8 h-8 text-primary" />
        </div>
        <h2 className="text-xl font-bold text-on-surface">AI 名片扫描</h2>
        <p className="text-sm text-text-muted mt-1">
          上传名片图片或 PDF，AI 自动提取信息
        </p>
      </div>

      {/* Upload zone */}
      <div
        className={`relative border-2 border-dashed rounded-2xl p-12 text-center cursor-pointer transition-all duration-200 ${
          dragOver
            ? 'border-primary bg-primary/5'
            : 'border-border-light hover:border-primary/50 hover:bg-slate-50'
        }`}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onClick={() => fileInputRef.current?.click()}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.jpg,.jpeg,.png,.bmp,.webp,.tiff,.tif"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) handleFileSelect(file);
          }}
        />

        {loading ? (
          <div className="flex flex-col items-center gap-3">
            <Loader2 className="w-10 h-10 text-primary animate-spin" />
            <p className="text-sm text-text-muted">正在识别名片文字...</p>
            <div className="w-48 h-1.5 bg-slate-200 rounded-full overflow-hidden">
              <div className="h-full bg-primary rounded-full animate-pulse" style={{ width: '60%' }} />
            </div>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-3">
            <Upload className="w-10 h-10 text-text-muted" />
            <div>
              <p className="text-sm font-medium text-on-surface">
                点击上传或拖拽文件到此处
              </p>
              <p className="text-xs text-text-muted mt-1">
                支持 PDF、JPG、PNG、BMP、WebP 格式
              </p>
            </div>
          </div>
        )}
      </div>

      {/* Sample cards hint */}
      <div className="text-center">
        <p className="text-xs text-text-muted">
          <Sparkles className="w-3 h-3 inline mr-1" />
          AI 自动识别姓名、职位、公司、联系方式等信息
        </p>
      </div>
    </div>
  );

  // ============================================================
  // 渲染: 审核编辑页面
  // ============================================================

  const renderReview = () => (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <button
          onClick={() => setStep('upload')}
          className="p-2 rounded-lg hover:bg-slate-100 transition-colors"
        >
          <ArrowLeft className="w-5 h-5" />
        </button>
        <div>
          <h2 className="text-lg font-bold text-on-surface">确认名片信息</h2>
          <p className="text-xs text-text-muted">请核对 AI 提取的信息，可手动修改</p>
        </div>
      </div>

      {/* Suggestions */}
      {suggestions.length > 0 && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-3">
          <div className="flex gap-2">
            <Sparkles className="w-4 h-4 text-amber-500 mt-0.5 shrink-0" />
            <div className="text-xs text-amber-800 space-y-1">
              {suggestions.map((s, i) => (
                <p key={i}>{s}</p>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Raw text (collapsible) */}
      {rawText && (
        <details className="bg-slate-50 rounded-xl p-3">
          <summary className="text-xs text-text-muted cursor-pointer select-none">
            OCR 原始识别文字
          </summary>
          <p className="text-xs text-text-muted mt-2 whitespace-pre-wrap">{rawText}</p>
        </details>
      )}

      {/* Editable fields */}
      <div className="grid grid-cols-1 gap-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <FieldInput
            icon={<User className="w-4 h-4" />}
            label="姓名 *"
            value={fields.name || ''}
            onChange={(v) => updateField('name', v)}
            placeholder="请输入姓名"
          />
          <FieldInput
            icon={<Briefcase className="w-4 h-4" />}
            label="职位"
            value={fields.position || ''}
            onChange={(v) => updateField('position', v)}
            placeholder="请输入职位"
          />
        </div>

        <FieldInput
          icon={<Building2 className="w-4 h-4" />}
          label="公司"
          value={fields.company || ''}
          onChange={(v) => updateField('company', v)}
          placeholder="请输入公司名称"
        />

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <FieldInput
            icon={<Phone className="w-4 h-4" />}
            label="手机"
            value={fields.phone || ''}
            onChange={(v) => updateField('phone', v)}
            placeholder="请输入手机号"
            type="tel"
          />
          <FieldInput
            icon={<Mail className="w-4 h-4" />}
            label="邮箱"
            value={fields.email || ''}
            onChange={(v) => updateField('email', v)}
            placeholder="请输入邮箱"
            type="email"
          />
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <FieldInput
            icon={<MessageCircle className="w-4 h-4" />}
            label="微信"
            value={fields.wechat || ''}
            onChange={(v) => updateField('wechat', v)}
            placeholder="请输入微信号"
          />
          <FieldInput
            icon={<Globe className="w-4 h-4" />}
            label="官网"
            value={fields.website || ''}
            onChange={(v) => updateField('website', v)}
            placeholder="请输入网址"
          />
        </div>

        <FieldInput
          icon={<MapPin className="w-4 h-4" />}
          label="地址"
          value={fields.address || ''}
          onChange={(v) => updateField('address', v)}
          placeholder="请输入地址"
        />
      </div>

      {/* Action buttons */}
      <div className="flex gap-3">
        <button
          onClick={handleReset}
          className="flex-1 py-3 px-4 rounded-xl border border-border-light text-on-surface font-medium text-sm hover:bg-slate-50 transition-colors"
        >
          重新上传
        </button>
        <button
          onClick={handleGenerate}
          disabled={loading || !fields.name?.trim()}
          className="flex-1 py-3 px-4 rounded-xl bg-primary text-white font-medium text-sm hover:bg-primary-container transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
        >
          {loading ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              生成中...
            </>
          ) : (
            <>
              <Sparkles className="w-4 h-4" />
              生成数字名片
            </>
          )}
        </button>
      </div>
    </div>
  );

  // ============================================================
  // 渲染: 翻页预览
  // ============================================================

  const renderPreview = () => {
    if (!cardData?.album_meta) return null;

    const page = cardData.album_meta.pages[currentPage];
    if (!page) return null;

    const settings = cardData.album_meta.settings;

    return (
      <div className="space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-bold text-on-surface">数字名片</h2>
            <p className="text-xs text-text-muted">
              {cardData.name} · 浏览 {cardData.view_count} 次
            </p>
          </div>
          <button
            onClick={() => setStep('review')}
            className="text-xs text-primary hover:text-primary-container transition-colors"
          >
            重新编辑
          </button>
        </div>

        {/* 3D Flip Book Preview */}
        <div className="flex flex-col items-center">
          <div
            className="relative rounded-2xl overflow-hidden transition-all duration-500 select-none"
            style={{
              width: settings.page_width,
              height: settings.page_height,
              borderRadius: settings.corner_radius,
              boxShadow: settings.shadow
                ? '0 20px 60px rgba(0,0,0,0.15), 0 8px 20px rgba(0,0,0,0.1)'
                : 'none',
              perspective: '1500px',
            }}
          >
            {/* Page content */}
            <div
              className="w-full h-full p-6 flex flex-col transition-all duration-500"
              style={{
                background: page.style.background,
                color: page.style.textColor,
                transform: `rotateY(${0}deg)`,
                transformStyle: 'preserve-3d',
              }}
            >
              {renderPageContent(page)}
            </div>

            {/* Page edge shadow effect */}
            <div
              className="absolute top-0 right-0 w-4 h-full pointer-events-none"
              style={{
                background: 'linear-gradient(to left, rgba(0,0,0,0.08), transparent)',
              }}
            />

            {/* Page curl corner */}
            <div
              className="absolute bottom-0 right-0 w-8 h-8 pointer-events-none"
              style={{
                background: `linear-gradient(135deg, transparent 50%, rgba(0,0,0,0.04) 50%)`,
              }}
            />
          </div>

          {/* Page navigation */}
          <div className="flex items-center gap-4 mt-4">
            <button
              onClick={goPrevPage}
              disabled={currentPage === 0}
              className="p-2 rounded-full hover:bg-slate-100 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
            >
              <ChevronLeft className="w-5 h-5" />
            </button>

            <div className="flex gap-1.5">
              {Array.from({ length: totalPages }).map((_, i) => (
                <button
                  key={i}
                  onClick={() => setCurrentPage(i)}
                  className={`w-2 h-2 rounded-full transition-all duration-300 ${
                    i === currentPage
                      ? 'bg-primary w-6'
                      : 'bg-slate-300 hover:bg-slate-400'
                  }`}
                />
              ))}
            </div>

            <button
              onClick={goNextPage}
              disabled={currentPage === totalPages - 1}
              className="p-2 rounded-full hover:bg-slate-100 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
            >
              <ChevronRight className="w-5 h-5" />
            </button>
          </div>

          <p className="text-xs text-text-muted mt-2">
            第 {currentPage + 1} 页，共 {totalPages} 页
          </p>
        </div>

        {/* Share & Match actions */}
        <div className="space-y-3">
          {/* Share link */}
          <div className="flex items-center gap-2">
            <div className="flex-1 bg-slate-50 rounded-xl px-3 py-2.5 text-xs text-on-surface truncate">
              {shareUrl}
            </div>
            <button
              onClick={handleCopyLink}
              className="p-2.5 rounded-xl bg-primary/10 text-primary hover:bg-primary/20 transition-colors"
              title={copied ? '已复制' : '复制链接'}
            >
              {copied ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
            </button>
          </div>

          {/* Action buttons */}
          <div className="flex gap-3">
            <button
              onClick={handleMatch}
              disabled={matchLoading}
              className="flex-1 py-3 px-4 rounded-xl bg-gradient-to-r from-primary to-purple-600 text-white font-medium text-sm hover:opacity-90 transition-opacity disabled:opacity-50 flex items-center justify-center gap-2"
            >
              {matchLoading ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <RefreshCw className="w-4 h-4" />
              )}
              AI 供需匹配
            </button>
            <button
              onClick={handleCopyLink}
              className="flex-1 py-3 px-4 rounded-xl border border-border-light text-on-surface font-medium text-sm hover:bg-slate-50 transition-colors flex items-center justify-center gap-2"
            >
              <Share2 className="w-4 h-4" />
              分享
            </button>
            <button
              onClick={handleShowQR}
              className="py-3 px-4 rounded-xl border border-border-light text-on-surface font-medium text-sm hover:bg-slate-50 transition-colors flex items-center justify-center gap-2"
            >
              <QrCode className="w-4 h-4" />
              画册QR
            </button>
          </div>

          {/* QR Code Modal */}
          {showQRModal && (
            <div
              className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
              onClick={handleCloseQR}
            >
              <div
                className="bg-white rounded-2xl p-6 mx-4 max-w-xs w-full shadow-2xl"
                onClick={(e) => e.stopPropagation()}
              >
                <h3 className="text-base font-bold text-center text-on-surface mb-1">
                  分享画册二维码
                </h3>
                <p className="text-xs text-text-muted text-center mb-4">
                  扫码即可查看您的数字名片画册
                </p>

                <div className="flex justify-center mb-4">
                  {qrLoading ? (
                    <div className="w-48 h-48 flex items-center justify-center">
                      <Loader2 className="w-8 h-8 text-primary animate-spin" />
                    </div>
                  ) : qrCodeUrl ? (
                    <img
                      src={qrCodeUrl}
                      alt="名片二维码"
                      className="w-48 h-48 rounded-xl"
                    />
                  ) : (
                    <div className="w-48 h-48 flex items-center justify-center bg-slate-50 rounded-xl">
                      <p className="text-xs text-text-muted">加载失败</p>
                    </div>
                  )}
                </div>

                <div className="flex gap-2">
                  <button
                    onClick={handleCloseQR}
                    className="flex-1 py-2.5 rounded-xl border border-border-light text-sm text-on-surface font-medium hover:bg-slate-50 transition-colors"
                  >
                    关闭
                  </button>
                  <button
                    onClick={handleDownloadQR}
                    disabled={!qrCodeUrl}
                    className="flex-1 py-2.5 rounded-xl bg-primary text-white text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50 flex items-center justify-center gap-1.5"
                  >
                    <Download className="w-4 h-4" />
                    保存图片
                  </button>
                </div>

                <p className="text-[10px] text-text-muted text-center mt-3">
                  长按或点击「保存图片」即可保存到相册分享
                </p>
              </div>
            </div>
          )}
        </div>

        {/* Match results (if already matched) */}
        {matchResults.length > 0 && (
          <div className="border-t border-border-light pt-4">
            <h3 className="text-sm font-bold text-on-surface mb-3 flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-primary" />
              AI 匹配结果 ({matchResults.length})
            </h3>
            <div className="space-y-2">
              {matchResults.slice(0, 5).map((item) => (
                <div
                  key={`${item.type}-${item.id}`}
                  className="bg-slate-50 rounded-xl p-3 flex items-start gap-3"
                >
                  <span className={`px-2 py-0.5 rounded text-[10px] font-medium ${
                    item.type === 'need' ? 'bg-amber-100 text-amber-700' : 'bg-blue-100 text-blue-700'
                  }`}>
                    {item.type === 'need' ? '需求' : '产品'}
                  </span>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-on-surface truncate">
                      {item.title}
                    </p>
                    <div className="flex items-center gap-2 mt-0.5">
                      <span className="text-xs text-text-muted">{item.category}</span>
                      <span className={`text-xs font-medium ${
                        item.score >= 0.7 ? 'text-green-600' : item.score >= 0.4 ? 'text-amber-600' : 'text-text-muted'
                      }`}>
                        匹配度 {Math.round(item.score * 100)}%
                      </span>
                    </div>
                  </div>
                  <ExternalLink className="w-4 h-4 text-text-muted shrink-0" />
                </div>
              ))}
              {matchResults.length > 5 && (
                <p className="text-xs text-primary text-center py-2">
                  还有 {matchResults.length - 5} 个匹配结果
                </p>
              )}
            </div>
          </div>
        )}

        {/* Create another */}
        <button
          onClick={handleReset}
          className="w-full py-3 rounded-xl border border-border-light text-on-surface font-medium text-sm hover:bg-slate-50 transition-colors"
        >
          创建新名片
        </button>
      </div>
    );
  };

  // ============================================================
  // 辅助: 渲染页面内容
  // ============================================================

  const renderPageContent = (page: AlbumPage) => {
    switch (page.type) {
      case 'cover':
        return (
          <div className="flex flex-col items-center justify-center h-full text-center">
            <div className="w-20 h-20 rounded-full bg-white/20 flex items-center justify-center mb-4">
              <User className="w-10 h-10 text-white" />
            </div>
            <h3 className="text-2xl font-bold mb-1">{page.title}</h3>
            {page.subtitle && (
              <p className="text-sm opacity-80">{page.subtitle}</p>
            )}
            <div
              className="mt-6 px-4 py-1.5 rounded-full text-xs font-medium"
              style={{
                background: page.style.accentColor,
                color: '#ffffff',
              }}
            >
              Powered by 链客宝AI AI
            </div>
          </div>
        );

      case 'contact':
        return (
          <div className="flex flex-col h-full">
            <h3 className="text-base font-bold mb-4" style={{ color: page.style.accentColor }}>
              {page.title}
            </h3>
            <div className="flex-1 space-y-3">
              {(page.fields || []).map((f, i) => (
                <div key={i} className="flex items-start gap-2">
                  <span className="text-xs opacity-60 w-10 shrink-0">{f.label.split(' ')[0]}</span>
                  <span className="text-sm font-medium">{f.value}</span>
                </div>
              ))}
              {(!page.fields || page.fields.length === 0) && (
                <p className="text-sm opacity-60">暂无联系方式</p>
              )}
            </div>
          </div>
        );

      case 'company':
        return (
          <div className="flex flex-col h-full">
            <h3 className="text-base font-bold mb-4" style={{ color: page.style.accentColor }}>
              {page.title}
            </h3>
            <div className="flex-1 space-y-3">
              {page.content?.company && (
                <div>
                  <p className="text-xs opacity-60 mb-0.5">公司</p>
                  <p className="text-sm font-medium">{page.content.company}</p>
                </div>
              )}
              {page.content?.position && (
                <div>
                  <p className="text-xs opacity-60 mb-0.5">职位</p>
                  <p className="text-sm font-medium">{page.content.position}</p>
                </div>
              )}
              {page.content?.address && (
                <div>
                  <p className="text-xs opacity-60 mb-0.5">地址</p>
                  <p className="text-sm">{page.content.address}</p>
                </div>
              )}
              {page.content?.website && (
                <div>
                  <p className="text-xs opacity-60 mb-0.5">官网</p>
                  <p className="text-sm text-blue-600 truncate">{page.content.website}</p>
                </div>
              )}
            </div>
          </div>
        );

      case 'qrcode':
        return (
          <div className="flex flex-col items-center justify-center h-full text-center">
            <div
              className="w-40 h-40 rounded-2xl flex items-center justify-center mb-4"
              style={{ background: page.style.accentColor + '15' }}
            >
              <QrCode
                className="w-24 h-24"
                style={{ color: page.style.accentColor }}
              />
            </div>
            <h3 className="text-base font-bold">{page.title}</h3>
            {page.subtitle && (
              <p className="text-xs opacity-60 mt-1">{page.subtitle}</p>
            )}
          </div>
        );

      default:
        return (
          <div className="flex items-center justify-center h-full">
            <p className="text-sm opacity-60">{page.title}</p>
          </div>
        );
    }
  };

  // ============================================================
  // 渲染: 主界面
  // ============================================================

  return (
    <div className="min-h-screen bg-neutral-bg">
      {/* Top bar */}
      <div className="sticky top-0 z-10 bg-white/80 backdrop-blur-xl border-b border-border-light">
        <div className="max-w-lg mx-auto px-4 py-3 flex items-center gap-3">
          <button
            onClick={() => navigate(-1)}
            className="p-2 -ml-2 rounded-lg hover:bg-slate-100 transition-colors"
          >
            <ArrowLeft className="w-5 h-5" />
          </button>
          <h1 className="text-base font-bold text-on-surface">AI 数字名片</h1>
        </div>
      </div>

      {/* Content */}
      <div className="max-w-lg mx-auto px-4 py-6">
        {/* Error */}
        {error && (
          <div className="mb-4 bg-rose-50 border border-rose-200 rounded-xl p-3 text-xs text-rose-700">
            {error}
            <button
              onClick={() => setError('')}
              className="ml-2 underline"
            >
              关闭
            </button>
          </div>
        )}

        {/* Step indicator */}
        {step !== 'upload' && (
          <div className="flex items-center gap-2 mb-6">
            {(['upload', 'review', 'preview'] as Step[]).map((s, i) => {
              const idx = ['upload', 'review', 'preview'].indexOf(step);
              const isActive = i <= idx && step === 'preview';
              return (
                <div key={s} className="flex items-center gap-2">
                  <div className={`w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-bold transition-colors ${
                    i <= idx ? 'bg-primary text-white' : 'bg-slate-200 text-slate-400'
                  }`}>
                    {i + 1}
                  </div>
                  {i < 2 && (
                    <div className={`w-8 h-0.5 transition-colors ${
                      i < idx ? 'bg-primary' : 'bg-slate-200'
                    }`} />
                  )}
                </div>
              );
            })}
          </div>
        )}

        {/* Render current step */}
        {step === 'upload' && renderUpload()}
        {step === 'review' && renderReview()}
        {step === 'preview' && renderPreview()}
        {step === 'matched' && renderPreview()}
      </div>
    </div>
  );
}

// ============================================================
// 字段输入组件
// ============================================================

function FieldInput({
  icon,
  label,
  value,
  onChange,
  placeholder,
  type = 'text',
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  type?: string;
}) {
  return (
    <div>
      <label className="block text-xs font-medium text-on-surface mb-1.5 flex items-center gap-1.5">
        {icon}
        {label}
      </label>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full px-3 py-2.5 rounded-xl border border-border-light bg-white text-sm text-on-surface placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary transition-all"
      />
    </div>
  );
}
