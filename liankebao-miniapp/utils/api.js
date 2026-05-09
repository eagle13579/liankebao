const API_BASE = 'https://47.100.160.250/api'

module.exports = {
  get(path) { return request(path) },
  post(path, data) { return request(path, 'POST', data) },
  put(path, data) { return request(path, 'PUT', data) },
  loginWithWechat() {
    return new Promise((resolve, reject) => {
      wx.login({
        success: (res) => {
          if (res.code) {
            request('/auth/wechat-login', 'POST', { code: res.code }).then(data => {
              if (data.code === 200) {
                wx.setStorageSync('token', data.data.token)
                wx.setStorageSync('user', data.data.user)
                resolve(data.data)
              } else reject(data.message)
            })
          } else reject('微信登录失败')
        },
        fail: reject
      })
    })
  }
}

function request(path, method = 'GET', data = null) {
  const token = wx.getStorageSync('token')
  const header = { 'Content-Type': 'application/json' }
  if (token) header['Authorization'] = 'Bearer ' + token
  return new Promise((resolve) => {
    wx.request({
      url: API_BASE + path,
      method,
      data,
      header,
      success: (res) => resolve(res.data),
      fail: (e) => resolve({ code: 500, message: e.errMsg || '网络错误' })
    })
  })
}
