/**
 * 链客宝小程序 - API请求封装 v3.0
 * 统一后端地址: https://liankebao.top/lkapi
 * 本地开发地址: http://localhost:8001
 */

const PROD_BASE_URL = 'https://liankebao.top/lkapi'
const LOCAL_BASE_URL = 'http://localhost:8001'

// 设置为 true 使用本地开发 API
const USE_LOCAL_API = true
const BASE_URL = USE_LOCAL_API ? LOCAL_BASE_URL : PROD_BASE_URL

/**
 * 通用请求封装
 */
function request(path, method, data) {
  if (!method) method = 'GET'
  return new Promise((resolve, reject) => {
    wx.request({
      url: BASE_URL + path,
      method: method,
      timeout: 10000,
      data: data,
      header: { 'Content-Type': 'application/json' },
      success: (res) => {
        if (res.statusCode === 200) {
          resolve(res.data)
        } else {
          reject({ code: res.statusCode, msg: res.errMsg || '请求失败' })
        }
      },
      fail: (err) => {
        reject({ code: -1, msg: err.errMsg || '网络异常' })
      }
    })
  })
}

/** 获取自己的画册数据（生产环境） */
function getMyBrochures(userId) {
  return request('/api/brochures/' + userId)
}

/** 通过分享令牌获取名片（生产环境） */
function getSharedBrochure(token) {
  return request('/api/brochure/t/' + token)
}

/* ========== 本地开发 API (http://localhost:8001) ========== */

/** 获取名片列表 */
function getCards() {
  return request('/api/business-card/cards')
}

/** 通过分享令牌获取画册/名片 */
function getBrochure(token) {
  return request('/api/brochure/' + token)
}

/** 获取微信用户信息（头像、昵称） */
function getWxUserProfile() {
  return new Promise((resolve, reject) => {
    wx.getUserProfile({
      desc: '用于展示您的头像和昵称',
      lang: 'zh_CN',
      success: (res) => {
        const { nickName, avatarUrl } = res.userInfo
        resolve({ nickName, avatarUrl })
      },
      fail: () => reject({ code: -1, msg: '用户拒绝授权' })
    })
  })
}

/** 获取微信手机号 */
function getWxPhoneNumber(e) {
  return new Promise((resolve, reject) => {
    if (e.detail.errMsg && e.detail.errMsg.indexOf('fail') !== -1) {
      reject({ code: -1, msg: '用户拒绝授权手机号' })
      return
    }
    const { encryptedData, iv } = e.detail
    wx.login({
      success: (loginRes) => {
        if (loginRes.code) {
          resolve({ encryptedData, iv, code: loginRes.code })
        } else {
          reject({ code: -1, msg: '登录code获取失败' })
        }
      },
      fail: () => reject({ code: -1, msg: 'wx.login失败' })
    })
  })
}

/** 创建AI数字名片 */
function createCard(params) {
  return request('/api/card/generate', 'POST', {
    nickName: params.nickName,
    avatarUrl: params.avatarUrl,
    encryptedData: params.encryptedData,
    iv: params.iv,
    code: params.code,
    company: params.company,
    position: params.position
  })
}

module.exports = {
  request,
  get: (p) => request(p, 'GET'),
  post: (p, d) => request(p, 'POST', d),
  put: (p, d) => request(p, 'PUT', d),
  del: (p) => request(p, 'DELETE'),
  login: (p, d) => request(p, 'POST', d),
  getMyBrochures,
  getSharedBrochure,
  getWxUserProfile,
  getWxPhoneNumber,
  createCard,
  // 本地开发 API
  getCards,
  getBrochure
}
