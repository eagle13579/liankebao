/**
 * 画册首页 pages/brochure/index
 * 展示用户画册信息：头像、名片、产品列表、需求列表、信任网络
 */
const api = require('../../utils/api');

Page({
  data: {
    // 加载状态
    loading: true,
    error: false,
    errorMsg: '',

    // 用户信息
    userInfo: null,

    // 画册数据
    brochure: null,

    // 产品列表（横向滚动用）
    products: [],

    // 需求列表
    needs: [],

    // 信任网络
    trustCount: 0,
    hasBadge: false,

    // 骨架屏数据
    skeletonItems: [1, 2, 3, 4, 5, 6],
  },

  onLoad() {
    this.loadBrochure();
  },

  /**
   * 加载画册数据
   */
  loadBrochure() {
    const self = this;
    const user = wx.getStorageSync('user');
    let userId = '';

    if (user && user.id) {
      userId = user.id;
    } else if (user && user.user_id) {
      userId = user.user_id;
    }

    if (!userId) {
      self.setData({
        loading: false,
        error: true,
        errorMsg: '未获取到用户信息，请重新登录',
      });
      return;
    }

    self.setData({ loading: true, error: false });

    api.request('/api/v1/brochures/' + userId)
      .then(function (res) {
        const data = res.data || res;
        self.setData({
          loading: false,
          brochure: data,
          userInfo: {
            avatar: data.avatar || '',
            name: data.name || data.nickname || '未设置昵称',
            company: data.company || '',
            position: data.position || '',
            bio: data.bio || data.introduction || '',
          },
          products: data.products || [],
          needs: data.needs || [],
          trustCount: data.trust_count || data.trustCount || 0,
          hasBadge: data.has_badge || data.hasBadge || false,
        });
      })
      .catch(function (err) {
        self.setData({
          loading: false,
          error: true,
          errorMsg: err.message || '加载失败，请重试',
        });
      });
  },

  /**
   * 点击产品项
   */
  onProductTap(e) {
    const productId = e.currentTarget.dataset.id;
    if (productId) {
      wx.navigateTo({
        url: '/pages/products/detail?id=' + productId,
      });
    }
  },

  /**
   * 点击需求项
   */
  onNeedTap(e) {
    const needId = e.currentTarget.dataset.id;
    if (needId) {
      wx.navigateTo({
        url: '/pages/needs/detail?id=' + needId,
      });
    }
  },

  /**
   * 分享画册
   */
  onShareAppMessage() {
    const brochure = this.data.brochure;
    const userInfo = this.data.userInfo;
    const title = (userInfo && userInfo.name) ? (userInfo.name + ' 的画册') : '链客宝 - 我的画册';
    const imageUrl = (userInfo && userInfo.avatar) ? userInfo.avatar : '';

    return {
      title: title,
      path: '/pages/brochure/index',
      imageUrl: imageUrl,
    };
  },

  /**
   * 分享到朋友圈
   */
  onShareTimeline() {
    const userInfo = this.data.userInfo;
    const title = (userInfo && userInfo.name) ? (userInfo.name + ' 的画册') : '链客宝 - 我的画册';
    return {
      title: title,
      query: {},
    };
  },

  /**
   * 下拉刷新
   */
  onPullDownRefresh() {
    this.loadBrochure();
    wx.stopPullDownRefresh();
  },

  /**
   * 重试加载
   */
  onRetry() {
    this.loadBrochure();
  },
});
