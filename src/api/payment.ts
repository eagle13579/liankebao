import { api } from './client';

export interface UnifiedOrderResponse {
  prepay_id: string;
  nonce_str: string;
  sign: string;
  timestamp: string;
  package_val: string;
}

export interface OrderQueryResponse {
  status: string;
  transaction_id: string;
}

export interface PaymentConfigResponse {
  platforms: string[];
  wxpay_configured: boolean;
  alipay_configured: boolean;
}

export const paymentApi = {
  /** 统一下单 - 获取微信支付参数 */
  unifiedOrder: (orderNo: string, description: string = '商品订单', platform: string = 'wxpay') =>
    api.post<UnifiedOrderResponse>('/api/payment/wxpay/unified-order', {
      order_no: orderNo,
      platform,
      description,
    }),

  /** 查询订单支付状态 */
  queryOrder: (orderNo: string) =>
    api.get<OrderQueryResponse>('/api/payment/wxpay/query/' + orderNo),

  /** 获取支付配置信息 */
  getConfig: () =>
    api.get<PaymentConfigResponse>('/api/payment/config'),
};
