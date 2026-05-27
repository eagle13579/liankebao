export default {
  pages: [
    'pages/index/index',
    'pages/login/index',
    'pages/product/index',
  ],
  subpackages: [
    {
      root: 'pages/orders',
      name: 'orders',
      pages: [
        'index',
      ],
    },
    {
      root: 'pages/mine',
      name: 'mine',
      pages: [
        'index',
      ],
    },
    {
      root: 'pages/recharge',
      name: 'recharge',
      pages: [
        'index',
      ],
    },
    {
      root: 'pages/supply-demand',
      name: 'supplyDemand',
      pages: [
        'index',
      ],
    },
    {
      root: 'pages/contacts',
      name: 'contacts',
      pages: [
        'index',
        'detail',
      ],
    },
    {
      root: 'pages/membership',
      name: 'membership',
      pages: [
        'index',
      ],
    },
    {
      root: 'pages/notifications',
      name: 'notifications',
      pages: [
        'index',
      ],
    },
    {
      root: 'pages/tutorial',
      name: 'tutorial',
      pages: [
        'index',
      ],
    },
  ],
  window: {
    navigationStyle: 'custom',
    backgroundColor: '#f5f5f5',
  },
}
