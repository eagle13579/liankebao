import { Component } from 'react'
import { View, Text } from '@tarojs/components'
import Taro from '@tarojs/taro'
import './NavBar.scss'

interface NavBarProps {
  title: string
  showBack?: boolean
  rightContent?: React.ReactNode
  onBack?: () => void
}

export default class NavBar extends Component<NavBarProps> {
  handleBack = () => {
    if (this.props.onBack) {
      this.props.onBack()
    } else {
      Taro.navigateBack()
    }
  }

  render() {
    const { title, showBack, rightContent } = this.props
    return (
      <View className='navbar glass'>
        <View className='navbar-left'>
          {showBack && (
            <Text className='navbar-back' onClick={this.handleBack}>
              ‹ 返回
            </Text>
          )}
        </View>
        <Text className='navbar-title'>{title}</Text>
        <View className='navbar-right'>{rightContent}</View>
      </View>
    )
  }
}
