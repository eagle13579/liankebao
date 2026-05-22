var api = require('../../utils/api')

var STATUS_TABS = [
  { key: 'all', label: '全部' },
  { key: 'pending', label: '待付款' },
  { key: 'paid', label: '已付款' },
  { key: 'shipped', label: '已发货' },
  { key: 'completed', label: '已完成' }
]

var STATUS_MAP = {
  pending: '待付款',
  paid: '已付款',
  shipped: '已发货',
  completed: '已完成',
  cancelled: '已取消'
}

Page({
  data: {
    orders: [],
    loading: true,
    statusTabs: STATUS_TABS,
    currentTab: 'all'
  },
  onLoad: function() {
    var token = wx.getStorageSync('token')
    if (!token) {
      wx.navigateTo({ url: '/pages/login/index' })
      return
    }
    this.loadOrders()
  },
  loadOrders: function() {
    var self = this
    self.setData({ loading: true })
    api.get('/orders').then(function(res) {
      var raw = (res.data && res.data.items) || []
      var items = []
      for (var i = 0; i < raw.length; i++) {
        var o = raw[i]
        var prod = o.product || {}
        items.push({
          id: o.id,
          order_no: o.order_no || o.id,
          status: o.status,
          statusText: STATUS_MAP[o.status] || o.status,
          total_price: o.total_price,
          quantity: o.quantity,
          productName: prod.name || '未知产品',
          created_at: o.created_at || o.create_time || '',
          images: prod.images || ''
        })
      }
      self.setData({ allOrders: items, loading: false })
      self.filterOrders()
    })
  },
  filterOrders: function() {
    var self = this
    var tab = self.data.currentTab
    var all = self.data.allOrders || []
    var filtered = tab === 'all' ? all : all.filter(function(o) { return o.status === tab })
    self.setData({ orders: filtered })
  },
  switchTab: function(e) {
    var tab = e.currentTarget.dataset.tab
    this.setData({ currentTab: tab })
    this.filterOrders()
  },
  handlePay: function(e) {
    var self = this
    var orderId = e.currentTarget.dataset.id
    wx.showLoading({ title: '支付处理中...' })
    // 1. 调后端获取微信支付参数
    api.post('/orders/' + orderId + '/pay').then(function(res) {
      wx.hideLoading()
      if (res.code === 200 && res.data) {
        var payParams = res.data
        // 2. 调起微信支付
        wx.requestPayment({
          timeStamp: payParams.timeStamp,
          nonceStr: payParams.nonceStr,
          package: payParams.package,
          signType: payParams.signType || 'MD5',
          paySign: payParams.paySign,
          success: function() {
            wx.showToast({ title: '支付成功', icon: 'success' })
            self.loadOrders()
          },
          fail: function(err) {
            wx.showToast({ title: '支付失败或已取消', icon: 'none' })
          }
        })
      } else {
        wx.showToast({ title: res.message || '获取支付参数失败', icon: 'none' })
      }
    }).catch(function() {
      wx.hideLoading()
      wx.showToast({ title: '网络异常，请重试', icon: 'none' })
    })
  },
  handleShip: function(e) {
    var self = this
    var orderId = e.currentTarget.dataset.id
    wx.showLoading({ title: '处理中...' })
    api.put('/orders/' + orderId + '/status', { status: 'shipped' }).then(function(res) {
      wx.hideLoading()
      if (res.code === 200) {
        wx.showToast({ title: '已发货', icon: 'success' })
        self.loadOrders()
      } else {
        wx.showToast({ title: res.message || '操作失败', icon: 'none' })
      }
    })
  },
  handleConfirm: function(e) {
    var self = this
    var orderId = e.currentTarget.dataset.id
    wx.showLoading({ title: '处理中...' })
    api.put('/orders/' + orderId + '/status', { status: 'completed' }).then(function(res) {
      wx.hideLoading()
      if (res.code === 200) {
        wx.showToast({ title: '已确认收货', icon: 'success' })
        self.loadOrders()
      } else {
        wx.showToast({ title: res.message || '操作失败', icon: 'none' })
      }
    })
  },
  handleCancel: function(e) {
    var self = this
    var orderId = e.currentTarget.dataset.id
    wx.showModal({
      title: '提示',
      content: '确定取消该订单？',
      success: function(res) {
        if (res.confirm) {
          api.put('/orders/' + orderId + '/status', { status: 'cancelled' }).then(function(res) {
            if (res.code === 200) {
              wx.showToast({ title: '已取消', icon: 'success' })
              self.loadOrders()
            } else {
              wx.showToast({ title: res.message || '操作失败', icon: 'none' })
            }
          })
        }
      }
    })
  }
})
