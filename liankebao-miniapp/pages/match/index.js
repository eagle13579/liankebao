// pages/match/index.js
// 匹配结果页 - 脱敏展示 + 付费解锁
var api = require('../../utils/api')
var util = require('../../utils/util')
var auth = require('../../utils/auth')

Page({
  data: {
    loading: true,
    matches: [],
    filteredMatches: [],
    filterType: '',        // 筛选: '' | 找合作伙伴 | 找客户 | 找投资人 | 找供应商
    filterOptions: ['全部', '找合作伙伴', '找客户', '找投资人', '找供应商'],
    matchStats: { total: 0, today: 0 },
    // 解锁弹窗
    showUnlockModal: false,
    unlockTarget: null,
    // 会员信息
    membershipTier: 'free',  // free | vip
    userInfo: null
  },

  onLoad: function() {
    if (!auth.checkLogin()) {
      wx.reLaunch({ url: '/pages/login/index' })
      return
    }
    this.loadUserInfo()
  },

  onShow: function() {
    if (auth.checkLogin()) {
      this.loadMatches()
    }
  },

  loadUserInfo: function() {
    var self = this
    // 从缓存或后端获取用户会员信息
    var user = wx.getStorageSync('user') || {}
    self.setData({
      userInfo: user,
      membershipTier: user.membership_tier || 'free'
    })
    // 尝试从后端获取最新信息
    api.getUserInfo().then(function(res) {
      var userData = res.data || res
      if (userData) {
        var tier = userData.membership_tier || 'free'
        self.setData({
          userInfo: userData,
          membershipTier: tier
        })
        // 更新缓存
        var cachedUser = wx.getStorageSync('user') || {}
        cachedUser.membership_tier = tier
        cachedUser.name = userData.name || cachedUser.name
        wx.setStorageSync('user', cachedUser)
      }
    }).catch(function() {})
  },

  loadMatches: function() {
    var self = this
    self.setData({ loading: true })

    api.matchEngine({}).then(function(res) {
      var matchList = []
      if (res && res.data) {
        matchList = Array.isArray(res.data) ? res.data : (res.data.matches || res.data.items || [])
      } else if (Array.isArray(res)) {
        matchList = res
      } else if (res && res.matches) {
        matchList = res.matches
      }

      // 处理脱敏数据
      var processed = matchList.map(function(m) {
        return {
          id: m.id || m.match_id || '',
          name: m.name || util.maskName(m.real_name || m.username || '未知'),
          masked_name: util.maskName(m.real_name || m.name || m.username || '未知'),
          real_name: m.real_name || m.name || '',
          company: m.company || '',
          position: m.position || '',
          matchPercent: m.match_percent || m.match_score || m.score || 0,
          tags: m.tags || m.provide_tags || [],
          needTags: m.need_tags || [],
          isUnlocked: m.is_unlocked || m.unlocked || false,
          phone: m.is_unlocked ? (m.phone || '') : util.maskPhone(m.phone || ''),
          full_phone: m.phone || '',
          email: m.email || '',
          wechat: m.wechat || '',
          avatar: m.avatar || '',
          purpose: m.purpose || ''
        }
      })

      self.setData({
        matches: processed,
        filteredMatches: processed,
        matchStats: {
          total: processed.length,
          today: processed.filter(function(m) { return m.matchPercent >= 80 }).length || 0
        },
        loading: false
      })
    }).catch(function(err) {
      // 降级：使用mock数据
      self.loadMockMatches()
    })
  },

  loadMockMatches: function() {
    var self = this
    var mockMatches = [
      { id: '1', name: '李**', real_name: '李伟', company: '数据科技公司', position: 'CTO', matchPercent: 85, tags: ['AI开发', '云计算'], needTags: ['市场渠道'], phone: '138****0000', full_phone: '13800138000', purpose: '找合作伙伴' },
      { id: '2', name: '王**', real_name: '王芳', company: '创新工场', position: '投资经理', matchPercent: 72, tags: ['创业投资', '市场拓展'], needTags: ['优质项目'], phone: '139****1111', full_phone: '13900139111', purpose: '找投资人' },
      { id: '3', name: '赵**', real_name: '赵强', company: '供应链集团', position: '采购总监', matchPercent: 68, tags: ['供应链', '物流'], needTags: ['供应商'], phone: '137****2222', full_phone: '13700137222', purpose: '找供应商' },
      { id: '4', name: '陈**', real_name: '陈静', company: '营销策划公司', position: 'CEO', matchPercent: 91, tags: ['品牌营销', '新媒体'], needTags: ['客户资源'], phone: '136****3333', full_phone: '13600136333', purpose: '找客户' }
    ]
    self.setData({
      matches: mockMatches,
      filteredMatches: mockMatches,
      matchStats: { total: mockMatches.length, today: 3 },
      loading: false
    })
  },

  // === 筛选 ===
  selectFilter: function(e) {
    var type = e.currentTarget.dataset.type
    var filterType = type === '全部' ? '' : type
    this.setData({ filterType: filterType })
    this.applyFilter()
  },

  applyFilter: function() {
    var ft = this.data.filterType
    var list = this.data.matches
    if (ft) {
      list = list.filter(function(m) {
        return m.purpose === ft
      })
    }
    this.setData({ filteredMatches: list })
  },

  // === 解锁弹窗 ===
  showUnlock: function(e) {
    var id = e.currentTarget.dataset.id
    var target = this.data.matches.find(function(m) { return m.id == id })
    if (!target) return

    // 已解锁直接显示
    if (target.isUnlocked) {
      wx.showModal({
        title: target.real_name + '的联系方式',
        content: '📞 ' + (target.full_phone || target.phone) + '\n✉️ ' + (target.email || '未提供') + '\n💬 ' + (target.wechat || '未提供'),
        showCancel: false
      })
      return
    }

    // 免费用户
    if (this.data.membershipTier === 'free') {
      // 显示402提示
      wx.showModal({
        title: '升级会员',
        content: '免费用户暂不支持查看联系方式。升级VIP会员即可无限次解锁。',
        confirmText: '去升级',
        success: function(res) {
          if (res.confirm) {
            wx.switchTab({ url: '/pages/mine/index' })
          }
        }
      })
      return
    }

    // VIP用户显示解锁弹窗
    this.setData({
      showUnlockModal: true,
      unlockTarget: target
    })
  },

  closeUnlockModal: function() {
    this.setData({ showUnlockModal: false, unlockTarget: null })
  },

  stopPropagation: function() {},

  // 单次解锁
  handleUnlock: function() {
    var self = this
    var target = self.data.unlockTarget
    if (!target) return

    wx.showLoading({ title: '解锁中...' })
    api.unlockContact(target.id).then(function(res) {
      wx.hideLoading()
      self.closeUnlockModal()

      // 更新匹配列表
      var matches = self.data.matches.map(function(m) {
        if (m.id == target.id) {
          m.isUnlocked = true
          m.phone = m.full_phone
        }
        return m
      })
      self.setData({ matches: matches })
      self.applyFilter()

      wx.showToast({ title: '解锁成功', icon: 'success' })
    }).catch(function(err) {
      wx.hideLoading()
      wx.showModal({
        title: '解锁失败',
        content: err.message || '请稍后重试',
        showCancel: false
      })
    })
  },

  // 去升级会员
  goUpgrade: function() {
    this.closeUnlockModal()
    wx.switchTab({ url: '/pages/mine/index' })
  },

  // 查看他人名片
  goViewProfile: function(e) {
    var id = e.currentTarget.dataset.id
  },

  goEdit: function() {
    wx.navigateTo({ url: '/pages/card-editor/index' })
  },

  onShareAppMessage: function() {
    return {
      title: 'AI数字名片 - 智能匹配合作伙伴',
      path: '/pages/match/index'
    }
  }
})
