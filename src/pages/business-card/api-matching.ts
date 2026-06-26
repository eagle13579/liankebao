/**
 * 链客宝 - 匹配/收藏/评价/计费 API 封装
 * ========================================
 * 调用 /d/链客宝/backend/ 中已实现的 API 端点
 */

const API_BASE = '';

// ── 匹配历史 ──────────────────────────────────────────

export interface MatchHistoryItem {
  id: number;
  title: string;
  description: string | null;
  category: string | null;
  match_score: number;
  match_reasons: string[];
  strategy: string | null;
  matched_at?: string;
  contact_name?: string;
  contacted?: boolean;
  direction: 'need_to_product' | 'product_to_need';
}

export async function fetchMatchHistory(
  needId: number,
  direction: 'need_to_product' | 'product_to_need' = 'need_to_product',
  offset = 0,
  limit = 50,
): Promise<{ items: MatchHistoryItem[]; total: number }> {
  const endpoint =
    direction === 'need_to_product'
      ? `/api/matching/needs/${needId}/products`
      : `/api/matching/products/${needId}/needs`;
  const resp = await fetch(`${API_BASE}${endpoint}?offset=${offset}&limit=${limit}`);
  if (!resp.ok) throw new Error(`匹配历史查询失败: ${resp.status}`);
  const json = await resp.json();
  const items: MatchHistoryItem[] = (json.data?.items || []).map((item: any) => ({
    ...item,
    direction,
    matched_at: new Date().toISOString(),
  }));
  return { items, total: json.data?.total ?? items.length };
}

// ── 收藏（localStorage 实现，TODO: 迁移至 POST /api/favorites 数据库） ──

const FAVORITES_KEY = 'chainke_favorites';

export interface FavoriteItem {
  match_id: number;
  title: string;
  match_score: number;
  saved_at: string;
  direction: string;
  description?: string;
}

export function getFavorites(): FavoriteItem[] {
  try {
    const raw = localStorage.getItem(FAVORITES_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

export function saveToFavorites(item: FavoriteItem): void {
  const list = getFavorites();
  if (list.some((f) => f.match_id === item.match_id)) return;
  list.unshift(item);
  localStorage.setItem(FAVORITES_KEY, JSON.stringify(list));
}

export function removeFromFavorites(matchId: number): void {
  const list = getFavorites().filter((f) => f.match_id !== matchId);
  localStorage.setItem(FAVORITES_KEY, JSON.stringify(list));
}

export function isFavorite(matchId: number): boolean {
  return getFavorites().some((f) => f.match_id === matchId);
}

// ── 评价（localStorage 实现，TODO: 迁移至数据库） ──

const REVIEWS_KEY = 'chainke_reviews';

export interface ReviewData {
  match_id: number;
  title: string;
  accuracy: number; // 1-5
  comment: string;
  created_at: string;
}

export function getReviews(): ReviewData[] {
  try {
    const raw = localStorage.getItem(REVIEWS_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

export function submitReview(review: ReviewData): void {
  const list = getReviews();
  const idx = list.findIndex((r) => r.match_id === review.match_id);
  if (idx >= 0) {
    list[idx] = review;
  } else {
    list.unshift(review);
  }
  localStorage.setItem(REVIEWS_KEY, JSON.stringify(list));
}

export function getReviewForMatch(matchId: number): ReviewData | undefined {
  return getReviews().find((r) => r.match_id === matchId);
}

// ── 计费/额度 ─────────────────────────────────────────

export interface CreditsStatus {
  credits: number;
  tier: string;
}

export async function fetchCredits(): Promise<CreditsStatus> {
  const resp = await fetch(`${API_BASE}/api/membership/credits`);
  if (!resp.ok) throw new Error(`获取额度失败: ${resp.status}`);
  const json = await resp.json();
  return { credits: json.credits ?? 0, tier: json.tier ?? 'free' };
}

export async function fetchMembershipStatus(): Promise<{
  level: string;
  level_name: string;
  expired_at: string | null;
  remaining_coupons: number;
  total_coupons_this_month: number;
  coupon_used_count: number;
}> {
  const resp = await fetch(`${API_BASE}/api/membership/status`);
  if (!resp.ok) throw new Error(`获取会员状态失败: ${resp.status}`);
  return resp.json();
}

// ── 额度消耗历史（localStorage + MatchCreditLog API） ──

const CREDIT_HISTORY_KEY = 'chainke_credit_history';

export interface CreditLogEntry {
  amount: number;
  balance_after: number;
  reason: string;
  related_type?: string;
  related_title?: string;
  created_at: string;
}

export function getCreditHistory(): CreditLogEntry[] {
  try {
    const raw = localStorage.getItem(CREDIT_HISTORY_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

export function addCreditLog(entry: CreditLogEntry): void {
  const list = getCreditHistory();
  list.unshift(entry);
  localStorage.setItem(CREDIT_HISTORY_KEY, JSON.stringify(list));
}

// ── 服务器端评价提交 ──────────────────────────────
// POST /api/recommend/feedback { action: "rate", score, comment }

export async function submitRatingFeedback(params: {
  productId?: number;
  matchId?: number;
  score: number; // 1-5
  comment?: string;
}): Promise<boolean> {
  try {
    const resp = await fetch(`${API_BASE}/api/recommend/feedback`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_id: 0,
        product_id: params.productId ?? params.matchId ?? 0,
        action: 'rate',
        score: params.score,
        source: 'match_card',
        comment: params.comment || '',
      }),
    });
    return resp.ok;
  } catch {
    return false;
  }
}

// ── 用户资料（含 match_credits） ──────────────────────

export interface UserProfile {
  id: number;
  name: string;
  match_credits: number;
  total_credits_this_month?: number;
  tier?: string;
}

export async function fetchUserProfile(): Promise<UserProfile> {
  const resp = await fetch(`${API_BASE}/api/user/profile`);
  if (!resp.ok) throw new Error(`获取用户资料失败: ${resp.status}`);
  const json = await resp.json();
  return {
    id: json.id ?? 0,
    name: json.name ?? '',
    match_credits: json.match_credits ?? json.credits ?? 0,
    total_credits_this_month: json.total_credits_this_month ?? json.match_credits ?? 10,
    tier: json.tier ?? 'free',
  };
}

// ── 联系记录（localStorage） ──

const CONTACT_RECORDS_KEY = 'chainke_contact_records';

export function markContacted(matchId: number): void {
  try {
    const raw = localStorage.getItem(CONTACT_RECORDS_KEY);
    const list: number[] = raw ? JSON.parse(raw) : [];
    if (!list.includes(matchId)) {
      list.push(matchId);
      localStorage.setItem(CONTACT_RECORDS_KEY, JSON.stringify(list));
    }
  } catch {
    // ignore
  }
}

export function isContacted(matchId: number): boolean {
  try {
    const raw = localStorage.getItem(CONTACT_RECORDS_KEY);
    const list: number[] = raw ? JSON.parse(raw) : [];
    return list.includes(matchId);
  } catch {
    return false;
  }
}
