# 需求原点定位 P0 功能实现

## 概述
在注册流程中增加「你的核心痛点是什么」3选1选择器，实现需求原点定位，据此引导onboarding路径和首页推荐顺序。

## 改动清单

### 后端 (backend/app/)
| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `models.py` | 修改 | User模型新增 `onboarding_pain_point` (String, nullable) 字段 |
| `schemas.py` | 修改 | UserResponse新增 `onboarding_pain_point` 字段；新增 `OnboardingPreferenceRequest` schema |
| `routers/onboarding.py` | **新增** | POST `/api/auth/onboarding-preference` 保存用户痛点选择 |
| `routers/recommend.py` | 修改 | 新增 GET `/api/recommend/features` 基于痛点返回首页功能排序 |
| `main.py` | 修改 | 注册 `onboarding` 路由模块 |

### 前端 (src/)
| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `components/OnboardingPainSelector.tsx` | **新增** | 痛点三选一组件（emoji+标题+描述），含 `getFeaturePriorityByPainPoint` 和 `getOnboardingRedirect` 工具函数 |
| `screens/AuthScreens.tsx` | 修改 | 集成痛点选择器；注册成功后自动保存痛点偏好并引导跳转 |
| `screens/MainScreens.tsx` | 修改 | 首页功能卡片根据 `/api/recommend/features` 响应动态排序 |

## 痛点选项与引导路径
| 痛点 | 标签 | 注册后引导 |
|------|------|-----------|
| 📉 获客成本太高 | `low_acquisition_cost` | `/product-pool`（推荐任务） |
| 🛡️ 缺信任背书难成交 | `lack_trust` | `/supply-demand`（企业信任网络） |
| 🔄 分销结算太麻烦 | `distribution_pain` | `/promotion-center`（发布任务→邀请伙伴） |

## 数据库迁移
需要执行:
```sql
ALTER TABLE users ADD COLUMN onboarding_pain_point VARCHAR(50) NULL;
```

## 测试验证
- [x] 后端 schemas 验证: pattern r"^(low_acquisition_cost|lack_trust|distribution_pain)$"
- [x] 后端所有 .py 语法检查通过
- [x] 前端组件可独立使用
- [x] 注册流程正常: 表单 → 角色选择 → 痛点选择 → 注册成功 → 引导跳转
