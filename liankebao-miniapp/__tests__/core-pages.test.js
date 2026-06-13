/**
 * 链客宝AI原生微信小程序 - 核心页面测试
 *
 * 使用 miniprogram-simulate + Jest 进行页面渲染测试
 */

const path = require('path');
const { loadPage, renderPage } = require('./helpers');

const PROJECT_ROOT = path.resolve(__dirname, '..');

describe('首页 (pages/index)', () => {
  let compId;
  let comp;

  beforeAll(() => {
    compId = loadPage(path.join(PROJECT_ROOT, 'pages/index/index'));
    comp = renderPage(compId);
  });

  test('页面能够成功加载并渲染', () => {
    expect(compId).toBeTruthy();
    expect(typeof compId).toBe('string');
    expect(comp).toBeTruthy();
  });

  test('data 包含默认初始值', () => {
    expect(comp.data.products).toEqual([]);
    expect(comp.data.recommendProducts).toEqual([]);
    expect(comp.data.banners).toHaveLength(3);
    expect(comp.data.loading).toBe(true);
  });

  test('页面实例的方法存在于 instance 上', () => {
    const inst = comp.instance;
    // 检查 instance 对象上有哪些 key
    const methodKeys = ['goPool', 'goDetail', 'goAIDiagnosis', 'goAICard', 'loadData', 'goPoolWithCat'];
    for (const key of methodKeys) {
      expect(typeof inst[key]).toBe('function');
    }
  });

  test('setData 能正确更新数据', () => {
    expect(comp.data.loading).toBe(true);
    comp.setData({ loading: false });
    expect(comp.data.loading).toBe(false);
    comp.setData({ loading: true });
    expect(comp.data.loading).toBe(true);
  });
});

describe('产品池 (pages/pool)', () => {
  let compId;
  let comp;

  beforeAll(() => {
    compId = loadPage(path.join(PROJECT_ROOT, 'pages/pool/index'));
    comp = renderPage(compId);
  });

  test('页面能够成功加载并渲染', () => {
    expect(compId).toBeTruthy();
    expect(comp).toBeTruthy();
  });

  test('data 包含默认初始值', () => {
    expect(comp.data.products).toEqual([]);
    expect(comp.data.keyword).toBe('');
    expect(comp.data.currentCategory).toBe('');
    expect(comp.data.categories).toEqual([
      'AI名片', 'GEO诊断', '数字分身', '营销工具', '企业服务', '其他'
    ]);
    expect(comp.data.hasMore).toBe(true);
    expect(comp.data.loading).toBe(false);
    expect(comp.data.page).toBe(1);
    expect(comp.data.pageSize).toBe(20);
  });

  test('页面实例的方法存在于 instance 上', () => {
    const inst = comp.instance;
    const methodKeys = ['selectCategory', 'clearSearch', 'loadProducts', 'loadMore', 'onSearchInput', 'onSearch', 'goDetail'];
    for (const key of methodKeys) {
      expect(typeof inst[key]).toBe('function');
    }
  });
});

describe('我的 (pages/mine)', () => {
  let compId;
  let comp;

  beforeAll(() => {
    compId = loadPage(path.join(PROJECT_ROOT, 'pages/mine/index'));
    comp = renderPage(compId);
  });

  test('页面能够成功加载并渲染', () => {
    expect(compId).toBeTruthy();
    expect(comp).toBeTruthy();
  });

  test('data 包含默认初始值（未登录状态）', () => {
    expect(comp.data.user).toBeNull();
    expect(comp.data.isLoggedIn).toBe(false);
    expect(comp.data.userName).toBe('未登录');
    expect(comp.data.userInitial).toBe('?');
    expect(comp.data.userRole).toBe('普通用户');
    expect(comp.data.isPromoter).toBe(false);
    expect(comp.data.isSupplier).toBe(false);
    expect(comp.data.unreadCount).toBe(0);
  });

  test('页面实例的方法存在于 instance 上', () => {
    const inst = comp.instance;
    const methodKeys = ['goOrders', 'goNotifications', 'goPartnerPolicy', 'handleLogout', 'loadUser', 'loadUnreadCount'];
    for (const key of methodKeys) {
      expect(typeof inst[key]).toBe('function');
    }
  });
});
