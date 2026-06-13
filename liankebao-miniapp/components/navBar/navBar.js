// components/navBar/navBar.js
Component({
  properties: {
    title: { type: String, value: 'AI数字名片' },
    showBack: { type: Boolean, value: false },
    showShare: { type: Boolean, value: false },
    bgTransparent: { type: Boolean, value: false }
  },
  data: {
    statusBarHeight: 0,
    navBarHeight: 0
  },
  lifetimes: {
    attached: function() {
      var sysInfo = wx.getSystemInfoSync()
      var statusBarHeight = sysInfo.statusBarHeight
      // 胶囊按钮位置信息
      var menuButton = wx.getMenuButtonBoundingClientRect()
      var navBarHeight = menuButton.bottom + 8
      this.setData({
        statusBarHeight: statusBarHeight,
        navBarHeight: navBarHeight
      })
    }
  },
  methods: {
    onBack: function() {
      wx.navigateBack({ delta: 1 })
    },
    onShare: function() {
      this.triggerEvent('share')
    }
  }
})
