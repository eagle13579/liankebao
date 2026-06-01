var api = require("../../utils/api")
Page({
  data: { loading: true, error: null, userInfo: null, products: [], needs: [], trustCount: 0, hasBadge: false },
  onLoad: function() {
    var user = wx.getStorageSync("user")
    if (user && user.user_id) {
      this.loadBrochure(user.user_id)
    } else { this.setData({ loading: false, error: "请先登录" }) }
  },
  onShow: function() {
    var user = wx.getStorageSync("user")
    if (user && user.user_id) this.loadBrochure(user.user_id)
  },
  loadBrochure: function(userId) {
    var self = this
    api.request("/api/v1/brochures/" + userId).then(function(res) {
      if (res && res.data) {
        self.setData({
          userInfo: res.data, products: res.data.products || [],
          needs: res.data.needs || [], trustCount: res.data.trust_count || 0,
          hasBadge: res.data.has_badge || false, loading: false
        })
      } else { self.setData({ loading: false, error: "暂无画册数据" }) }
    }).catch(function(e) { self.setData({ loading: false, error: "加载失败" }) })
  },
  onShareAppMessage: function() {
    var u = this.data.userInfo || {}
    return { title: u.name + "的电子画册", path: "/pages/brochure/index" }
  },
  goEdit: function() { wx.navigateTo({ url: "/pages/brochure-editor/index" }) },
  goQR: function() { wx.navigateTo({ url: "/pages/brochure-qrcode/index" }) },
  goTrust: function() { wx.navigateTo({ url: "/pages/trust-network/index" }) }
})