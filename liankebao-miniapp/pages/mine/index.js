// pages/mine/index.js
// 我的页面 - 用户信息与功能菜单

const api = require('../../utils/api');

Page({
  data: {
    userInfo: {},
    menuItems: [
      { text: '我的画册', icon: '📇', page: 'brochure/index' },
      { text: '画册二维码', icon: '📱', page: 'brochure-qrcode/index' },
      { text: '信任网络', icon: '🔗', page: 'trust-network/index' }
    ]
  },

  onLoad() {
    this.loadUser();
  },

  onShow() {
    this.loadUser();
  },

  loadUser() {
    // 从本地存储获取用户信息
    const userInfo = wx.getStorageSync('userInfo');
    if (userInfo) {
      this.setData({ userInfo });
    }

    // 尝试从服务端获取最新用户信息
    api.request('/api/v1/user/profile')
      .then(res => {
        if (res.data) {
          this.setData({ userInfo: res.data });
          wx.setStorageSync('userInfo', res.data);
        }
      })
      .catch(err => {
        console.error('获取用户信息失败:', err);
      });
  },

  onMenuItemTap(e) {
    const page = e.currentTarget.dataset.page;
    if (page) {
      wx.navigateTo({
        url: '/pages/' + page,
        fail(err) {
          console.error('跳转失败:', err);
          wx.showToast({ title: '页面不存在', icon: 'none' });
        }
      });
    }
  },

  goToProfile() {
    wx.navigateTo({
      url: '/pages/user/profile',
      fail() {
        wx.showToast({ title: '功能开发中', icon: 'none' });
      }
    });
  }
});
