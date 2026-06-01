import { api } from './client';

// ============================================================
// 链客宝会员模块 API
// ============================================================

/** 会员层级信息（来自后端） */
export interface MembershipTier {
  id: number;
  name: string;
  level: 'free' | 'gold' | 'diamond' | 'board';
  price: number;         // 年费，0表示免费
  trial_price: number;   // 体验价
  对接券_per_month: number;
  commission_rate: number; // 分润比例 e.g. 0.05
  features: string[];
  badge: string;
  sort_order: number;
}

/** 用户当前会员状态 */
export interface MembershipStatus {
  level: 'free' | 'gold' | 'diamond' | 'board';
  level_name: string;
  expired_at: string | null;
  remaining_coupons: number;   // 剩余对接券
  total_coupons_this_month: number;
  trial_used: boolean;         // 是否已使用过体验金卡
  coupon_used_count: number;   // 本月已用对接券次数
}

/** 升级预支付响应 */
export interface UpgradePaymentData {
  order_no: string;
  amount: number;
  pay_params: Record<string, any>;
  expire_seconds: number;
}

/** 升级订单查询 */
export interface UpgradeOrderQuery {
  status: string;  // 'paid' | 'pending' | 'failed' | 'expired'
  paid_at: string | null;
  level: string | null;
}

export const membershipApi = {
  /** 获取所有会员层级配置 */
  getTiers: () =>
    api.get<MembershipTier[]>('/api/v1/membership/tiers'),

  /** 获取当前用户会员状态 */
  getStatus: () =>
    api.get<MembershipStatus>('/api/v1/membership/status'),

  /** 升级会员（创建支付订单） */
  upgrade: (tierId: number, platform: string = 'alipay') =>
    api.post<UpgradePaymentData>('/api/v1/membership/upgrade', {
      tier_id: tierId,
      platform,
    }),

  /** 首月体验金卡 */
  trialGold: (platform: string = 'alipay') =>
    api.post<UpgradePaymentData>('/api/v1/membership/trial', {
      platform,
    }),

  /** 查询升级订单状态 */
  queryOrder: (orderNo: string) =>
    api.get<UpgradeOrderQuery>('/api/v1/membership/order/' + orderNo),

  /** 检查是否需要展示体验弹窗 */
  checkTrialEligibility: () =>
    api.get<{ eligible: boolean; reason?: string }>('/api/v1/membership/trial-eligible'),
};
