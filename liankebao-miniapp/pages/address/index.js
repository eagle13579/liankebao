var api = require('../../utils/api')

Page({
  data: {
    addresses: [],
    loading: true,
    formVisible: false,
    editId: null,
    formData: {
      name: '',
      mobile: '',
      address: '',
      is_default: false
    }
  },

  onLoad: function() {
    var token = wx.getStorageSync('token')
    if (!token) {
      wx.navigateTo({ url: '/pages/login/index' })
      return
    }
    this.loadAddresses()
  },

  onShow: function() {
    this.loadAddresses()
  },

  loadAddresses: function() {
    var self = this
    self.setData({ loading: true })
    api.get('/addresses').then(function(res) {
      var items = []
      if (res.code === 200 && res.data) {
        var raw = res.data.items || res.data || []
        for (var i = 0; i < raw.length; i++) {
          var a = raw[i]
          items.push({
            id: a.id,
            name: a.name || '',
            mobile: a.mobile || '',
            address: a.address || '',
            is_default: a.is_default || false
          })
        }
      }
      self.setData({ addresses: items, loading: false })
    }).catch(function() {
      self.setData({ loading: false })
      wx.showToast({ title: '网络异常，请重试', icon: 'none' })
    })
  },

  handleAdd: function() {
    this.setData({
      formVisible: true,
      editId: null,
      formData: { name: '', mobile: '', address: '', is_default: false }
    })
    this.showFormModal()
  },

  handleEdit: function(e) {
    var id = e.currentTarget.dataset.id
    var items = this.data.addresses
    var target = null
    for (var i = 0; i < items.length; i++) {
      if (items[i].id === id) {
        target = items[i]
        break
      }
    }
    if (!target) return
    this.setData({
      formVisible: true,
      editId: id,
      formData: {
        name: target.name,
        mobile: target.mobile,
        address: target.address,
        is_default: target.is_default
      }
    })
    this.showFormModal(true)
  },

  showFormModal: function(isEdit) {
    var self = this
    var fd = self.data.formData
    wx.showModal({
      title: isEdit ? '编辑地址' : '新增地址',
      content: ' ',
      editable: false,
      showCancel: false,
      success: function() {}
    })
    // Use custom form via prompt sequence - simpler approach with showModal for each field
    self.promptField('收件人姓名', fd.name, function(name) {
      if (name === null || name === '') { wx.showToast({ title: '请输入收件人', icon: 'none' }); return }
      self.promptField('手机号', fd.mobile, function(mobile) {
        if (mobile === null || mobile === '') { wx.showToast({ title: '请输入手机号', icon: 'none' }); return }
        if (!/^1\d{10}$/.test(mobile)) { wx.showToast({ title: '手机号格式有误', icon: 'none' }); return }
        self.promptField('详细地址', fd.address, function(address) {
          if (address === null || address === '') { wx.showToast({ title: '请输入详细地址', icon: 'none' }); return }
          self.promptDefault(function(isDefault) {
            var data = { name: name, mobile: mobile, address: address, is_default: isDefault }
            if (isEdit) {
              self.saveAddress(self.data.editId, data)
            } else {
              self.saveAddress(null, data)
            }
          })
        })
      })
    })
  },

  promptField: function(label, defaultValue, callback) {
    var self = this
    wx.showModal({
      title: label,
      content: '',
      placeholderText: '请输入' + label,
      editable: true,
      showCancel: true,
      cancelText: '取消',
      confirmText: '确定',
      success: function(res) {
        if (res.confirm) {
          callback(res.content || defaultValue)
        }
      }
    })
  },

  promptDefault: function(callback) {
    wx.showModal({
      title: '设为默认地址',
      content: '是否将此地址设为默认地址？',
      cancelText: '否',
      confirmText: '是',
      success: function(res) {
        callback(res.confirm)
      }
    })
  },

  saveAddress: function(id, data) {
    var self = this
    wx.showLoading({ title: '保存中...' })
    var request
    if (id) {
      request = api.put('/addresses/' + id, data)
    } else {
      request = api.post('/addresses', data)
    }
    request.then(function(res) {
      wx.hideLoading()
      if (res.code === 200) {
        wx.showToast({ title: '保存成功', icon: 'success' })
        self.setData({ formVisible: false })
        self.loadAddresses()
      } else {
        wx.showToast({ title: res.message || '保存失败', icon: 'none' })
      }
    }).catch(function() {
      wx.hideLoading()
      wx.showToast({ title: '网络异常，请重试', icon: 'none' })
    })
  },

  handleDelete: function(e) {
    var self = this
    var id = e.currentTarget.dataset.id
    wx.showModal({
      title: '提示',
      content: '确定删除该地址？',
      success: function(res) {
        if (res.confirm) {
          wx.showLoading({ title: '删除中...' })
          api.del('/addresses/' + id).then(function(res) {
            wx.hideLoading()
            if (res.code === 200) {
              wx.showToast({ title: '删除成功', icon: 'success' })
              self.loadAddresses()
            } else {
              wx.showToast({ title: res.message || '删除失败', icon: 'none' })
            }
          }).catch(function() {
            wx.hideLoading()
            wx.showToast({ title: '网络异常，请重试', icon: 'none' })
          })
        }
      }
    })
  }
})
