/**
 * AI数字名片 - API对接层
 * 后端DigitalBrochure API (:8003)
 * 复用 liankebao-weapp api/client.ts 的基础设施
 */

import { api } from './client'

// ===== 认证相关 =====
export const authApi = {
  /** 微信code登录 */
  wxLogin: (code: string) => api.post('/auth/wechat-login', { code }),

  /** 发送短信验证码 */
  smsCode: (phone: string) => api.post('/auth/sms-code', { phone }),

  /** 验证码登录 */
  smsLogin: (phone: string, code: string) => api.post('/auth/sms-login', { phone, code }),
}

// ===== 画册相关 =====
export const brochureApi = {
  /** 获取自己的画册 */
  getMine: () => api.get('/v1/brochures/mine'),

  /** 获取分享画册数据 */
  getShare: (shareToken: string) => api.get(`/brochures/share/${shareToken}`),

  /** 获取画册列表 */
  getList: (params?: any) => api.post('/brochures/list', params || {}),

  /** 创建画册 */
  create: (data: any) => api.post('/brochures', data),

  /** 更新画册 */
  update: (id: string, data: any) => api.put(`/brochures/${id}`, data),

  /** 发布画册 */
  publish: (id: string) => api.post(`/brochures/${id}/publish`, {}),

  /** 上传图片 */
  upload: (filePath: string) => {
    // 使用Taro.uploadFile处理文件上传
    const Taro = require('@tarojs/taro').default
    return new Promise((resolve, reject) => {
      Taro.uploadFile({
        url: `/miniapp-api/api/brochures/upload`,
        filePath,
        name: 'file',
        success: (res: any) => {
          try {
            resolve(JSON.parse(res.data))
          } catch {
            resolve(res.data)
          }
        },
        fail: reject,
      })
    })
  },

  /** AI OCR提取名片字段 */
  aiExtract: (fileId: string, purpose?: string) =>
    api.post('/brochures/ai-extract', { file_id: fileId, purpose }),
}

// ===== 匹配相关 =====
export const matchApi = {
  /** 获取供需匹配结果 */
  getMatches: (params?: { page?: number; purpose?: string }) =>
    api.post('/v1/match/engine', params || {}),

  /** 付费解锁联系方式 */
  unlock: (matchUserId: string) =>
    api.post('/v1/match/unlock', { match_user_id: matchUserId }),
}

// ===== 用户相关 =====
export const userApi = {
  /** 获取当前用户信息 */
  getMe: () => api.get('/v1/users/me'),

  /** 获取数据看板统计 */
  getStats: () => api.get('/v1/users/stats'),

  /** 获取最近访客 */
  getVisitors: () => api.get('/v1/users/visitors'),
}

// ===== 会员相关 =====
export const membershipApi = {
  /** 获取会员订阅方案 */
  getPlans: () => api.get('/v1/membership/plans'),

  /** 订阅会员/购买解锁 */
  subscribe: (planId: string) =>
    api.post('/v1/membership/subscribe', { plan_id: planId }),
}

// ===== 支付相关 =====
export const paymentApi = {
  /** 微信支付下单 */
  wxPay: (orderInfo: { amount: number; description: string; order_type: string }) =>
    api.post('/v1/payment/wx-pay', orderInfo),
}
