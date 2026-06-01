var api = require('../../utils/api')

Page({
  data: {
    title: '',
    categoryIndex: -1,
    categories: ['AI名片', 'GEO诊断', '数字分身', '营销工具', '企业服务', '软件开发', '设计', '其他'],
    budget: '',
    description: '',
    contact: '',
    submitting: false
  },
  onTitleInput: function(e) {
    this.setData({ title: e.detail.value })
  },
  onCategoryChange: function(e) {
    this.setData({ categoryIndex: parseInt(e.detail.value) })
  },
  onBudgetInput: function(e) {
    this.setData({ budget: e.detail.value })
  },
  onDescInput: function(e) {
    this.setData({ description: e.detail.value })
  },
  onContactInput: function(e) {
    this.setData({ contact: e.detail.value })
  },
  handleSubmit: function() {
    var self = this
    var title = self.data.title.trim()
    if (!title) {
      wx.showToast({ title: '请输入需求标题', icon: 'none' })
      return
    }
    if (self.data.submitting) return
    self.setData({ submitting: true })

    var data = { title: title }
    if (self.data.categoryIndex >= 0) data.category = self.data.categories[self.data.categoryIndex]
    if (self.data.budget) data.budget = parseFloat(self.data.budget) || 0
    if (self.data.description) data.description = self.data.description
    if (self.data.contact) data.contact = self.data.contact

    api.post('/api/v1/needs', data).then(function(res) {
      self.setData({ submitting: false })
      if (res && res.code === 200) {
        wx.showToast({ title: '发布成功', icon: 'success' })
        setTimeout(function() {
          wx.navigateBack()
        }, 1500)
      } else {
        wx.showToast({ title: res.message || '发布失败', icon: 'none' })
      }
    }).catch(function() {
      self.setData({ submitting: false })
      wx.showToast({ title: '网络错误', icon: 'none' })
    })
  }
})
