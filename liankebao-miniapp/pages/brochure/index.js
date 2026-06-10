// 链客宝AI数字名片 - 画册页面
var api = require('../../utils/api')
Page({
  data: {
    userInfo: null,
    products: [],
    needs: [],
    trustCount: 0,
    hasBadge: false,
    shareToken: '',
    currentPage: 0,
    totalPages: 3,
    touchStartX: 0,
    touchEndX: 0,
    isAnimating: false,
    pages: [
      { id: 'cover', title: '封面' },
      { id: 'product', title: '产品' },
      { id: 'demand', title: '需求' }
    ]
  },

  onLoad(options) {
    const { share_token } = options
    if (share_token) {
      console.log('[brochure] 分享token:', share_token)
      this.setData({ shareToken: share_token })
      api.getSharedBrochure(share_token).then(res => {
        if (res && res.data) this._setBrochureData(res.data)
      }).catch(e => console.error('[brochure] 加载分享名片失败', e))
    } else {
      // 自己的名片
      var user = wx.getStorageSync('user')
      if (user && user.user_id) {
        api.getMyBrochures(user.user_id).then(res => {
          if (res && res.data) this._setBrochureData(res.data)
        }).catch(e => console.error('[brochure] 加载画册失败', e))
      }
    }
  },

  /** 设置画册数据 */
  _setBrochureData: function(data) {
    this.setData({
      userInfo: {
        name: data.profile?.name || data.name || '',
        company: data.profile?.company || data.company || '',
        position: data.profile?.position || data.position || '',
        avatar: data.profile?.avatar || data.avatar || '',
        bio: data.bio || ''
      },
      products: data.supplies || data.products || [],
      needs: data.demands || data.needs || [],
      trustCount: data.trust_count || 0,
      hasBadge: data.has_badge || false,
      shareToken: data.share_token || this.data.shareToken || ''
    })
  },

  onShow() {
    // 重置动画状态
    this.setData({ isAnimating: false })
  },

  // 分享给客户 - 传递share_token
  onShareAppMessage() {
    const shareToken = this.data.shareToken || 'direct'
    const title = 'AI数字名片 - 链客宝'
    const path = `/pages/brochure/index?share_token=${shareToken}`
    return {
      title,
      path,
      imageUrl: '/assets/images/share-card.png'
    }
  },

  // 分享按钮点击
  handleShare() {
    wx.shareAppMessage({
      title: 'AI数字名片 - 链客宝',
      path: `/pages/brochure/index?share_token=${this.data.shareToken || 'direct'}`
    })
  },

  // 翻页：上一页
  prevPage() {
    if (this.data.isAnimating) return
    if (this.data.currentPage > 0) {
      this.setData({
        isAnimating: true,
        currentPage: this.data.currentPage - 1
      })
      setTimeout(() => {
        this.setData({ isAnimating: false })
      }, 400)
    }
  },

  // 翻页：下一页
  nextPage() {
    if (this.data.isAnimating) return
    if (this.data.currentPage < this.data.totalPages - 1) {
      this.setData({
        isAnimating: true,
        currentPage: this.data.currentPage + 1
      })
      setTimeout(() => {
        this.setData({ isAnimating: false })
      }, 400)
    }
  },

  // 触摸手势开始
  handleTouchStart(e) {
    if (this.data.isAnimating) return
    this.setData({
      touchStartX: e.touches[0].clientX
    })
  },

  // 触摸手势移动
  handleTouchMove(e) {
    if (this.data.isAnimating) return
    this.setData({
      touchEndX: e.touches[0].clientX
    })
  },

  // 触摸手势结束 - 判断翻页方向
  handleTouchEnd() {
    if (this.data.isAnimating) return
    const { touchStartX, touchEndX } = this.data
    const diff = touchStartX - touchEndX
    // 最小滑动距离 50px
    if (Math.abs(diff) < 50) return

    if (diff > 0) {
      // 左滑 -> 下一页
      this.nextPage()
    } else {
      // 右滑 -> 上一页
      this.prevPage()
    }

    this.setData({
      touchStartX: 0,
      touchEndX: 0
    })
  },

  // 指示器点击跳转
  goToPage(e) {
    if (this.data.isAnimating) return
    const page = e.currentTarget.dataset.page
    if (page >= 0 && page < this.data.totalPages) {
      this.setData({
        isAnimating: true,
        currentPage: page
      })
      setTimeout(() => {
        this.setData({ isAnimating: false })
      }, 400)
    }
  },

  // 跳转到创建名片页
  goToCreateCard() {
    wx.navigateTo({
      url: '/pages/create-card/index'
    })
  }
})
