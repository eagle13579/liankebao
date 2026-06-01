var api = require("../../utils/api")
Page({
  data: { trustList: [], searchQuery: "", searchResults: [], loading: true },
  onLoad: function() { this.loadTrust() },
  loadTrust: function() {
    var self = this, user = wx.getStorageSync("user")
    if (!user) return
    api.request("/api/v1/brochures/" + user.user_id + "/trust_network").then(function(r) {
      self.setData({ trustList: r && r.data ? r.data : [], loading: false })
    })
  },
  onSearch: function(e) {
    var q = e.detail.value, self = this
    self.setData({ searchQuery: q })
    if (q.length < 2) return
    api.request("/api/v1/users?q=" + q).then(function(r) {
      if (r && r.data) self.setData({ searchResults: r.data })
    })
  },
  addTrust: function(e) {
    var self = this, user = wx.getStorageSync("user"), targetId = e.currentTarget.dataset.id
    api.request("/api/v1/brochures/" + user.user_id + "/trust_network", "POST", { trusted_user_id: targetId }).then(function(r) {
      wx.showToast({ title: "已添加信任" }); self.loadTrust()
    })
  },
  removeTrust: function(e) {
    var self = this, user = wx.getStorageSync("user"), targetId = e.currentTarget.dataset.id
    wx.showModal({ content: "确定移除信任?", success: function(r) {
      if (r.confirm) api.request("/api/v1/brochures/" + user.user_id + "/trust_network?target_id=" + targetId, "DELETE").then(function() {
        wx.showToast({ title: "已移除" }); self.loadTrust()
      })
    }})
  }
})