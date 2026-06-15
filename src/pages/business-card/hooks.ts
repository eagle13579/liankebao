import { useState, useRef, useEffect, useCallback } from 'react';
import type { CardFields, CardData, MatchItem, Step } from './types';
import * as cardApi from './api';
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
  const fileInputRef = useRef<HTMLInputElement>(null);
  const totalPages = cardData?.album_pages?.length || 0;
  const handleFileSelect = useCallback(async (file: File) => {
    setLoading(true); setError(null);
    try { const r = await cardApi.scanCard(file); setSuggestions(r.suggestions||[]); setRawText(r.raw_text||''); setFields(r.fields||{}); setStep('review'); }
    catch(e:any) { setError(e?.message||'\u626b\u63cf\u5931\u8d25'); } finally { setLoading(false); }
  }, []);
  const handleDrop = useCallback((e: React.DragEvent) => { e.preventDefault(); const f=e.dataTransfer.files[0]; if(f) handleFileSelect(f); }, [handleFileSelect]);
  const updateField = useCallback((key:string, value:string) => { setFields(p=>({...p,[key]:value})); }, []);
  const handleGenerate = useCallback(async () => {
    setLoading(true); setError(null);
    try { const d=await cardApi.generateCard(fields); setCardData(d); setCurrentPage(0); setStep('preview'); }
    catch(e:any) { setError(e?.message||'\u751f\u6210\u5931\u8d25'); } finally { setLoading(false); }
  }, [fields]);
  const handleMatch = useCallback(async () => {
    if(!cardData) return; setLoading(true);
    try { setMatchResults(await cardApi.matchCard(cardData.id)); setStep('matched'); }
    catch(e:any) { setError(e?.message||'\u5339\u914d\u5931\u8d25'); } finally { setLoading(false); }
  }, [cardData]);
  const handleCopyLink = useCallback(async () => {
    try { await navigator.clipboard.writeText(window.location.href); setCopied(true); setTimeout(()=>setCopied(false),2000); }
    catch { setError('\u590d\u5236\u5931\u8d25'); }
  }, []);
  const handleShowQR = useCallback(() => { if(!cardData) return; setQrCodeUrl(cardApi.getQRCodeUrl(cardData.id)); setShowQRModal(true); }, [cardData]);
  const handleReset = useCallback(() => { setStep('upload'); setFields({}); setCardData(null); setMatchResults([]); setError(null); setSuggestions([]); setRawText(''); setCurrentPage(0); }, []);
  useEffect(() => { try { cardApi.fetchCommonConnections('current').then(setCommonConnections).catch(()=>{}); } catch {} }, []);
  return { step,loading,error,fields,suggestions,rawText,cardData,setCardData,currentPage,totalPages,matchResults,showQRModal,qrCodeUrl,commonConnections,copied,fileInputRef,handleFileSelect,handleDrop,updateField,handleGenerate,handleMatch,handleCopyLink,handleShowQR,handleReset,setCurrentPage,setShowQRModal };
}
