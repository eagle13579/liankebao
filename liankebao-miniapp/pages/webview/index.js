Page({
  data: {
    url: ''
  },
  onLoad: function(options) {
    if (options.url) {
      this.setData({ url: decodeURIComponent(options.url) })
    } else {
      wx.showToast({ title: '链接错误', icon: 'none' })
      setTimeout(function() { wx.navigateBack() }, 1500)
    }
  },
  onWebMessage: function(e) {
    // 接收webview消息
  },
  onWebLoad: function() {
    // webview加载完成
  },
  onWebError: function() {
    wx.showToast({ title: '页面加载失败', icon: 'none' })
  }
})
