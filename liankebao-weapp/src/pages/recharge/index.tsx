import { Component } from 'react'
import { View, Text, ScrollView, Input, Button } from '@tarojs/components'
import { api } from '../../api/client'
import Taro from '@tarojs/taro'
import './index.scss'

const PRESET_AMOUNTS = [50, 100, 200, 500, 1000]

interface RechargeState {
  balanceData: any | null
  loading: boolean
  error: string
  selectedAmount: number | null
  customAmount: string
  loadError: string
}

export default class RechargeIndex extends Component<{}, RechargeState> {
  state: RechargeState = {
    balanceData: null,
    loading: true,
    error: '',
    selectedAmount: null,
    customAmount: '',
    loadError: '',
  }

  componentDidMount() {
    this.fetchBalance()
  }

  fetchBalance = () => {
    this.setState({ loading: true, loadError: '' })
    api.get('/recharge/balance')
      .then((res: any) => {
        if (res.code === 200 && res.data) {
          this.setState({ balanceData: res.data, loading: false })
        } else {
          this.setState({ loadError: res.message || '加载失败', loading: false })
        }
      })
      .catch((e: any) => {
        this.setState({ loadError: e.message || '网络错误', loading: false })
      })
  }

  getAmount = (): number | null => {
    const { selectedAmount, customAmount } = this.state
    if (selectedAmount !== null) return selectedAmount
    if (customAmount) {
      const v = parseFloat(customAmount)
      if (!isNaN(v) && v > 0) return Math.round(v * 100) / 100
    }
    return null
  }

  handleConfirm = () => {
    const amount = this.getAmount()
    if (amount === null) {
      this.setState({ error: '请选择或输入充值金额' })
      return
    }
    if (amount > 999999.99) {
      this.setState({ error: '单次充值金额不能超过¥999,999.99' })
      return
    }
    this.setState({ error: '' })
    Taro.navigateTo({ url: `/pages/recharge/pay?amount=${amount.toFixed(2)}` })
  }

  handleCustomInput = (e: any) => {
    let v = e.detail.value
    if (!/^\d*\.?\d{0,2}$/.test(v)) return
    this.setState({ customAmount: v, selectedAmount: null, error: '' })
  }

  render() {
    const { balanceData, loading, error, selectedAmount, customAmount, loadError } = this.state

    if (loadError) {
      return (
        <View className='recharge'>
          <View className='header'>
            <Text className='header-back' onClick={() => Taro.navigateBack()}>←</Text>
            <Text className='header-title'>账户充值</Text>
          </View>
          <View className='error-state'>
            <Text className='error-icon'>⚠</Text>
            <Text className='error-text'>{loadError}</Text>
            <Text className='error-retry' onClick={this.fetchBalance}>点击重试</Text>
          </View>
        </View>
      )
    }

    return (
      <View className='recharge'>
        <View className='header'>
          <Text className='header-back' onClick={() => Taro.navigateBack()}>←</Text>
          <Text className='header-title'>账户充值</Text>
        </View>

        <ScrollView className='recharge-body' scrollY>
          {/* 余额卡片 */}
          <View className='balance-card'>
            <View className='balance-label'>
              <Text className='balance-icon'>💰</Text>
              <Text className='balance-label-text'>可用余额</Text>
            </View>
            {loading ? (
              <View className='balance-skeleton' />
            ) : (
              <Text className='balance-amount'>¥{(balanceData?.balance ?? 0).toFixed(2)}</Text>
            )}
            {balanceData && (
              <View className='balance-stats'>
                <Text className='balance-stat'>累计充值 ¥{balanceData.total_recharged?.toFixed(2) || '0.00'}</Text>
                <Text className='balance-stat'>累计消费 ¥{balanceData.total_consumed?.toFixed(2) || '0.00'}</Text>
              </View>
            )}
          </View>

          {/* 预设金额 */}
          <View className='section'>
            <Text className='section-title'>选择金额</Text>
            <View className='amount-grid'>
              {PRESET_AMOUNTS.map((amt) => (
                <View
                  key={amt}
                  className={`amount-btn ${selectedAmount === amt ? 'amount-btn-active' : ''}`}
                  onClick={() => this.setState({ selectedAmount: amt, customAmount: '', error: '' })}
                >
                  <Text>¥{amt}</Text>
                </View>
              ))}
            </View>
          </View>

          {/* 自定义金额 */}
          <View className='section'>
            <Text className='section-title'>自定义金额</Text>
            <View className='custom-input-wrap'>
              <Text className='custom-prefix'>¥</Text>
              <Input
                className='custom-input'
                type='digit'
                placeholder='输入充值金额'
                value={customAmount}
                onInput={this.handleCustomInput}
              />
            </View>
          </View>

          {error && <Text className='error-hint'>{error}</Text>}

          {/* 确认充值 */}
          <Button className='confirm-btn' onClick={this.handleConfirm}>
            确认充值
          </Button>

          {/* 快捷入口 */}
          <View className='quick-links'>
            <View className='quick-link' onClick={() => Taro.navigateTo({ url: '/pages/recharge/history' })}>
              <Text className='quick-link-text'>充值记录</Text>
              <Text className='quick-arrow'>›</Text>
            </View>
            <View className='quick-link' onClick={() => Taro.navigateTo({ url: '/pages/recharge/balance-logs' })}>
              <Text className='quick-link-text'>余额明细</Text>
              <Text className='quick-arrow'>›</Text>
            </View>
          </View>
        </ScrollView>
      </View>
    )
  }
}
