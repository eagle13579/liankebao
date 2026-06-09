// 链客宝AI AI数字名片 API 请求封装 v3.0
// 对接后端 :8003

var BASE_URL = 'https://liankebao.top'
var API_PREFIX = '/api/v1'

function apiUrl(path) {
  // 兼容旧路径: 如果已经是 /api/v1/ 开头就不加前缀
  if (path.startsWith('/api/v1/')) return BASE_URL + path
  return BASE_URL + API_PREFIX + path
}

function request(path, method, data) {
  if (!method) method = 'GET'
  var token = wx.getStorageSync('token')
  var header = { 'Content-Type': 'application/json' }
  if (token) header['Authorization'] = 'Bearer ' + token
  return new Promise(function(resolve, reject) {
    wx.request({
      url: apiUrl(path),
      method: method,
      data: data,
      header: header,
      timeout: 5000,  // 5秒超时，避免卡住
      success: function(res) {
        if (res.statusCode === 401) {
          wx.removeStorageSync('token')
          wx.removeStorageSync('user')
          wx.reLaunch({ url: '/pages/login/index' })
          reject({ code: 401, message: '未授权' })
          return
        }
        resolve(res.data)
      },
      fail: function(e) {
        reject({ code: 500, message: e.errMsg || '网络错误' })
      }
    })
  })
}

module.exports = {
  request: request,
  BASE_URL: BASE_URL,
  get: function(path) { return request(path, 'GET') },
  post: function(path, data) { return request(path, 'POST', data) },
  put: function(path, data) { return request(path, 'PUT', data) },
  del: function(path) { return request(path, 'DELETE') },

  // === 认证相关 ===
  // 微信小程序登录
  wxMiniLogin: function(code, userInfo) {
    return request('/api/auth/wx-mini-login', 'POST', { code: code, userInfo: userInfo })
  },
  // 手机号登录
  phoneLogin: function(phone, code) {
    return request('/api/auth/login', 'POST', { phone: phone, code: code })
  },

  // === 画册相关 ===
  // 创建画册
  createBrochure: function(data) {
    return request('/api/brochures', 'POST', data)
  },
  // 获取我的画册列表
  getMyBrochures: function() {
    return request('/api/brochures', 'GET')
  },
  // 获取公开画册 (通过share_token)
  getSharedBrochure: function(shareToken) {
    return request('/api/brochures/share/' + shareToken, 'GET')
  },
  // 上传图片
  uploadImage: function(filePath) {
    var token = wx.getStorageSync('token')
    return new Promise(function(resolve, reject) {
      wx.uploadFile({
        url: apiUrl('/api/brochures/upload'),
        filePath: filePath,
        name: 'file',
        header: { 'Authorization': 'Bearer ' + token },
        success: function(res) {
          try {
            resolve(JSON.parse(res.data))
          } catch(e) {
            resolve(res.data)
          }
        },
        fail: reject
      })
    })
  },

  // === 标签相关 ===
  addTags: function(tags) {
    return request('/api/tags/me', 'POST', tags)
  },

  // === 匹配相关 ===
  matchEngine: function(params) {
    return request('/api/match/engine', 'POST', params)
  },
  getMatchRecords: function() {
    return request('/api/match/records', 'GET')
  },
  unlockContact: function(matchId) {
    return request('/api/match/' + matchId + '/unlock', 'POST')
  },

  // === 用户相关 ===
  getUserInfo: function() {
    return request('/api/users/me', 'GET')
  }
}
