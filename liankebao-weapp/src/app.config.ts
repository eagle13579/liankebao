export default {
  pages: [
    'pages/index/index',
    'pages/card-match/index',
    'pages/mine/index',
    'pages/login/index',
    'pages/card-editor/index',
    'pages/brochure-preview/index',
  ],
  subpackages: [
    {
      root: 'pages/orders',
      name: 'orders',
      pages: ['index'],
    },
    {
      root: 'pages/recharge',
      name: 'recharge',
      pages: ['index'],
    },
    {
      root: 'pages/supply-demand',
      name: 'supplyDemand',
      pages: ['index'],
    },
    {
      root: 'pages/contacts',
      name: 'contacts',
      pages: ['index', 'detail'],
    },
    {
      root: 'pages/membership',
      name: 'membership',
      pages: ['index'],
    },
    {
      root: 'pages/notifications',
      name: 'notifications',
      pages: ['index'],
    },
    {
      root: 'pages/tutorial',
      name: 'tutorial',
      pages: ['index'],
    },
    {
      root: 'pages/promoter',
      name: 'promoter',
      pages: ['index'],
    },
    {
      root: 'pages/activities',
      name: 'activities',
      pages: ['index'],
    },
    {
      root: 'pages/admin',
      name: 'admin',
      pages: ['index'],
    },
    {
      root: 'pages/search',
      name: 'search',
      pages: ['index'],
    },
    {
      root: 'pages/imports',
      name: 'imports',
      pages: ['index'],
    },
  ],
  window: {
    navigationStyle: 'custom',
    backgroundColor: '#0f0c29',
    backgroundTextStyle: 'dark',
  },
  tabBar: {
    color: '#94a3b8',
    selectedColor: '#667eea',
    backgroundColor: '#0f172a',
    borderStyle: 'black',
    list: [
      {
        pagePath: 'pages/index/index',
        text: '名片',
        iconPath: 'images/tab_card.png',
        selectedIconPath: 'images/tab_card_active.png',
      },
      {
        pagePath: 'pages/card-match/index',
        text: '匹配',
        iconPath: 'images/tab_match.png',
        selectedIconPath: 'images/tab_match_active.png',
      },
      {
        pagePath: 'pages/mine/index',
        text: '我的',
        iconPath: 'images/tab_mine.png',
        selectedIconPath: 'images/tab_mine_active.png',
      },
    ],
  },
}
