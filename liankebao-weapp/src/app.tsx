import { Component, ReactNode } from 'react'
import { View } from '@tarojs/components'
import './app.scss'

interface AppProps {
  children?: ReactNode
}

class App extends Component<AppProps> {
  componentDidMount() {}

  componentDidShow() {}

  componentDidHide() {}

  render() {
    return <View>{this.props.children}</View>
  }
}

export default App
