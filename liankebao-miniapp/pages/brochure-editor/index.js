var api = require("../../utils/api")
Page({
  data: { step: 1, maxStep: 6, form: { name: "", company: "", position: "", bio: "", phone: "", wechat: "", email: "", products: [], needs: [], trustIds: [] }, submitting: false },
  next: function() { var s = this.data.step; if (s < this.data.maxStep) this.setData({ step: s + 1 }) },
  prev: function() { var s = this.data.step; if (s > 1) this.setData({ step: s - 1 }) },
  onInput: function(e) { var f = this.data.form; f[e.currentTarget.dataset.field] = e.detail.value; this.setData({ form: f }) },
  addProduct: function() { var p = this.data.form.products; p.push({ name: "", price: "", desc: "", image: "" }); this.setData({ "form.products": p }) },
  removeProduct: function(e) { var p = this.data.form.products; p.splice(e.currentTarget.dataset.index, 1); this.setData({ "form.products": p }) },
  submit: function() {
    var self = this, user = wx.getStorageSync("user")
    if (!user || !user.user_id) { wx.showToast({ title: "请先登录", icon: "none" }); return }
    self.setData({ submitting: true })
    api.request("/api/brochures/" + user.user_id, "PUT", self.data.form).then(function(r) {
      wx.showToast({ title: "保存成功" })
      setTimeout(function() { wx.navigateBack() }, 1500)
    }).catch(function(e) { wx.showToast({ title: "保存失败", icon: "none" }) })
    .finally(function() { self.setData({ submitting: false }) })
  }
})