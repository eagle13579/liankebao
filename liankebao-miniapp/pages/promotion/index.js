var api = require('../../utils/api')

Page({
  data: {
    stats: null,
    products: [],
    withdrawals: [],
    loading: true,
    tabActive: 'stats'
  },
  onLoad: function() {
    var token = wx.getStorageSync('token')
    var user = wx.getStorageSync('user')
    if (!token) {
      wx.navigateTo({ url: '/pages/login/index' })
      return
    }
    if (!user || user.role !== 'promoter') {
      wx.showToast({ title: '仅推广员可访问', icon: 'none' })
      setTimeout(function() { wx.navigateBack() }, 1500)
      return
    }
    this.loadData()
  },
  loadData: function() {
    var self = this
    self.setData({ loading: true })

    // 加载统计数据（后端路由: /api/promoter/earnings）
    api.get('/promoter/earnings').then(function(res) {
      if (res.code === 200) {
        var d = res.data || {}
        self.setData({
          stats: {
            total_earnings: d.total_earnings || 0,
            balance: d.available || 0,
            withdrawn: d.withdrawn || 0,
            pending: d.pending || 0,
            order_count: d.order_count || 0
          }
        })
      }
    })

    // 加载可推广产品（后端路由: /api/products）
    api.get('/products').then(function(res) {
      var raw = (res.data && res.data.items) || []
      var items = []
      for (var i = 0; i < raw.length; i++) {
        var p = raw[i]
        items.push({
          id: p.id,
          name: p.name,
          price: p.price,
          earn_per_share: p.earn_per_share || 0,
          images: p.images,
          firstImage: (function(arr){ try { return JSON.parse(arr||'[]')[0]||'' } catch(e) { return '' } })(p.images)
        })
      }
      self.setData({ products: items })
    })

    // 加载提现记录（后端路由: /api/promoter/withdrawals）
    api.get('/promoter/withdrawals').then(function(res) {
      var raw = (res.data && res.data.items) || []
      self.setData({ withdrawals: raw, loading: false })
    })
  },
  switchTab: function(e) {
    var tab = e.currentTarget.dataset.tab
    this.setData({ tabActive: tab })
  },
  goProduct: function(e) {
    wx.navigateTo({ url: '/pages/product/index?id=' + e.currentTarget.dataset.id })
  },
  shareProduct: function(e) {
    var id = e.currentTarget.dataset.id
    var name = e.currentTarget.dataset.name
    var path = '/pages/product/index?id=' + id
    // 生成推广链接（带推广员ID）
    var user = wx.getStorageSync('user')
    if (user && user.id) {
      path = path + '&promoter=' + user.id
    }
    wx.showShareMenu({
      withShareTicket: true
    })
    // 生成小程序码
    wx.showLoading({ title: '生成分享码...' })
    api.get('/promoter/qrcode?product_id=' + id).then(function(res) {
      wx.hideLoading()
      if (res.code === 200 && res.data && res.data.qrcode) {
        wx.showActionSheet({
          itemList: ['保存二维码', '复制推广链接'],
          success: function(resp) {
            if (resp.tapIndex === 0) {
              wx.downloadFile({
                url: res.data.qrcode,
                success: function(downloadRes) {
                  wx.saveImageToPhotosAlbum({
                    filePath: downloadRes.tempFilePath,
                    success: function() { wx.showToast({ title: '已保存', icon: 'success' }) },
                    fail: function() { wx.showToast({ title: '保存失败', icon: 'none' }) }
                  })
                }
              })
            } else {
              wx.setClipboardData({
                data: 'https://www.go-aiport.com/lkapi/share?product=' + id,
                success: function() { wx.showToast({ title: '链接已复制', icon: 'success' }) }
              })
            }
          }
        })
      } else {
        // 降级：直接复制链接
        wx.setClipboardData({
          data: 'https://www.go-aiport.com/lkapi/share?product=' + id,
          success: function() { wx.showToast({ title: '推广链接已复制', icon: 'success' }) }
        })
      }
    })
  },
  goWithdraw: function() {
    var self = this
    var stats = self.data.stats
    var amount = stats && stats.balance ? stats.balance : 0
    if (amount <= 0) {
      wx.showToast({ title: '无可提现金额', icon: 'none' })
      return
    }
    wx.showModal({
      title: '提现',
      content: '可提现金额: ¥' + amount.toFixed(2) + '\n确认提现到微信零钱？',
      success: function(res) {
        if (res.confirm) {
          wx.showLoading({ title: '提现中...' })
          api.post('/promoter/withdraw', { amount: amount }).then(function(res) {
            wx.hideLoading()
            if (res.code === 200) {
              wx.showToast({ title: '提现申请已提交', icon: 'success' })
              self.loadData()
            } else {
              wx.showToast({ title: res.message || '提现失败', icon: 'none' })
            }
          })
        }
      }
    })
  }
})
