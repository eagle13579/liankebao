// pages/brochure-qrcode/index.js
// 画册二维码页面 - 生成、保存及分享画册二维码

const api = require('../../utils/api');

Page({
  data: {
    qrcodeUrl: '',
    brochureTitle: '',
    brochureId: '',
    stats: null,
    loading: false
  },

  onLoad(options) {
    const { id } = options;
    if (id) {
      this.setData({ brochureId: id });
      this.loadQrcode(id);
      this.loadStats(id);
    } else {
      // 从本地存储获取最近浏览的画册
      const lastBrochure = wx.getStorageSync('lastBrochure');
      if (lastBrochure) {
        this.setData({
          brochureId: lastBrochure.id,
          brochureTitle: lastBrochure.title
        });
        this.loadQrcode(lastBrochure.id);
        this.loadStats(lastBrochure.id);
      }
    }
  },

  onShow() {
    if (this.data.brochureId) {
      this.loadStats(this.data.brochureId);
    }
  },

  loadQrcode(id) {
    this.setData({ loading: true });
    api.request('/api/v1/brochure/' + id + '/qrcode')
      .then(res => {
        this.setData({
          qrcodeUrl: res.data.url || res.data,
          brochureTitle: res.data.title || this.data.brochureTitle || '我的画册',
          loading: false
        });
      })
      .catch(err => {
        console.error('加载二维码失败:', err);
        wx.showToast({ title: '加载失败', icon: 'none' });
        this.setData({ loading: false });
      });
  },

  loadStats(id) {
    api.request('/api/v1/brochure/' + id + '/stats')
      .then(res => {
        this.setData({ stats: res.data });
      })
      .catch(err => {
        console.error('加载统计失败:', err);
      });
  },

  saveToAlbum() {
    const that = this;
    if (!this.data.qrcodeUrl) {
      wx.showToast({ title: '二维码未加载', icon: 'none' });
      return;
    }
    // 先下载图片到本地临时文件
    wx.downloadFile({
      url: this.data.qrcodeUrl,
      success(res) {
        if (res.statusCode === 200) {
          wx.saveImageToPhotosAlbum({
            filePath: res.tempFilePath,
            success() {
              wx.showToast({ title: '已保存到相册', icon: 'success' });
              // 上报保存事件
              if (that.data.brochureId) {
                api.request('/api/v1/brochure/' + that.data.brochureId + '/stats/action', {
                  method: 'POST',
                  data: { action: 'save' }
                }).catch(() => {});
              }
            },
            fail(err) {
              if (err.errMsg.indexOf('auth deny') > -1) {
                wx.showModal({
                  title: '提示',
                  content: '需要您授权保存到相册',
                  success: (modal) => {
                    if (modal.confirm) {
                      wx.openSetting();
                    }
                  }
                });
              } else {
                wx.showToast({ title: '保存失败', icon: 'none' });
              }
            }
          });
        }
      },
      fail() {
        wx.showToast({ title: '下载失败', icon: 'none' });
      }
    });
  },

  shareBrochure() {
    // 转发给好友 - 通过按钮的 open-type="share" 触发
    // 此方法用于手动触发分享统计上报
    if (this.data.brochureId) {
      api.request('/api/v1/brochure/' + this.data.brochureId + '/stats/action', {
        method: 'POST',
        data: { action: 'share' }
      }).catch(() => {});
    }
  },

  onShareAppMessage() {
    return {
      title: this.data.brochureTitle || '我的电子画册',
      path: '/pages/brochure-qrcode/index?id=' + this.data.brochureId,
      imageUrl: this.data.qrcodeUrl
    };
  }
});
