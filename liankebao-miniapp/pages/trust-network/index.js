// pages/trust-network/index.js
// 信任网络页面 - 管理用户的信任关系

const api = require('../../utils/api');

Page({
  data: {
    trustList: [],
    searchKeyword: '',
    searchResults: [],
    showSearchResults: false,
    loading: false
  },

  onLoad() {
    this.loadTrustNetwork();
  },

  onShow() {
    this.loadTrustNetwork();
  },

  // 加载信任网络列表
  loadTrustNetwork() {
    this.setData({ loading: true });
    // 获取当前用户ID（从全局或本地存储）
    const userId = wx.getStorageSync('userId') || wx.getStorageSync('userInfo')?.id;
    if (!userId) {
      this.setData({ loading: false });
      return;
    }
    api.request('/api/v1/brochures/' + userId + '/trust_network')
      .then(res => {
        this.setData({
          trustList: res.data || res.data?.list || [],
          loading: false
        });
      })
      .catch(err => {
        console.error('加载信任网络失败:', err);
        this.setData({ loading: false });
      });
  },

  // 搜索输入
  onSearchInput(e) {
    const keyword = e.detail.value;
    this.setData({ searchKeyword: keyword });
    if (keyword.trim().length < 2) {
      this.setData({ searchResults: [], showSearchResults: false });
      return;
    }
    // 防抖搜索
    if (this._searchTimer) clearTimeout(this._searchTimer);
    this._searchTimer = setTimeout(() => {
      this.searchUsers(keyword.trim());
    }, 300);
  },

  // 搜索确认
  onSearchConfirm() {
    const keyword = this.data.searchKeyword.trim();
    if (keyword.length >= 2) {
      this.searchUsers(keyword);
    }
  },

  // 搜索用户
  searchUsers(keyword) {
    api.request('/api/v1/users/search', {
      data: { keyword }
    })
      .then(res => {
        const results = res.data || res.data?.list || [];
        // 过滤掉已在信任列表中的用户
        const trustIds = this.data.trustList.map(t => t.id);
        const filtered = results.filter(u => !trustIds.includes(u.id));
        this.setData({
          searchResults: filtered,
          showSearchResults: true
        });
      })
      .catch(err => {
        console.error('搜索用户失败:', err);
        wx.showToast({ title: '搜索失败', icon: 'none' });
      });
  },

  // 添加信任
  addTrust(e) {
    const user = e.currentTarget.dataset.user;
    if (!user || !user.id) return;

    wx.showLoading({ title: '添加中...' });
    api.request('/api/v1/trust/add', {
      method: 'POST',
      data: { targetUserId: user.id }
    })
      .then(res => {
        wx.hideLoading();
        wx.showToast({ title: '已添加信任', icon: 'success' });
        // 从搜索结果中移除
        const results = this.data.searchResults.filter(u => u.id !== user.id);
        this.setData({ searchResults: results });
        // 重新加载信任列表
        this.loadTrustNetwork();
      })
      .catch(err => {
        wx.hideLoading();
        wx.showToast({ title: '添加失败', icon: 'none' });
        console.error('添加信任失败:', err);
      });
  },

  // 长按移除信任
  onLongPress(e) {
    const id = e.currentTarget.dataset.id;
    const index = e.currentTarget.dataset.index;
    const item = this.data.trustList[index];

    wx.showModal({
      title: '移除信任',
      content: '确定要移除对 ' + (item.name || '该用户') + ' 的信任吗？',
      success: (res) => {
        if (res.confirm) {
          this.removeTrust(id, index);
        }
      }
    });
  },

  // 执行移除
  removeTrust(id, index) {
    wx.showLoading({ title: '移除中...' });
    api.request('/api/v1/trust/remove', {
      method: 'POST',
      data: { targetUserId: id }
    })
      .then(res => {
        wx.hideLoading();
        wx.showToast({ title: '已移除', icon: 'success' });
        const list = [...this.data.trustList];
        list.splice(index, 1);
        this.setData({ trustList: list });
      })
      .catch(err => {
        wx.hideLoading();
        wx.showToast({ title: '移除失败', icon: 'none' });
        console.error('移除信任失败:', err);
      });
  }
});
