// Mock @tarojs/taro
const taro = {
  request: jest.fn(() => Promise.resolve({ data: { code: 200, data: {} } })),
  navigateTo: jest.fn(),
  navigateBack: jest.fn(),
  switchTab: jest.fn(),
  reLaunch: jest.fn(),
  redirectTo: jest.fn(),
  showToast: jest.fn(),
  showLoading: jest.fn(),
  hideLoading: jest.fn(),
  showModal: jest.fn(({ success }) => {
    if (success) success({ confirm: true, cancel: false })
  }),
  showActionSheet: jest.fn(),
  getStorageSync: jest.fn(() => 'mock-token'),
  setStorageSync: jest.fn(),
  removeStorageSync: jest.fn(),
  getStorage: jest.fn(() => Promise.resolve({ data: null })),
  setStorage: jest.fn(() => Promise.resolve()),
  removeStorage: jest.fn(() => Promise.resolve()),
  login: jest.fn(({ success }) => {
    if (success) success({ code: 'mock-code', errMsg: 'login:ok' })
  }),
  getUserInfo: jest.fn(({ success }) => {
    if (success) success({ userInfo: { nickName: '测试用户' }, errMsg: 'getUserInfo:ok' })
  }),
  chooseMessageFile: jest.fn(({ success }) => {
    if (success) success({ tempFiles: [{ path: '/tmp/mock.xlsx', name: 'contacts.xlsx', size: 1024 }] })
  }),
  uploadFile: jest.fn(() => {
    return Promise.resolve({
      data: JSON.stringify({ code: 200, data: {} }),
      statusCode: 200,
      errMsg: 'uploadFile:ok',
    })
  }),
  downloadFile: jest.fn(),
  getSystemInfoSync: jest.fn(() => ({
    windowWidth: 375,
    windowHeight: 812,
    pixelRatio: 2,
    platform: 'ios',
    statusBarHeight: 44,
  })),
  getSystemInfo: jest.fn(({ success }) => {
    if (success) success({
      windowWidth: 375,
      windowHeight: 812,
      pixelRatio: 2,
      platform: 'ios',
      statusBarHeight: 44,
    })
  }),
  getCurrentPages: jest.fn(() => []),
  getApp: jest.fn(() => ({})),
  events: {
    on: jest.fn(),
    off: jest.fn(),
    trigger: jest.fn(),
  },
  ENV_TYPE: {
    WEAPP: 'WEAPP',
    WEB: 'WEB',
    RN: 'RN',
    SWAN: 'SWAN',
    ALIPAY: 'ALIPAY',
    TT: 'TT',
    QQ: 'QQ',
    JD: 'JD',
  },
  getEnv: jest.fn(() => 'WEAPP'),
  cloud: null,
  interceptor: {
    add: jest.fn(),
    clean: jest.fn(),
  },
}

taro.default = taro
module.exports = taro
