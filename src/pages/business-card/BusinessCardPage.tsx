import { useBusinessCard } from './hooks';
import UploadZone from './components/UploadZone';
import ReviewForm from './components/ReviewForm';
import FlipBook from './components/FlipBook';
import CommonConnections from './components/CommonConnections';
import ShareActions from './components/ShareActions';
import MatchResultsPanel from './components/MatchResultsPanel';
import QRCodeModal from './components/QRCodeModal';
import StepIndicator from './components/StepIndicator';

export default function BusinessCardPage() {
  const {
    step, loading, error, fields, suggestions, rawText,
    cardData, currentPage, totalPages, matchResults,
    showQRModal, qrCodeUrl, commonConnections, copied,
    fileInputRef,
    handleFileSelect, handleDrop, updateField,
    handleGenerate, handleMatch, handleCopyLink,
    handleShowQR, handleDownloadQR, handleReset,
    setCurrentPage, setShowQRModal,
  } = useBusinessCard();

  const dragOver = false; // handled by useBusinessCard or local state if needed

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

      {/* Content */}
      <div className="max-w-4xl mx-auto px-4 pb-8">
        {step === 'upload' && (
          <UploadZone
            loading={loading}
            dragOver={false}
            onDrop={handleDrop}
            onDragOver={e => e.preventDefault()}
            onDragLeave={e => e.preventDefault()}
            onClick={() => fileInputRef.current?.click()}
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
