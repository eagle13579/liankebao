import { useState, useCallback } from 'react';
import { useBusinessCard } from './hooks';
import UploadZone from './components/UploadZone';
import ReviewForm from './components/ReviewForm';
import FlipBook from './components/FlipBook';
import CommonConnections from './components/CommonConnections';
import ShareActions from './components/ShareActions';
import MatchResultsPanel from './components/MatchResultsPanel';
import QRCodeModal from './components/QRCodeModal';
import StepIndicator from './components/StepIndicator';
import ManualForm from './components/ManualForm';
import NLSearchWidget from '../../components/NLSearchWidget';
import type { NLSearchResult, NLSearchApiItem } from '../../components/NLSearchWidget';

export default function BusinessCardPage() {
  const {
    step, loading, error, fields, suggestions, rawText,
    cardData, currentPage, totalPages, matchResults,
    showQRModal, qrCodeUrl, commonConnections, copied,
    fileInputRef,
    handleFileSelect, handleDrop, updateField,
    handleGenerate, handleMatch, handleCopyLink,
    handleShowQR, handleDownloadQR, handleReset,
    setCurrentPage, setShowQRModal, setCardData,
  } = useBusinessCard();

  const dragOver = false; // handled by useBusinessCard or local state if needed
  const [activeTab, setActiveTab] = useState<'upload' | 'manual'>('upload');

  const handleManualSubmit = async (cardData: import('./types').CardData) => {
    setCardData(cardData);
    setCurrentPage(0);
    setStep('preview');
  };

  /** NL搜索回调 — 结构化解析 + API搜索 */
  const handleNLSearch = useCallback((result: NLSearchResult) => {
    console.log('[NLSearchWidget] 结构化搜索结果:', result);
  }, []);

  /** NL搜索 — 选中某个搜索结果 */
  const handleNLResultSelect = useCallback((item: NLSearchApiItem) => {
    console.log('[NLSearchWidget] 选中的企业:', item);
    const msg = `已选中: ${item.title} (匹配度 ${Math.round(item.match_score * 100)}%)`;
    console.log(`[NLSearchWidget] ${msg}`);
  }, []);

  return (
    <div className="min-h-screen bg-gradient-to-b from-gray-50 to-white">
      {/* Hidden file input */}
      <input ref={fileInputRef} type="file" className="hidden" accept="image/*,.pdf"
        onChange={e => { const f = e.target.files?.[0]; if (f) handleFileSelect(f); }} />

      {/* Header */}
      <header className="sticky top-0 z-10 bg-white/80 backdrop-blur-sm border-b border-gray-100">
        <div className="max-w-4xl mx-auto px-4 py-3">
          <div className="flex items-center justify-between">
            <h1 className="text-lg font-semibold text-gray-800">AI 数字名片</h1>
            <div className="flex items-center gap-2">
              <button onClick={() => fileInputRef.current?.click()} className="text-sm text-blue-600 hover:text-blue-700 transition-colors">
                重新上传
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* Error */}
      {error && (
        <div className="max-w-4xl mx-auto px-4 mt-2">
          <div className="p-3 bg-red-50 border border-red-200 rounded-xl text-red-600 text-sm">{error}</div>
        </div>
      )}

      {/* Step Indicator */}
      <StepIndicator currentStep={step} />

      {/* 自然语言搜索组件 — 紧凑模式嵌入 */}
      <div className="max-w-4xl mx-auto px-4 mb-4">
        <NLSearchWidget compact onSearch={handleNLSearch} onResultSelect={handleNLResultSelect} />
      </div>

      {/* Content */}
      <div className="max-w-4xl mx-auto px-4 pb-8">
        {/* Tab Switcher — only at upload step */}
        {step === 'upload' && (
          <div className="flex mb-6 border-b border-gray-200">
            <button
              onClick={() => setActiveTab('upload')}
              className={`px-6 py-3 text-sm font-medium transition-colors relative ${
                activeTab === 'upload'
                  ? 'text-blue-600'
                  : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              上传识别
              {activeTab === 'upload' && (
                <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-blue-600 rounded-full" />
              )}
            </button>
            <button
              onClick={() => setActiveTab('manual')}
              className={`px-6 py-3 text-sm font-medium transition-colors relative ${
                activeTab === 'manual'
                  ? 'text-blue-600'
                  : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              手动输入
              {activeTab === 'manual' && (
                <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-blue-600 rounded-full" />
              )}
            </button>
          </div>
        )}

        {step === 'upload' && activeTab === 'upload' && (
          <UploadZone
            loading={loading}
            dragOver={false}
            onDrop={handleDrop}
            onDragOver={e => e.preventDefault()}
            onDragLeave={e => e.preventDefault()}
            onClick={() => fileInputRef.current?.click()}
          />
        )}

        {step === 'upload' && activeTab === 'manual' && (
          <ManualForm
            onSubmit={handleManualSubmit}
            loading={loading}
            error={error}
          />
        )}

        {step === 'review' && (
          <ReviewForm
            fields={fields}
            suggestions={suggestions}
            rawText={rawText}
            onUpdateField={updateField}
            onGenerate={handleGenerate}
            onReset={handleReset}
            loading={loading}
            error={error}
          />
        )}

        {(step === 'preview' || step === 'matched') && cardData && (
          <>
            <FlipBook
              pages={cardData.album_pages || []}
              currentPage={currentPage}
              totalPages={totalPages}
              cardData={cardData}
              onPageChange={setCurrentPage}
            />
            <CommonConnections count={commonConnections.count} names={commonConnections.names} />
            <ShareActions
              shareUrl={window.location.href}
              copied={copied}
              matchLoading={loading}
              onCopy={handleCopyLink}
              onMatch={handleMatch}
              onShowQR={handleShowQR}
            />
            {step === 'matched' && <MatchResultsPanel items={matchResults} loading={loading} />}
          </>
        )}
      </div>

      {/* QR Modal */}
      <QRCodeModal
        show={showQRModal}
        onClose={() => setShowQRModal(false)}
        onDownload={handleDownloadQR}
        qrCodeUrl={qrCodeUrl}
        qrLoading={false}
      />
    </div>
  );
}
