import { api } from './client';

/** 微信V3 JSAPI 支付参数（与微信官方规范一致） */
export interface PaymentParams {
  appId: string;
  timeStamp: string;
  nonceStr: string;
  /** 值为 "prepay_id=xxx" */
  package: string;
  signType: string;
  paySign: string;
  _mode?: string;
}

/** 统一下单返回值结构 */
export interface UnifiedOrderData {
  order: Record<string, any>;
  payment: PaymentParams;
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
  /** 统一下单 - 获取微信V3 JSAPI支付参数 */
  unifiedOrder: (orderId: number, description?: string) =>
    api.post<UnifiedOrderData>('/api/payment/wxpay/unified-order', {
      order_id: orderId,
    }),

  /** 查询订单支付状态 */
  queryOrder: (orderNo: string) =>
    api.get<OrderQueryResponse>('/api/payment/wxpay/query/' + orderNo),

  /** 获取支付配置信息 */
  getConfig: () =>
    api.get<PaymentConfigResponse>('/api/payment/config'),
};
