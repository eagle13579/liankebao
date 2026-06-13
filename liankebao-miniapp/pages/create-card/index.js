// 链客宝AI数字名片 - 自助创建页面
const api = require('../../utils/api')

Page({
  data: {
    // 微信授权状态
    authStep: 'profile', // profile: 用户信息授权, phone: 手机号授权, form: 补充信息, done: 已完成
    // 用户信息
    nickName: '',
    avatarUrl: '',
    phoneNumber: '',
    company: '',
    position: '',
    // 生成的卡片信息
    cardId: '',
    previewUrl: '',
    // 加载状态
    loading: false,
    errorMsg: ''
  },

  onLoad(options) {
    // 检查是否已有登录态，如果有直接进入表单
    const hasProfile = wx.getStorageSync('wx_user_profile')
    if (hasProfile) {
      this.setData({
        nickName: hasProfile.nickName,
        avatarUrl: hasProfile.avatarUrl,
        authStep: 'phone'
      })
    }
  },

  // 步骤1: 获取微信用户信息（头像、昵称）
  handleGetUserProfile() {
    if (this.data.loading) return
    this.setData({ loading: true, errorMsg: '' })

    api.getWxUserProfile()
      .then((userInfo) => {
        // 缓存用户信息
        wx.setStorageSync('wx_user_profile', userInfo)
        this.setData({
          nickName: userInfo.nickName,
          avatarUrl: userInfo.avatarUrl,
          authStep: 'phone',
          loading: false
        })
      })
      .catch((err) => {
        this.setData({
          loading: false,
          errorMsg: err.msg || '授权失败，请重试'
        })
      })
  },

  // 步骤2: 获取微信手机号
  handleGetPhoneNumber(e) {
    if (this.data.loading) return
    this.setData({ loading: true, errorMsg: '' })

    api.getWxPhoneNumber(e)
      .then((phoneData) => {
        // 暂存手机号加密数据
        this.setData({
          encryptedData: phoneData.encryptedData,
          iv: phoneData.iv,
          code: phoneData.code,
          authStep: 'form',
          loading: false
        })
      })
      .catch((err) => {
        this.setData({
          loading: false,
          errorMsg: err.msg || '获取手机号失败'
        })
      })
  },

  // 步骤3: 表单输入 - 公司名
  onCompanyInput(e) {
    this.setData({ company: e.detail.value })
  },

  // 步骤3: 表单输入 - 职位
  onPositionInput(e) {
    this.setData({ position: e.detail.value })
  },

  // 步骤4: 提交生成名片
  handleSubmit() {
    const { nickName, avatarUrl, encryptedData, iv, code, company, position } = this.data
    if (!company.trim()) {
      this.setData({ errorMsg: '请填写公司名称' })
      return
    }
    if (!position.trim()) {
      this.setData({ errorMsg: '请填写职位' })
      return
    }
    if (this.data.loading) return
    this.setData({ loading: true, errorMsg: '' })

    api.createCard({
      nickName,
      avatarUrl,
      encryptedData,
      iv,
      code,
      company: company.trim(),
      position: position.trim()
    })
      .then((res) => {
        this.setData({
          cardId: res.cardId,
          previewUrl: res.previewUrl,
          authStep: 'done',
          loading: false
        })
        // 跳转到预览页面
        wx.navigateTo({
          url: `/pages/brochure/index?card_id=${res.cardId}`
        })
      })
      .catch((err) => {
        this.setData({
          loading: false,
          errorMsg: err.msg || '名片生成失败，请重试'
        })
      })
  },

  // 返回上一页
  goBack() {
    wx.navigateBack()
  },

  // 重新授权用户信息
  handleRetry() {
    this.setData({
      authStep: 'profile',
      errorMsg: '',
      nickName: '',
      avatarUrl: '',
      phoneNumber: '',
      company: '',
      position: ''
    })
  }
})
