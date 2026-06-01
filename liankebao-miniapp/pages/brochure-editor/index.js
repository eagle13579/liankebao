// pages/brochure-editor/index.js
// 画册编辑器 - 6步编辑向导

const api = require('../../utils/api');

const STEPS = [
  { id: 1, title: '基本信息' },
  { id: 2, title: '联系方式' },
  { id: 3, title: '产品列表' },
  { id: 4, title: '供需需求' },
  { id: 5, title: '信任网络' },
  { id: 6, title: '预览发布' }
];

Page({
  data: {
    // 步骤
    currentStep: 1,
    totalSteps: 6,
    steps: STEPS,
    progressPercent: 16.67,

    // 加载
    loading: false,
    submitting: false,

    // ===== Step 1: 基本信息 =====
    name: '',
    avatar: '',
    company: '',
    position: '',
    bio: '',

    // ===== Step 2: 联系方式 =====
    phone: '',
    wechat: '',
    email: '',

    // ===== Step 3: 产品列表 =====
    products: [],

    // ===== Step 4: 供需需求 =====
    needType: 'supply', // supply | demand
    needTitle: '',
    needDesc: '',
    needTags: '',
    needImage: '',

    // ===== Step 5: 信任网络 =====
    trustList: [],
    searchKeyword: '',
    searchResults: [],
    showSearchResults: false,

    // ===== Step 6: 预览数据 =====
    previewData: {},

    // 错误状态
    fieldErrors: {}
  },

  onLoad() {
    this.loadExistingData();
    this.loadTrustNetwork();
  },

  // 加载已有画册数据
  loadExistingData() {
    const self = this;
    const user = wx.getStorageSync('user') || wx.getStorageSync('userInfo');
    let userId = user?.id || user?.user_id || '';

    if (!userId) {
      wx.showToast({ title: '未获取到用户信息', icon: 'none' });
      return;
    }

    self.setData({ loading: true });

    api.request('/api/v1/brochures/' + userId)
      .then(function (res) {
        const data = res.data || res;
        self.setData({
          loading: false,
          name: data.name || data.nickname || user?.nickName || '',
          avatar: data.avatar || user?.avatarUrl || user?.avatar || '',
          company: data.company || '',
          position: data.position || '',
          bio: data.bio || data.introduction || '',
          phone: data.phone || '',
          wechat: data.wechat || data.weixin || '',
          email: data.email || '',
          products: data.products || [],
          needType: data.need_type || 'supply',
          needTitle: data.need_title || '',
          needDesc: data.need_desc || '',
          needTags: data.need_tags || '',
          needImage: data.need_image || '',
          trustList: data.trust_list || [],
        });
      })
      .catch(function (err) {
        self.setData({ loading: false });
        console.error('加载画册数据失败:', err);
      });
  },

  // 加载信任网络
  loadTrustNetwork() {
    const self = this;
    const user = wx.getStorageSync('user') || wx.getStorageSync('userInfo');
    let userId = user?.id || user?.user_id || '';
    if (!userId) return;

    api.request('/api/v1/brochures/' + userId + '/trust_network')
      .then(res => {
        const list = res.data || res.data?.list || [];
        // 合并到已有trustList
        const existingIds = self.data.trustList.map(t => t.id || t.user_id);
        const newItems = list.filter(t => !existingIds.includes(t.id || t.user_id));
        self.setData({
          trustList: [...self.data.trustList, ...newItems]
        });
      })
      .catch(err => {
        console.error('加载信任网络失败:', err);
      });
  },

  // ===== 步骤导航 =====
  goNext() {
    if (!this.validateStep(this.data.currentStep)) return;
    if (this.data.currentStep < this.data.totalSteps) {
      const next = this.data.currentStep + 1;
      this.setData({
        currentStep: next,
        progressPercent: (next / this.data.totalSteps) * 100
      });
      // 进入步骤5时加载信任网络
      if (next === 5) {
        this.loadTrustNetwork();
      }
      // 进入步骤6时生成预览数据
      if (next === 6) {
        this.generatePreview();
      }
    }
  },

  goPrev() {
    if (this.data.currentStep > 1) {
      const prev = this.data.currentStep - 1;
      this.setData({
        currentStep: prev,
        progressPercent: (prev / this.data.totalSteps) * 100
      });
    }
  },

  goToStep(e) {
    const step = parseInt(e.currentTarget.dataset.step);
    if (step < this.data.currentStep) {
      this.setData({
        currentStep: step,
        progressPercent: (step / this.data.totalSteps) * 100
      });
    }
  },

  // ===== 表单验证 =====
  validateStep(step) {
    const errors = {};
    switch (step) {
      case 1:
        if (!this.data.name.trim()) errors.name = '请输入姓名';
        if (!this.data.company.trim()) errors.company = '请输入公司名称';
        break;
      case 2:
        if (!this.data.phone.trim()) errors.phone = '请输入手机号';
        break;
      case 3:
        // 产品验证可选，至少提示
        break;
      case 4:
        if (!this.data.needTitle.trim()) errors.needTitle = '请输入需求标题';
        if (!this.data.needDesc.trim()) errors.needDesc = '请输入需求描述';
        break;
    }
    this.setData({ fieldErrors: errors });
    if (Object.keys(errors).length > 0) {
      const firstError = Object.values(errors)[0];
      wx.showToast({ title: firstError, icon: 'none' });
      return false;
    }
    return true;
  },

  // ===== 字段更新 =====
  onFieldChange(e) {
    const field = e.currentTarget.dataset.field;
    const value = e.detail.value;
    this.setData({ [field]: value });
    // 清除该字段错误
    if (this.data.fieldErrors[field]) {
      const errors = { ...this.data.fieldErrors };
      delete errors[field];
      this.setData({ fieldErrors: errors });
    }
  },

  // ===== Step 1: 头像选择 =====
  onChooseAvatar() {
    const self = this;
    wx.chooseMedia({
      count: 1,
      mediaType: ['image'],
      sourceType: ['album', 'camera'],
      sizeType: ['compressed'],
      success(res) {
        const tempPath = res.tempFiles[0].tempFilePath;
        // 上传头像
        wx.showLoading({ title: '上传中...' });
        wx.uploadFile({
          url: api.BASE_URL + '/api/v1/upload/avatar',
          filePath: tempPath,
          name: 'file',
          header: {
            'Authorization': 'Bearer ' + (wx.getStorageSync('token') || '')
          },
          success(resp) {
            wx.hideLoading();
            try {
              const data = JSON.parse(resp.data);
              const url = data.url || data.data?.url || data.data?.path || '';
              if (url) {
                self.setData({ avatar: url });
              } else {
                // 如果上传失败，临时用本地路径
                self.setData({ avatar: tempPath });
              }
            } catch (e) {
              self.setData({ avatar: tempPath });
            }
          },
          fail() {
            wx.hideLoading();
            self.setData({ avatar: tempPath });
            wx.showToast({ title: '上传失败，已使用本地图片', icon: 'none' });
          }
        });
      }
    });
  },

  // ===== Step 3: 产品管理 =====
  onAddProduct() {
    const products = [...this.data.products];
    products.push({
      id: 'temp_' + Date.now(),
      name: '',
      price: '',
      description: '',
      image: ''
    });
    this.setData({ products });
  },

  onRemoveProduct(e) {
    const index = e.currentTarget.dataset.index;
    const products = [...this.data.products];
    products.splice(index, 1);
    this.setData({ products });
  },

  onProductFieldChange(e) {
    const index = e.currentTarget.dataset.index;
    const field = e.currentTarget.dataset.field;
    const value = e.detail.value;
    const products = [...this.data.products];
    products[index] = { ...products[index], [field]: value };
    this.setData({ products });
  },

  onChooseProductImage(e) {
    const self = this;
    const index = e.currentTarget.dataset.index;
    wx.chooseMedia({
      count: 1,
      mediaType: ['image'],
      sourceType: ['album'],
      sizeType: ['compressed'],
      success(res) {
        const tempPath = res.tempFiles[0].tempFilePath;
        wx.showLoading({ title: '上传中...' });
        wx.uploadFile({
          url: api.BASE_URL + '/api/v1/upload/product',
          filePath: tempPath,
          name: 'file',
          header: {
            'Authorization': 'Bearer ' + (wx.getStorageSync('token') || '')
          },
          success(resp) {
            wx.hideLoading();
            try {
              const data = JSON.parse(resp.data);
              const url = data.url || data.data?.url || data.data?.path || '';
              const products = [...self.data.products];
              products[index] = { ...products[index], image: url || tempPath };
              self.setData({ products });
            } catch (e) {
              const products = [...self.data.products];
              products[index] = { ...products[index], image: tempPath };
              self.setData({ products });
            }
          },
          fail() {
            wx.hideLoading();
            const products = [...self.data.products];
            products[index] = { ...products[index], image: tempPath };
            self.setData({ products });
            wx.showToast({ title: '上传失败，已使用本地图片', icon: 'none' });
          }
        });
      }
    });
  },

  // ===== Step 4: 供需类型切换 =====
  onNeedTypeChange(e) {
    this.setData({ needType: e.currentTarget.dataset.type });
  },

  // ===== Step 5: 信任网络搜索 =====
  onSearchInput(e) {
    const keyword = e.detail.value;
    this.setData({ searchKeyword: keyword });
    if (keyword.trim().length < 2) {
      this.setData({ searchResults: [], showSearchResults: false });
      return;
    }
    if (this._searchTimer) clearTimeout(this._searchTimer);
    this._searchTimer = setTimeout(() => {
      this.searchUsers(keyword.trim());
    }, 300);
  },

  onSearchConfirm() {
    const keyword = this.data.searchKeyword.trim();
    if (keyword.length >= 2) {
      this.searchUsers(keyword);
    }
  },

  searchUsers(keyword) {
    const self = this;
    api.request('/api/v1/users/search', {
      data: { keyword }
    })
      .then(res => {
        const results = res.data || res.data?.list || [];
        const trustIds = self.data.trustList.map(t => t.id || t.user_id);
        const filtered = results.filter(u => !trustIds.includes(u.id || u.user_id));
        self.setData({
          searchResults: filtered,
          showSearchResults: true
        });
      })
      .catch(err => {
        console.error('搜索用户失败:', err);
        wx.showToast({ title: '搜索失败', icon: 'none' });
      });
  },

  addTrust(e) {
    const self = this;
    const user = e.currentTarget.dataset.user;
    if (!user || !(user.id || user.user_id)) return;

    wx.showLoading({ title: '添加中...' });
    api.request('/api/v1/trust/add', {
      method: 'POST',
      data: { targetUserId: user.id || user.user_id }
    })
      .then(res => {
        wx.hideLoading();
        wx.showToast({ title: '已添加信任', icon: 'success' });
        const results = self.data.searchResults.filter(u => (u.id || u.user_id) !== (user.id || user.user_id));
        self.setData({
          trustList: [...self.data.trustList, user],
          searchResults: results
        });
      })
      .catch(err => {
        wx.hideLoading();
        wx.showToast({ title: '添加失败', icon: 'none' });
        console.error('添加信任失败:', err);
      });
  },

  removeTrust(e) {
    const self = this;
    const item = e.currentTarget.dataset.item;
    const index = e.currentTarget.dataset.index;

    wx.showModal({
      title: '移除信任',
      content: '确定要移除对 ' + (item.name || '该用户') + ' 的信任吗？',
      success: (res) => {
        if (res.confirm) {
          wx.showLoading({ title: '移除中...' });
          api.request('/api/v1/trust/remove', {
            method: 'POST',
            data: { targetUserId: item.id || item.user_id }
          })
            .then(() => {
              wx.hideLoading();
              wx.showToast({ title: '已移除', icon: 'success' });
              const list = [...self.data.trustList];
              list.splice(index, 1);
              self.setData({ trustList: list });
            })
            .catch(err => {
              wx.hideLoading();
              wx.showToast({ title: '移除失败', icon: 'none' });
              console.error('移除信任失败:', err);
            });
        }
      }
    });
  },

  // ===== Step 6: 预览数据处理 =====
  generatePreview() {
    this.setData({
      previewData: {
        name: this.data.name,
        avatar: this.data.avatar,
        company: this.data.company,
        position: this.data.position,
        bio: this.data.bio,
        phone: this.data.phone,
        wechat: this.data.wechat,
        email: this.data.email,
        products: this.data.products,
        need: {
          type: this.data.needType,
          title: this.data.needTitle,
          desc: this.data.needDesc,
          tags: this.data.needTags,
          image: this.data.needImage
        },
        trustList: this.data.trustList,
        trustCount: this.data.trustList.length
      }
    });
  },

  // ===== 发布 =====
  onSubmit() {
    const self = this;
    const user = wx.getStorageSync('user') || wx.getStorageSync('userInfo');
    let userId = user?.id || user?.user_id || '';

    if (!userId) {
      wx.showToast({ title: '用户信息丢失，请重新登录', icon: 'none' });
      return;
    }

    // 最后一步验证
    if (!this.data.name.trim() || !this.data.company.trim()) {
      wx.showToast({ title: '请完善基本信息', icon: 'none' });
      this.setData({ currentStep: 1, progressPercent: 16.67 });
      return;
    }

    const payload = {
      name: this.data.name.trim(),
      avatar: this.data.avatar,
      company: this.data.company.trim(),
      position: this.data.position.trim(),
      bio: this.data.bio.trim(),
      phone: this.data.phone.trim(),
      wechat: this.data.wechat.trim(),
      email: this.data.email.trim(),
      products: this.data.products.map(p => ({
        name: p.name,
        price: p.price,
        description: p.description,
        image: p.image
      })),
      need_type: this.data.needType,
      need_title: this.data.needTitle.trim(),
      need_desc: this.data.needDesc.trim(),
      need_tags: this.data.needTags.trim(),
      need_image: this.data.needImage,
      trust_list: this.data.trustList.map(t => ({
        id: t.id || t.user_id,
        name: t.name,
        avatar: t.avatar,
        company: t.company
      }))
    };

    self.setData({ submitting: true });

    api.request('/api/v1/brochures/' + userId, {
      method: 'PUT',
      data: payload
    })
      .then(res => {
        self.setData({ submitting: false });
        wx.showToast({ title: '发布成功！', icon: 'success', duration: 2000 });
        setTimeout(() => {
          // 返回画册首页
          wx.navigateBack({
            delta: 1,
            fail() {
              wx.redirectTo({ url: '/pages/brochure/index' });
            }
          });
        }, 1500);
      })
      .catch(err => {
        self.setData({ submitting: false });
        wx.showToast({ title: err.message || '发布失败，请重试', icon: 'none' });
      });
  }
});
