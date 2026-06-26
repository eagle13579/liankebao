import { useState, useRef, useEffect, useCallback } from 'react';
import type { CardFields, CardData, MatchItem, Step } from './types';
import * as cardApi from './api';
import { fetchCredits, fetchUserProfile } from './api-matching';

export function useBusinessCard() {
  const [step, setStep] = useState<Step>('upload');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fields, setFields] = useState<CardFields>({});
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [rawText, setRawText] = useState('');
  const [cardData, setCardData] = useState<CardData | null>(null);

  const [currentPage, setCurrentPage] = useState(0);
  const [matchResults, setMatchResults] = useState<MatchItem[]>([]);
  const [showQRModal, setShowQRModal] = useState(false);
  const [qrCodeUrl, setQrCodeUrl] = useState('');
  const [commonConnections, setCommonConnections] = useState<{count:number;names:string[]}>({count:0,names:[]});
  const [copied, setCopied] = useState(false);
  const [remainingCredits, setRemainingCredits] = useState<number | undefined>(undefined);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const totalPages = cardData?.album_pages?.length || 0;

  // Fetch remaining credits on mount — try /api/user/profile first (match_credits), fallback to /api/membership/credits
  useEffect(() => {
    fetchUserProfile()
      .then((profile) => setRemainingCredits(profile.match_credits))
      .catch(() => {
        fetchCredits()
          .then((res) => setRemainingCredits(res.credits))
          .catch(() => setRemainingCredits(undefined));
      });
  }, []);

  const handleFileSelect = useCallback(async (file: File) => {
    setLoading(true); setError(null);
    try { const r = await cardApi.scanCard(file); setSuggestions(r.suggestions||[]); setRawText(r.raw_text||''); setFields(r.fields||{}); setStep('review'); }
    catch(e:any) { setError(e?.message||'扫描失败'); } finally { setLoading(false); }
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => { e.preventDefault(); const f=e.dataTransfer.files[0]; if(f) handleFileSelect(f); }, [handleFileSelect]);

  const updateField = useCallback((key:string, value:string) => { setFields(p=>({...p,[key]:value})); }, []);

  const handleGenerate = useCallback(async () => {
    setLoading(true); setError(null);
    try { const d=await cardApi.generateCard(fields); setCardData(d); setCurrentPage(0); setStep('preview'); }
    catch(e:any) { setError(e?.message||'生成失败'); } finally { setLoading(false); }
  }, [fields]);

  const handleMatch = useCallback(async () => {
    if(!cardData) return;
    // Check credits
    if (remainingCredits !== undefined && remainingCredits <= 0) {
      setError('匹配额度不足，请先充值');
      return;
    }
    setLoading(true);
    try {
      setMatchResults(await cardApi.matchCard(cardData.id));
      setStep('matched');
      // Refresh credits after match
      const res = await fetchCredits();
      setRemainingCredits(res.credits);
    } catch(e:any) { setError(e?.message||'匹配失败'); } finally { setLoading(false); }
  }, [cardData, remainingCredits]);

  const handleCopyLink = useCallback(async () => {
    try { await navigator.clipboard.writeText(window.location.href); setCopied(true); setTimeout(()=>setCopied(false),2000); }
    catch { setError('复制失败'); }
  }, []);

  const handleShowQR = useCallback(() => { if(!cardData) return; setQrCodeUrl(cardApi.getQRCodeUrl(cardData.id)); setShowQRModal(true); }, [cardData]);

  const handleReset = useCallback(() => {
    setStep('upload'); setFields({}); setCardData(null); setMatchResults([]);
    setError(null); setSuggestions([]); setRawText(''); setCurrentPage(0);
  }, []);

  useEffect(() => {
    try { cardApi.fetchCommonConnections('current').then(setCommonConnections).catch(()=>{}); } catch {}
  }, []);

  return {
    step, loading, error, fields, suggestions, rawText,
    cardData, setCardData, currentPage, totalPages, matchResults,
    showQRModal, qrCodeUrl, commonConnections, copied,
    remainingCredits, setRemainingCredits,
    fileInputRef,
    handleFileSelect, handleDrop, updateField,
    handleGenerate, handleMatch, handleCopyLink,
    handleShowQR, handleDownloadQR: handleShowQR, handleReset,
    setCurrentPage, setShowQRModal,
  };
}
