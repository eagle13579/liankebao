/**
 * 链客宝小程序 - 微信API请求封装
 */

// 基础URL（开发环境使用localhost，生产环境替换为实际域名）
const BASE_URL = 'https://api.liankebao.top'

/**
 * 通用请求封装
 */
function request(url, method = 'GET', data = {}, header = {}) {
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${BASE_URL}${url}`,
      method,
      data,
      header: {
        'Content-Type': 'application/json',
        ...header
      },
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

/**
 * 获取微信用户信息（头像、昵称）
 * 调用 wx.getUserProfile 弹出授权窗口
 * @returns {Promise<{nickName: string, avatarUrl: string}>}
 */
function getWxUserProfile() {
  return new Promise((resolve, reject) => {
    wx.getUserProfile({
      desc: '用于展示您的头像和昵称',
      lang: 'zh_CN',
      success: (res) => {
        const { nickName, avatarUrl } = res.userInfo
        resolve({ nickName, avatarUrl })
      },
      fail: (err) => {
        reject({ code: -1, msg: '用户拒绝授权' })
      }
    })
  })
}

/**
 * 获取微信手机号
 * @param {Object} e - 微信手机号获取事件对象（从button的bindgetphonenumber回调获取）
 * @returns {Promise<{encryptedData: string, iv: string, code: string}>}
 */
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
          resolve({
            encryptedData,
            iv,
            code: loginRes.code
          })
        } else {
          reject({ code: -1, msg: '登录code获取失败' })
        }
      },
      fail: () => {
        reject({ code: -1, msg: 'wx.login失败' })
      }
    })
  })
}

/**
 * 创建AI数字名片
 * @param {Object} params
 * @param {string} params.nickName  - 微信昵称
 * @param {string} params.avatarUrl - 微信头像URL
 * @param {string} params.encryptedData - 手机号加密数据
 * @param {string} params.iv - 加密向量
 * @param {string} params.code - wx.login得到的临时code
 * @param {string} params.company - 公司名称
 * @param {string} params.position - 职位
 * @returns {Promise<{cardId: string, previewUrl: string}>}
 */
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
  getWxUserProfile,
  getWxPhoneNumber,
  createCard
}
