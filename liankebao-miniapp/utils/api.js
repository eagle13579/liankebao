// 链客宝小程序 API 请求封装 v2.0
// 同步网页版 /api/v1/ 版本

var BASE_URL = 'https://www.go-aiport.com/lkapi'

function request(path, method, data) {
  if (!method) method = 'GET'
  var token = wx.getStorageSync('token')
  var header = { 'Content-Type': 'application/json' }
  if (token) header['Authorization'] = 'Bearer ' + token
  return new Promise(function(resolve, reject) {
    wx.request({
      url: BASE_URL + path,
      method: method,
      data: data,
      header: header,
      success: function(res) {
        if (res.statusCode === 401) {
          wx.removeStorageSync('token')
          wx.removeStorageSync('user')
          wx.redirectTo({ url: '/pages/login/index' })
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
  login: function(path, data) { return request(path, 'POST', data) }
}
