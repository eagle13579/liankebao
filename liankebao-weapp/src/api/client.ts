import Taro from '@tarojs/taro'

const API_BASE = 'http://localhost:8003/api'

export const api = {
  get: (path: string) => request(path),
  post: (path: string, body: any) => request(path, { method: 'POST', data: body }),
  put: (path: string, body: any) => request(path, { method: 'PUT', data: body }),
}

async function request(path: string, options?: any) {
  const token = Taro.getStorageSync('token')
  const header: any = { 'Content-Type': 'application/json' }
  if (token) header['Authorization'] = `Bearer ${token}`
  try {
    const res = await Taro.request({ url: `${API_BASE}${path}`, header, ...options })
    return res.data
  } catch (e: any) {
    return { code: 500, message: e.errMsg || '网络错误' }
  }
}

export function loginWithWechat() {
  return new Promise((resolve, reject) => {
    Taro.login({
      success: (res) => {
        if (res.code) {
          api.post('/auth/wechat-login', { code: res.code }).then((data: any) => {
            if (data.code === 200) {
              Taro.setStorageSync('token', data.data.token)
              Taro.setStorageSync('user', data.data.user)
              resolve(data.data)
            } else reject(data.message)
          })
        } else reject('微信登录失败')
      },
      fail: reject,
    })
  })
}
