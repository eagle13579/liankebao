var api = require('../../utils/api')

Page({
  data: {
    list: [],
    page: 1,
    pageSize: 20,
    hasMore: true,
    loading: false
  },
  onLoad: function() {
    this.loadNotifications(true)
  },
  onShow: function() {
    if (this.data.list.length > 0) {
      this.loadNotifications(true)
    }
  },
  onPullDownRefresh: function() {
    this.loadNotifications(true)
    wx.stopPullDownRefresh()
  },
  loadNotifications: function(reset) {
    var self = this
    if (reset) {
      self.setData({ page: 1, hasMore: true, list: [], loading: true })
    } else {
      self.setData({ loading: true })
    }

    var params = { page: self.data.page, pageSize: self.data.pageSize }

    api.get('/api/v1/notifications?' + objToParams(params)).then(function(res) {
      var raw = (res.data && res.data.items) || res.data || []
      if (!Array.isArray(raw)) raw = []

      var newList = reset ? raw : self.data.list.concat(raw)
      var hasMore = raw.length >= self.data.pageSize

      self.setData({
        list: newList,
        hasMore: hasMore,
        loading: false,
        page: reset ? 2 : self.data.page + 1
      })
    }).catch(function() {
      self.setData({ loading: false })
    })
  },
  markRead: function(e) {
    var self = this
    var id = e.currentTarget.dataset.id
    var list = self.data.list
    for (var i = 0; i < list.length; i++) {
      if (list[i].id === id) {
        if (list[i].read) return
        list[i].read = true
        break
      }
    }
    self.setData({ list: list })

    api.put('/api/v1/notifications/' + id + '/read').then(function(res) {
      // silent
    }).catch(function() {
      // silent
    })
  },
  loadMore: function() {
    if (!this.data.hasMore || this.data.loading) return
    this.loadNotifications(false)
  }
})

function objToParams(obj) {
  var parts = []
  for (var key in obj) {
    if (obj[key] !== undefined && obj[key] !== null && obj[key] !== '') {
      parts.push(encodeURIComponent(key) + '=' + encodeURIComponent(obj[key]))
    }
  }
  return parts.join('&')
}
