import { api } from './client';

export interface RechargeBalanceResponse {
  balance: number;
  total_recharged: number;
  total_consumed: number;
  recent_logs: Array<{
    id: number;
    amount: number;
    type: string;       // 'recharge' | 'consume'
    description: string;
    created_at: string;
  }>;
}

export interface RechargePrecreateResponse {
  order_no: string;
  prepay_id: string;
  pay_params: Record<string, any>;
}

export interface RechargeOrderQueryResponse {
  status: string;   // 'paid' | 'pending' | 'failed' | 'expired'
  paid_at: string | null;
}

export interface RechargeItem {
  id: number;
  order_no: string;
  amount: number;
  platform: string;     // 'wxpay' | 'alipay'
  status: string;       // 'paid' | 'pending' | 'failed' | 'expired'
  created_at: string;
  paid_at: string | null;
}

export interface RechargeListResponse {
  items: RechargeItem[];
  total: number;
  page: number;
  limit: number;
}

/** 获取充值相关余额信息 */
export function getRechargeBalance(): Promise<{ code: number; message: string; data?: RechargeBalanceResponse }> {
  return api.get<RechargeBalanceResponse>('/api/recharge/balance');
}

/** 创建充值预支付订单 */
export function createRechargePrecreate(amount: number, platform: string): Promise<{ code: number; message: string; data?: RechargePrecreateResponse }> {
  return api.post<RechargePrecreateResponse>('/api/recharge/precreate', { amount, platform });
}

/** 查询充值订单状态 */
export function queryRechargeOrder(order_no: string): Promise<{ code: number; message: string; data?: RechargeOrderQueryResponse }> {
  return api.get<RechargeOrderQueryResponse>('/api/recharge/query/' + order_no);
}

/** 获取充值记录列表 */
export function getRechargeList(page: number = 1, limit: number = 20): Promise<{ code: number; message: string; data?: RechargeListResponse }> {
  return api.get<RechargeListResponse>('/api/recharge/list?page=' + page + '&limit=' + limit);
}

/** 获取余额变动明细 */
export function getBalanceLogs(page: number = 1, limit: number = 20): Promise<{ code: number; message: string; data?: { items: RechargeBalanceResponse['recent_logs']; total: number; page: number; limit: number } }> {
  return api.get<{ items: RechargeBalanceResponse['recent_logs']; total: number; page: number; limit: number }>(
    '/api/recharge/balance-logs?page=' + page + '&limit=' + limit
  );
}
