import { Component } from 'react'
import { View, Text, ScrollView } from '@tarojs/components'
import { api } from '../../api/client'
import Taro from '@tarojs/taro'
import './index.scss'

interface ImportRecord {
  id: number
  filename: string
  total: number
  success: number
  failed: number
  status: string
  created_at: string
}

interface ImportsState {
  records: ImportRecord[]
  loading: boolean
  error: string
}

export default class ImportsIndex extends Component<{}, ImportsState> {
  state: ImportsState = {
    records: [],
    loading: true,
    error: '',
  }

  componentDidMount() {
    this.fetchRecords()
  }

  fetchRecords = () => {
    this.setState({ loading: true, error: '' })

    api.get('/imports')
      .then((res: any) => {
        if (res.code === 200 && res.data) {
          this.setState({ records: res.data.items || [], loading: false })
        } else {
          this.setState({ error: res.message || '加载失败', loading: false })
        }
      })
      .catch((e: any) => {
        this.setState({ error: e.message || '网络错误', loading: false })
      })
  }

  handleImportFromWechat = () => {
    Taro.navigateTo({ url: '/pages/contacts/index' })
  }

  handleUploadFile = () => {
    Taro.chooseMessageFile({
      count: 1,
      type: 'file',
      extension: ['xlsx', 'xls', 'csv'],
      success: (res) => {
        const file = res.tempFiles[0]
        Taro.uploadFile({
          url: 'https://www.liankebao.com/api/imports/upload',
          filePath: file.path,
          name: 'file',
          header: {
            Authorization: `Bearer ${Taro.getStorageSync('token')}`,
          },
          success: (uploadRes) => {
            const data = JSON.parse(uploadRes.data)
            if (data.code === 200) {
              Taro.showToast({ title: '上传成功，正在导入', icon: 'success' })
              this.fetchRecords()
            } else {
              Taro.showToast({ title: data.message || '导入失败', icon: 'error' })
            }
          },
          fail: () => {
            Taro.showToast({ title: '上传失败', icon: 'error' })
          },
        })
      },
      fail: () => {},
    })
  }

  handleViewDetail = (id: number) => {
    Taro.navigateTo({ url: `/pages/imports/detail?id=${id}` })
  }

  getStatusText = (status: string): string => {
    const map: Record<string, string> = {
      pending: '处理中',
      processing: '导入中',
      completed: '已完成',
      failed: '导入失败',
      partial: '部分成功',
    }
    return map[status] || status
  }

  getStatusClass = (status: string): string => {
    if (status === 'completed') return 'ip-status-success'
    if (status === 'failed') return 'ip-status-failed'
    return 'ip-status-pending'
  }

  getStatusIcon = (status: string): string => {
    if (status === 'completed') return '✅'
    if (status === 'failed') return '❌'
    if (status === 'partial') return '⚠️'
    return '⏳'
  }

  render() {
    const { records, loading, error } = this.state

    return (
      <View className='imports-page'>
        {/* Header */}
        <View className='ip-header'>
          <Text className='ip-back' onClick={() => Taro.navigateBack()}>←</Text>
          <Text className='ip-title'>导入联系人</Text>
        </View>

        {/* Tips */}
        <View className='ip-tips'>
          <Text className='ip-tips-text'>
            💡 支持 .xlsx、.xls、.csv 格式文件，第一行为表头。必填列：姓名、电话
          </Text>
        </View>

        {/* Import Methods */}
        <View className='ip-methods'>
          <View className='ip-method-card' onClick={this.handleImportFromWechat}>
            <View className='ip-method-icon'>📱</View>
            <View className='ip-method-info'>
              <Text className='ip-method-name'>从微信好友导入</Text>
              <Text className='ip-method-desc'>导入微信聊天中的联系人信息</Text>
            </View>
            <Text className='ip-method-arrow'>›</Text>
          </View>

          <View className='ip-method-card' onClick={this.handleUploadFile}>
            <View className='ip-method-icon'>📄</View>
            <View className='ip-method-info'>
              <Text className='ip-method-name'>上传文件导入</Text>
              <Text className='ip-method-desc'>支持 Excel / CSV 文件批量导入</Text>
            </View>
            <Text className='ip-method-arrow'>›</Text>
          </View>

          <View className='ip-method-card' onClick={() => Taro.navigateTo({ url: '/pages/contacts/index' })}>
            <View className='ip-method-icon'>✏️</View>
            <View className='ip-method-info'>
              <Text className='ip-method-name'>手动添加</Text>
              <Text className='ip-method-desc'>逐个录入联系人信息</Text>
            </View>
            <Text className='ip-method-arrow'>›</Text>
          </View>
        </View>

        {/* History Section */}
        <Text className='ip-section-title'>导入记录</Text>

        <ScrollView className='ip-history-list' scrollY>
          {loading ? (
            <View className='ip-loading'>
              {[1, 2, 3].map((i) => (
                <View key={i} className='ip-skel-card'>
                  <View className='ip-skel-icon' />
                  <View className='ip-skel-body'>
                    <View className='ip-skel-line w-60' />
                    <View className='ip-skel-line w-40' />
                  </View>
                </View>
              ))}
            </View>
          ) : error ? (
            <View className='ip-error'>
              <Text className='ip-error-icon'>⚠</Text>
              <Text className='ip-error-text'>{error}</Text>
              <Text className='ip-error-retry' onClick={this.fetchRecords}>点击重试</Text>
            </View>
          ) : records.length === 0 ? (
            <View className='ip-empty'>
              <Text className='ip-empty-icon'>📂</Text>
              <Text className='ip-empty-text'>暂无导入记录</Text>
            </View>
          ) : (
            records.map((r) => (
              <View
                key={r.id}
                className='ip-history-card'
                onClick={() => this.handleViewDetail(r.id)}
              >
                <Text className='ip-history-icon'>{this.getStatusIcon(r.status)}</Text>
                <View className='ip-history-info'>
                  <Text className='ip-history-filename'>{r.filename || '批量导入'}</Text>
                  <Text className='ip-history-meta'>
                    {r.success || 0} 成功 · {r.failed || 0} 失败 · 共 {r.total || 0} 条
                  </Text>
                </View>
                <Text className={`ip-history-status ${this.getStatusClass(r.status)}`}>
                  {this.getStatusText(r.status)}
                </Text>
              </View>
            ))
          )}
        </ScrollView>
      </View>
    )
  }
}
