/**
 * 链客宝原生微信小程序测试辅助工具
 *
 * 提供 Page() 全局 polyfill，使 miniprogram-simulate 能加载页面文件
 * Page({...}) 的方法在顶层定义，jComponent 期望 methods 在 methods 键下，
 * 因此需要转换。
 */

const path = require('path');
const fs = require('fs');
const jComponent = require('j-component');
const simulate = require('miniprogram-simulate');

// 存储页面定义，供测试使用
const pageRegistry = {};

// 页面生命周期钩子，这些保留在顶层，其他顶层方法移入 methods
const PAGE_LIFECYCLE = [
  'onLoad', 'onShow', 'onReady', 'onHide', 'onUnload',
  'onPullDownRefresh', 'onReachBottom', 'onShareAppMessage',
  'onPageScroll', 'onResize', 'onTabItemTap',
];

/**
 * 加载一个微信小程序页面，返回可渲染的组件 ID
 *
 * @param {string} pageDir - 页面目录的绝对路径（如 /path/to/pages/index/index）
 * @returns {string} componentId - 可用于 simulate.render() 的组件 ID
 */
function loadPage(pageDir) {
  const jsPath = `${pageDir}.js`;
  const wxmlPath = `${pageDir}.wxml`;
  const jsonPath = `${pageDir}.json`;

  // 读取页面配置
  let pageJson = {};
  if (fs.existsSync(jsonPath)) {
    try {
      pageJson = JSON.parse(fs.readFileSync(jsonPath, 'utf-8'));
    } catch (e) {
      // ignore
    }
  }

  // 读取 WXML 模板
  let wxmlContent = '<view></view>';
  if (fs.existsSync(wxmlPath)) {
    wxmlContent = fs.readFileSync(wxmlPath, 'utf-8');
  }

  // 生成唯一的组件 ID 和标签名
  const pageName = path.basename(pageDir);
  const tagName = `page-${pageName}-${Date.now()}`;
  const compId = `comp_${tagName}`;

  // 设置 Page 全局函数，捕获页面定义
  let capturedOptions = null;
  global.Page = function(options) {
    capturedOptions = Object.assign({}, options);
  };

  // 确保 simulate 的全局 wx API 可用
  // (miniprogram-simulate/src/definition.js 在首次 import 时已注入 global.wx)

  // 执行页面 JS（这会调用 Page({...})）
  delete require.cache[require.resolve(jsPath)];
  require(jsPath);

  if (!capturedOptions) {
    throw new Error(`Page() was not called in ${jsPath}`);
  }

  // --- 转换 Page 定义 -> Component 定义 ---
  // Page 的方法在顶层，Component 的方法需要放在 methods 下
  const usingComponents = pageJson.usingComponents || {};
  const definition = {
    id: compId,
    tagName: tagName,
    template: wxmlContent,
    usingComponents: usingComponents,
    // 保留 data
    data: capturedOptions.data || {},
    // 保留 Page 生命周期钩子（jComponent 也支持 onLoad 等作为顶层）
    methods: {},
  };

  // 将顶层非生命周期的方法移入 methods
  for (const key of Object.keys(capturedOptions)) {
    if (key === 'data' || key === 'options' || key === 'behaviors') {
      // 这些保留在顶层
      definition[key] = capturedOptions[key];
    } else if (PAGE_LIFECYCLE.includes(key)) {
      // 生命周期方法保留在顶层
      definition[key] = capturedOptions[key];
    } else {
      // 其他方法移入 methods
      definition.methods[key] = capturedOptions[key];
    }
  }

  definition.options = Object.assign({
    classPrefix: tagName,
  }, definition.options || {});

  jComponent.register(definition);

  pageRegistry[compId] = { tagName, path: pageDir };

  return compId;
}

/**
 * 渲染已加载的页面组件
 */
function renderPage(compId) {
  return simulate.render(compId);
}

module.exports = {
  loadPage,
  renderPage,
  pageRegistry,
};
