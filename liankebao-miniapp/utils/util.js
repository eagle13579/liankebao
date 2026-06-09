// 链客宝AI AI数字名片 工具函数

// 脱敏手机号: 138****8000
function maskPhone(phone) {
  if (!phone) return ''
  return phone.substring(0, 3) + '****' + phone.substring(phone.length - 4)
}

// 脱敏姓名: 张**
function maskName(name) {
  if (!name) return ''
  if (name.length <= 1) return name + '**'
  return name[0] + '**'
}

// 格式化时间
function formatTime(dateStr) {
  if (!dateStr) return ''
  var d = new Date(dateStr)
  var now = new Date()
  var diff = now - d

  if (diff < 60000) return '刚刚'
  if (diff < 3600000) return Math.floor(diff / 60000) + '分钟前'
  if (diff < 86400000) return Math.floor(diff / 3600000) + '小时前'
  if (diff < 172800000) return '昨天'

  var month = (d.getMonth() + 1).toString().padStart(2, '0')
  var day = d.getDate().toString().padStart(2, '0')
  return month + '-' + day
}

// 匹配度百分比转颜色
function matchColor(percent) {
  if (percent >= 85) return '#22c55e'
  if (percent >= 70) return '#eab308'
  return '#f97316'
}

// 安全解析JSON
function safeParse(str, defaultVal) {
  try { return JSON.parse(str) }
  catch(e) { return defaultVal || {} }
}

// 对象转URL参数
function objToParams(obj) {
  var parts = []
  for (var key in obj) {
    if (obj[key] !== undefined && obj[key] !== null && obj[key] !== '') {
      parts.push(encodeURIComponent(key) + '=' + encodeURIComponent(obj[key]))
    }
  }
  return parts.join('&')
}

module.exports = {
  maskPhone: maskPhone,
  maskName: maskName,
  formatTime: formatTime,
  matchColor: matchColor,
  safeParse: safeParse,
  objToParams: objToParams
}
