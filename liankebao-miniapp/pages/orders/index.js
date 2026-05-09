var api = require('../../utils/api')

Page({
  data: { orders: [], loading: true },
  onLoad: function() {
    var self = this
    var token = wx.getStorageSync('token')
    if (!token) {
      wx.navigateTo({ url: '/pages/login/index' })
      return
    }
    api.get('/orders').then(function(res) {
      var raw = (res.data && res.data.items) || []
      var items = []
      for (var i = 0; i < raw.length; i++) {
        var o = raw[i]
        var prod = o.product || {}
        items.push({
          id: o.id,
          status: o.status,
          total_price: o.total_price,
          quantity: o.quantity,
          productName: prod.name || '未知产品'
        })
      }
      self.setData({ orders: items, loading: false })
    })
  },
  handleConfirm: function(e) {
    var self = this
    var orderId = e.currentTarget.dataset.id
    api.put('/orders/' + orderId + '/status', { status: 'received' }).then(function(res) {
      if (res.code === 200) {
        wx.showToast({ title: '已确认收货', icon: 'success' })
        self.onLoad()
      }
    })
  }
})
