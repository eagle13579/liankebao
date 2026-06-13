// components/emptyState/emptyState.js
Component({
  properties: {
    icon: { type: String, value: '📭' },
    title: { type: String, value: '暂无内容' },
    desc: { type: String, value: '' },
    btnText: { type: String, value: '' }
  },
  methods: {
    onAction: function() {
      this.triggerEvent('action')
    }
  }
})
