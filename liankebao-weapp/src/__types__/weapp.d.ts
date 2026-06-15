/// <reference types="@tarojs/taro" />

import 'react'

// Add $router to Component instances (Taro injects it)
declare module 'react' {
  interface Component {
    $router?: {
      params: Record<string, string | undefined>
      path: string
    }
  }
}
