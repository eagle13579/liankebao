// utils/api.js
// 链客宝小程序 API 请求封装

const BASE_URL = 'https://api.liankebao.com';

function request(url, options = {}) {
  const token = wx.getStorageSync('token');
  const header = {
    'Content-Type': 'application/json'
  };
  if (token) {
    header['Authorization'] = 'Bearer ' + token;
  }

  return new Promise((resolve, reject) => {
    wx.request({
      url: url.startsWith('http') ? url : BASE_URL + url,
      method: options.method || 'GET',
      data: options.data || {},
      header: Object.assign(header, options.header || {}),
      success(res) {
        if (res.statusCode === 401) {
          // Token过期，跳转登录
          wx.removeStorageSync('token');
          wx.removeStorageSync('userInfo');
          wx.redirectTo({ url: '/pages/auth/login' });
          reject(new Error('未授权'));
          return;
        }
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res.data);
        } else {
          reject(new Error(res.data?.message || '请求失败'));
        }
      },
      fail(err) {
        reject(err);
      }
    });
  });
}

module.exports = {
  request
};
