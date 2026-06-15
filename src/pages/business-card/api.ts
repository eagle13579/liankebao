import { api } from '../../api/client';
import type { CardFields, CardData, MatchItem } from './types';
export async function scanCard(file: File): Promise<{raw_text:string;fields:CardFields;suggestions:string[]}> {
  const form = new FormData(); form.append("file", file);
  const res = await api.post('/api/brochure/scan', form);
  return res.data;
}
export async function generateCard(fields: CardFields): Promise<CardData> {
  const res = await api.post('/api/brochure/generate', fields);
  return res.data;
}
export async function matchCard(cardId: number): Promise<MatchItem[]> {
  const res = await api.post('/api/brochure/match', {card_id: cardId});
  return res.data?.matches || [];
}
export function getQRCodeUrl(cardId: number, download?: boolean): string {
  return '/api/brochure/' + cardId + '/qrcode' + (download ? '?download=1' : '');
}
export async function fetchCommonConnections(brochureUserId: string): Promise<{count:number;names:string[]}> {
  const res = await api.get('/api/brochure/' + brochureUserId + '/connections');
  return res.data || {count: 0, names: []};
}
