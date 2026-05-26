# react-bits 组件注入清单

## 概述
从 react-bits 精华库注入到本项目的组件。

## 组件列表

### BorderGlow (P0)
- 分类: Components
- 依赖: 无
- 文件: BorderGlow.jsx, BorderGlow.css
- 说明: 纯CSS边框辉光，零依赖，鼠标跟随

导入:
```tsx
import BorderGlow from '../components/BorderGlow';
```

### SpotlightCard (P0)
- 分类: Components
- 依赖: 无
- 文件: SpotlightCard.jsx, SpotlightCard.css
- 说明: 鼠标跟随聚光卡片，零依赖

导入:
```tsx
import SpotlightCard from '../components/SpotlightCard';
```

### Counter (P0)
- 分类: Components
- 依赖: motion
- 文件: Counter.jsx, Counter.css
- 说明: 数字计数器弹簧动画，适合KPI展示

导入:
```tsx
import Counter from '../components/Counter';
```

### DecryptedText (P1)
- 分类: TextAnimations
- 依赖: motion
- 文件: DecryptedText.jsx
- 说明: 文字解密效果，交互触发

导入:
```tsx
import DecryptedText from '../components/DecryptedText';
```

### Dock (P1)
- 分类: Components
- 依赖: motion
- 文件: Dock.jsx, Dock.css
- 说明: macOS停靠栏风格导航，弹簧动画

导入:
```tsx
import Dock from '../components/Dock';
```

### Carousel (P1)
- 分类: Components
- 依赖: motion, react-icons
- 文件: Carousel.jsx, Carousel.css
- 说明: 手势拖拽轮播，需安装 react-icons

导入:
```tsx
import Carousel from '../components/Carousel';
```

### SplashCursor (P2)
- 分类: Animations
- 依赖: 无
- 文件: SplashCursor.jsx
- 说明: WebGL流体鼠标轨迹，GPU加速，1087行

导入:
```tsx
import SplashCursor from '../components/SplashCursor';
```

## 注意事项
1. JSX 组件需要 tsconfig 允许 JSX
2. CSS 文件随组件一并复制
3. motion 组件需要 framer-motion v12+ (已安装)
4. 零依赖组件可直接使用
