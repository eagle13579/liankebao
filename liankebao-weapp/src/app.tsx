import { Component } from 'react'
import { View } from '@tarojs/components'
import './app.scss'

class App extends Component {
  componentDidMount() {}

  componentDidShow() {}

  componentDidHide() {}

  render() {
    return <View>{this.props.children}</View>
  }
}

export default App
