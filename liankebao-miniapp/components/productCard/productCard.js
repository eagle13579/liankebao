Component({
  properties: {
    product: Object
  },

  data: {
    img: '',
    name: '',
    price: 0,
    earn: 0
  },

  observers: {
    'product': function(product) {
      if (product) {
        const imgs = JSON.parse(product.images || '[]')
        this.setData({
          img: imgs[0] || '',
          name: product.name,
          price: product.price,
          earn: product.earn_per_share || 0
        })
      }
    }
  },

  methods: {
    handleClick() {
      wx.navigateTo({ url: '/pages/product/index?id=' + this.data.product.id })
    }
  }
})
