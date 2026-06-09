// 链客宝AI 登录状态管理

var api = require('./api')

// 检查登录状态
function checkLogin() {
  var token = wx.getStorageSync('token')
  var user = wx.getStorageSync('user')
  return !!(token && user)
}

// 获取当前用户
function getCurrentUser() {
  return wx.getStorageSync('user') || null
}

// 微信一键登录
function wxLogin() {
  return new Promise(function(resolve, reject) {
    // 用 setTimeout 兜底：5秒内 wx.login 没返回就切离线模式
    var timeoutTimer = setTimeout(function() {
      console.warn('[auth] wx.login timeout, switching to offline mode')
      var offlineUser = { name: '访客', company: '', token: 'offline_' + Date.now() }
      wx.setStorageSync('token', offlineUser.token)
      wx.setStorageSync('user', offlineUser)
      resolve(offlineUser)
    }, 5000)

    wx.login({
      success: function(loginRes) {
        clearTimeout(timeoutTimer)
        if (!loginRes.code) {
          reject('获取微信code失败')
          return
        }
        // 后端 wx-mini-login 有 mock 降级
        api.wxMiniLogin(loginRes.code, {}).then(function(res) {
          if (res && res.access_token) {
            wx.setStorageSync('token', res.access_token)
            wx.setStorageSync('user', res.user || {})
            resolve(res)
          } else if (res && res.data && res.data.access_token) {
            wx.setStorageSync('token', res.data.access_token)
            wx.setStorageSync('user', res.data.user || res.data)
            resolve(res.data)
          } else {
            // 仍然失败时创建离线会话（不阻塞用户体验）
            var offlineUser = { name: '用户', company: '', token: 'offline_' + Date.now() }
            wx.setStorageSync('token', offlineUser.token)
            wx.setStorageSync('user', offlineUser)
            resolve(offlineUser)
          }
        }).catch(function() {
          // 后端不可达时，创建离线会话，不阻塞
          var offlineUser = { name: '访客', company: '', token: 'offline_' + Date.now() }
          wx.setStorageSync('token', offlineUser.token)
          wx.setStorageSync('user', offlineUser)
          resolve(offlineUser)
        })
      },
      fail: function() {
        clearTimeout(timeoutTimer)
        console.warn('[auth] wx.login failed, switching to offline mode')
        var offlineUser = { name: '访客', company: '', token: 'offline_' + Date.now() }
        wx.setStorageSync('token', offlineUser.token)
        wx.setStorageSync('user', offlineUser)
        resolve(offlineUser)
      }
    })
  })
}
function logout() {
  wx.removeStorageSync('token')
  wx.removeStorageSync('user')
  wx.reLaunch({ url: '/pages/login/index' })
}

module.exports = {
  checkLogin: checkLogin,
  getCurrentUser: getCurrentUser,
  wxLogin: wxLogin,
  logout: logout
}
