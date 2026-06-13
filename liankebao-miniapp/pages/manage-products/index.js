var api = require('../../utils/api')

function safeGetImage(images) {
  try {
    var arr = JSON.parse(images || '[]')
    return arr[0] || ''
  } catch (e) {
    return ''
  }
}

Page({
  data: {
    products: [],
    loading: true
  },
  onLoad: function() {
    var token = wx.getStorageSync('token')
    var user = wx.getStorageSync('user')
    if (!token) {
      wx.navigateTo({ url: '/pages/login/index' })
      return
    }
    if (!user || user.role !== 'supplier') {
      wx.showToast({ title: '仅产品方可访问', icon: 'none' })
      setTimeout(function() { wx.navigateBack() }, 1500)
      return
    }
    this.loadProducts()
  },
  onShow: function() {
    this.loadProducts()
  },
  loadProducts: function() {
    var self = this
    self.setData({ loading: true })
    api.get('/products?owner=me').then(function(res) {
      var raw = (res.data && res.data.items) || []
      var items = []
      for (var i = 0; i < raw.length; i++) {
        var p = raw[i]
        items.push({
          id: p.id,
          name: p.name,
          price: p.price,
          description: p.description,
          earn_per_share: p.earn_per_share,
          status: p.status || 'active',
          isActive: p.status !== 'inactive',
          images: p.images,
          firstImage: safeGetImage(p.images)
        })
      }
      self.setData({ products: items, loading: false })
    })
  },
  toggleStatus: function(e) {
    var self = this
    var id = e.currentTarget.dataset.id
    var isActive = e.currentTarget.dataset.active === 'true'
    var newStatus = isActive ? 'inactive' : 'active'
    var action = isActive ? '下架' : '上架'

    wx.showModal({
      title: '提示',
      content: '确定' + action + '该产品？',
      success: function(res) {
        if (res.confirm) {
          wx.showLoading({ title: action + '中...' })
          api.put('/products/' + id + '/status', { status: newStatus }).then(function(res) {
            wx.hideLoading()
            if (res.code === 200) {
              wx.showToast({ title: action + '成功', icon: 'success' })
              self.loadProducts()
            } else {
              wx.showToast({ title: res.message || action + '失败', icon: 'none' })
            }
          })
        }
      }
    })
  },
  editProduct: function(e) {
    wx.showToast({ title: '编辑功能开发中', icon: 'none' })
  }
})
