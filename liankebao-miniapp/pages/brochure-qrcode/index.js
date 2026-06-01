var api = require("../../utils/api")
Page({
  data: { qrCodeUrl: "", visitorCount: 0, brochureId: "" },
  onLoad: function() {
    var user = wx.getStorageSync("user")
    if (user && user.user_id) {
      this.setData({ brochureId: user.user_id })
      this.loadQR(user.user_id)
    }
  },
  loadQR: function(id) {
    var self = this
    api.request("/api/v1/brochure/" + id + "/qrcode").then(function(r) {
      if (r && r.data) self.setData({ qrCodeUrl: r.data.url || "", visitorCount: r.data.visitor_count || 0 })
    })
  },
  saveImage: function() {
    var self = this
    wx.downloadFile({ url: self.data.qrCodeUrl, success: function(r) {
      wx.saveImageToPhotosAlbum({ filePath: r.tempFilePath, success: function() { wx.showToast({ title: "已保存" }) } })
    }})
  },
  onShareAppMessage: function() { return { title: "我的AI数字名片" } }
})
