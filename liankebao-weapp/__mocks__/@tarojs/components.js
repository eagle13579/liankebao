const React = require('react')

// Mock @tarojs/components — provide minimal React component stubs for all Taro components
const componentCache = {}

const createTaroComponent = (name) => {
  if (!componentCache[name]) {
    componentCache[name] = React.forwardRef((props, ref) => {
      const { children, className, style, ...rest } = props
      return React.createElement(
        'view',
        { ...rest, ref, className, style, 'data-taro-component': name },
        children
      )
    })
    componentCache[name].displayName = name
  }
  return componentCache[name]
}

// All Taro components used across the app
const componentNames = [
  'View', 'Text', 'ScrollView', 'Input', 'Image', 'Button', 'Swiper',
  'SwiperItem', 'Icon', 'RichText', 'Picker', 'Checkbox', 'Radio',
  'Switch', 'Slider', 'Form', 'Label', 'Progress', 'MovableView',
  'MovableArea', 'CoverView', 'CoverImage', 'Navigator', 'Audio',
  'Camera', 'Video', 'LivePlayer', 'LivePusher', 'Map', 'Canvas',
  'OpenData', 'WebView', 'Ad', 'OfficialAccount', 'FunctionalPageNavigator',
  'Editor', 'MatchMedia', 'PageContainer', 'RootPortal', 'ShareElement',
  'KeyboardAccessory', 'VoipRoom', 'AdCustom', 'NavigationBar',
  'TabBar', 'TabItem', 'StickyHeader', 'StickySection',
]

const namedExports = {}
for (const name of componentNames) {
  namedExports[name] = createTaroComponent(name)
}

module.exports = namedExports
