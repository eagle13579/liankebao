var API_BASE = 'https://www.go-aiport.com/lkapi'

function request(path, method, data) {
  if (!method) method = 'GET'
  var token = wx.getStorageSync('token')
  var header = { 'Content-Type': 'application/json' }
  if (token) header['Authorization'] = 'Bearer ' + token
  return new Promise(function(resolve) {
    wx.request({
      url: API_BASE + path,
      method: method,
      data: data,
      header: header,
      success: function(res) { resolve(res.data) },
      fail: function(e) { resolve({ code: 500, message: e.errMsg || '网络错误' }) }
    })
  })
}

module.exports = {
  get: function(path) { return request(path) },
  post: function(path, data) { return request(path, 'POST', data) },
  put: function(path, data) { return request(path, 'PUT', data) },
  del: function(path, data) { return request(path, 'DELETE', data) },
  loginWithWechat: function() {
    return new Promise(function(resolve, reject) {
      wx.login({
        success: function(res) {
          if (res.code) {
            request('/auth/wechat-login', 'POST', { code: res.code }).then(function(data) {
              if (data.code === 200) {
                wx.setStorageSync('token', data.data.token)
                wx.setStorageSync('user', data.data.user)
                resolve(data.data)
              } else {
                reject(data.message)
              }
            })
          } else {
            reject('微信登录失败')
          }
        },
        fail: function(e) { reject(e) }
      })
    })
  }
}
