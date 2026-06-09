// ============================================================
// 链客宝AI API SDK — 由 scripts/generate_api_sdk.py 自动生成
// 生成时间: 2026-05-29T09:26:49.660501
// ============================================================

import { api } from "./client";

// ============================================================
// 数据类型
// ============================================================

export interface ActivityCreate {
  action_type: string;
  detail: string | null | undefined;
  summary: string | null | undefined;
}

export interface AdjustRequest {
  amount: number;
  remark: string | undefined;
  user_id: number;
}

export interface AliPayUnifiedOrderRequest {
  order_id: number;
  subject: string | null | undefined;
}

export interface ApiResponse {
  code: number | undefined;
  data: string | null | undefined;
  message: string | undefined;
}

export interface BusinessNeedCreate {
  budget: string | null | undefined;
  category: string | null | undefined;
  contact_name: string;
  contact_phone: string | null | undefined;
  description: string | null | undefined;
  region: string | null | undefined;
  title: string;
}

export interface BusinessNeedUpdate {
  budget: string | null | undefined;
  category: string | null | undefined;
  contact_name: string | null | undefined;
  contact_phone: string | null | undefined;
  description: string | null | undefined;
  region: string | null | undefined;
  status: string | null | undefined;
  title: string | null | undefined;
}

export interface ConfigUpdateRequest {
  value: string;
}

export interface ContactCreate {
  company: string | null | undefined;
  email: string | null | undefined;
  name: string;
  notes: string | null | undefined;
  phone: string | null | undefined;
  position: string | null | undefined;
  source: string | null | undefined;
  tags: string | null | undefined;
  wechat_id: string | null | undefined;
}

export interface ContactUpdate {
  company: string | null | undefined;
  email: string | null | undefined;
  name: string | null | undefined;
  notes: string | null | undefined;
  phone: string | null | undefined;
  position: string | null | undefined;
  source: string | null | undefined;
  tags: string | null | undefined;
  wechat_id: string | null | undefined;
}

export interface DuplicateInfo {
  match_type: string | undefined;
  matched_contact_id: number | null | undefined;
  matched_name: string | undefined;
  row_index: number;
  similarity_score: number | undefined;
}

export interface ImportConfirmRequest {
  batch_id: string;
  duplicates: DuplicateInfo[] | null | undefined;
  field_mapping: Record<string, string>;
  strategy: string | undefined;
}

export interface InvoiceApplyRequest {
  email: string | null | undefined;
  order_id: number;
  remark: string | null | undefined;
  tax_id: string | null | undefined;
  title: string;
}

export interface InvoiceReviewRequest {
  action: string;
  remark: string | null | undefined;
}

export interface LoginRequest {
  password: string;
  username: string;
}

export interface OrderCreate {
  product_id: number;
  promoter_id: number | null | undefined;
  quantity: number | undefined;
}

export interface OrderStatusRequest {
  status: string;
}

export interface PrecreateRequest {
  amount: number;
  platform: string | undefined;
}

export interface ProductCreate {
  brand: string | null | undefined;
  category: string | null | undefined;
  description: string | null | undefined;
  details: string | null | undefined;
  earn_per_share: number | undefined;
  files: string | null | undefined;
  images: string | null | undefined;
  is_featured: number | null | undefined;
  name: string;
  price: number | undefined;
  sale_price: number | null | undefined;
  sort_order: number | null | undefined;
  specs: string | null | undefined;
  stock: number | undefined;
  tags: string | null | undefined;
  video_url: string | null | undefined;
}

export interface ProductReviewRequest {
  action: string;
  reason: string | null | undefined;
}

export interface ProductUpdate {
  brand: string | null | undefined;
  category: string | null | undefined;
  description: string | null | undefined;
  details: string | null | undefined;
  earn_per_share: number | null | undefined;
  files: string | null | undefined;
  images: string | null | undefined;
  is_featured: number | null | undefined;
  name: string | null | undefined;
  price: number | null | undefined;
  sale_price: number | null | undefined;
  sort_order: number | null | undefined;
  specs: string | null | undefined;
  stock: number | null | undefined;
  tags: string | null | undefined;
  video_url: string | null | undefined;
}

export interface RefreshTokenRequest {
  refresh_token: string;
}

export interface RegisterRequest {
  company: string | null | undefined;
  name: string;
  password: string;
  phone: string | null | undefined;
  position: string | null | undefined;
  role: string | null | undefined;
  username: string;
}

export interface UpdateUserRoleRequest {
  role: string;
}

export interface WechatLoginRequest {
  code: string;
}

export interface WithdrawRequest {
  amount: number;
  bank_info: string | null | undefined;
}

export interface WxPayRefundRequest {
  order_id: number;
  reason: string | null | undefined;
}

export interface WxPayUnifiedOrderRequest {
  openid: string | null | undefined;
  order_id: number;
}

// ============================================================
// 分页响应包装
// ============================================================

export interface PaginatedResponse<T> {
  total: number;
  page: number;
  page_size: number;
  items: T[];
}

// ============================================================
// API 函数
// ============================================================

export interface ApiResult<T> {
  code: number;
  message: string;
  data?: T;
}

/**
 * Login
 * 用户登录（带频率限制）
 * POST /api/auth/login
 */
export async function login(data: LoginRequest): Promise<ApiResult<any>> {
  let path: string = `/api/auth/login`;
  return api.post<any>(path, data);
}

/**
 * Register
 * 用户注册（含手机号/邮箱格式校验、密码强度校验）
 * POST /api/auth/register
 */
export async function register(data: RegisterRequest): Promise<ApiResult<any>> {
  let path: string = `/api/auth/register`;
  return api.post<any>(path, data);
}

/**
 * Get Me
 * 获取当前用户信息
 * GET /api/auth/me
 */
export async function getCurrentUser(): Promise<ApiResult<any>> {
  let path: string = `/api/auth/me`;
  return api.get<any>(path);
}

/**
 * Refresh Token
 * 刷新access token（refresh token轮换）
 * POST /api/auth/refresh
 */
export async function refreshToken(data: RefreshTokenRequest): Promise<ApiResult<any>> {
  let path: string = `/api/auth/refresh`;
  return api.post<any>(path, data);
}

/**
 * Logout
 * 退出登录
 * POST /api/auth/logout
 */
export async function logout(): Promise<ApiResult<any>> {
  let path: string = `/api/auth/logout`;
  return api.post<any>(path, undefined);
}

/**
 * Wechat Login
 * 微信登录 - 通过code获取openid并登录/注册
 * POST /api/auth/wechat-login
 */
export async function wechatLogin(data: WechatLoginRequest): Promise<ApiResult<any>> {
  let path: string = `/api/auth/wechat-login`;
  return api.post<any>(path, data);
}

/**
 * List Products
 * 获取产品列表
 * GET /api/products
 */
export interface GetProductsParams {
  category?: string | undefined;
  status?: string | undefined;
  search?: string | undefined;
  page?: number | undefined;
  page_size?: number | undefined;
}

export async function getProducts(params?: GetProductsParams): Promise<ApiResult<any>> {
  let path: string = `/api/products`;
  const queryParts = [
    (params?.category !== undefined ? `category=${params!.category}` : ''),
    (params?.status !== undefined ? `status=${params!.status}` : ''),
    (params?.search !== undefined ? `search=${params!.search}` : ''),
    (params?.page !== undefined ? `page=${params!.page}` : ''),
    (params?.page_size !== undefined ? `page_size=${params!.page_size}` : '')
  ].filter(Boolean);
  if (queryParts.length > 0) {
    path += (path.includes('?') ? '&' : '?') + queryParts.join('&');
  }
  return api.get<any>(path);
}

/**
 * Create Product
 * 创建产品
 * POST /api/products
 */
export async function createProduct(data: ProductCreate): Promise<ApiResult<any>> {
  let path: string = `/api/products`;
  return api.post<any>(path, data);
}

/**
 * Get Product
 * 获取产品详情
 * GET /api/products/{product_id}
 */
export async function getProduct(product_id: string | number): Promise<ApiResult<any>> {
  let path: string = `/api/products/${product_id}`;
  return api.get<any>(path);
}

/**
 * Update Product
 * 更新产品（仅自己创建的产品）
 * PUT /api/products/{product_id}
 */
export async function updateProduct(product_id: string | number, data: ProductUpdate): Promise<ApiResult<any>> {
  let path: string = `/api/products/${product_id}`;
  return api.put<any>(path, data);
}

/**
 * Delete Product
 * 删除产品（仅自己创建的产品或管理员可操作）
 * DELETE /api/products/{product_id}
 */
export async function deleteProduct(product_id: string | number): Promise<ApiResult<any>> {
  let path: string = `/api/products/${product_id}`;
  return api.request<any>(path, { method: 'DELETE' });
}

/**
 * Get Orders
 * 获取订单列表（按角色过滤）
 * GET /api/orders
 */
export async function getOrders(): Promise<ApiResult<any>> {
  let path: string = `/api/orders`;
  return api.get<any>(path);
}

/**
 * Create Order
 * 创建订单并返回支付参数
 * POST /api/orders
 */
export async function createOrder(data: OrderCreate): Promise<ApiResult<any>> {
  let path: string = `/api/orders`;
  return api.post<any>(path, data);
}

/**
 * Update Order Status
 * 更新订单状态（按角色限制）
 * PUT /api/orders/{order_id}/status
 */
export async function updateOrderStatus(order_id: string | number, data: OrderStatusRequest): Promise<ApiResult<any>> {
  let path: string = `/api/orders/${order_id}/status`;
  return api.put<any>(path, data);
}

/**
 * Get Order
 * 获取订单详情
 * GET /api/orders/{order_id}
 */
export async function getOrder(order_id: string | number): Promise<ApiResult<any>> {
  let path: string = `/api/orders/${order_id}`;
  return api.get<any>(path);
}

/**
 * Get Earnings
 * 获取推广员收益
 * GET /api/promoter/earnings
 */
export async function getEarnings(): Promise<ApiResult<any>> {
  let path: string = `/api/promoter/earnings`;
  return api.get<any>(path);
}

/**
 * Withdraw
 * 发起提现
 * POST /api/promoter/withdraw
 */
export async function withdraw(data: WithdrawRequest): Promise<ApiResult<any>> {
  let path: string = `/api/promoter/withdraw`;
  return api.post<any>(path, data);
}

/**
 * Get Withdrawals
 * 获取提现记录
 * GET /api/promoter/withdrawals
 */
export async function getWithdrawals(): Promise<ApiResult<any>> {
  let path: string = `/api/promoter/withdrawals`;
  return api.get<any>(path);
}

/**
 * Get Dashboard
 * 获取管理后台数据看板
 * GET /api/admin/dashboard
 */
export async function getDashboard(): Promise<ApiResult<any>> {
  let path: string = `/api/admin/dashboard`;
  return api.get<any>(path);
}

/**
 * List Users
 * 获取用户列表
 * GET /api/admin/users
 */
export async function getAdminUsers(): Promise<ApiResult<any>> {
  let path: string = `/api/admin/users`;
  return api.get<any>(path);
}

/**
 * Update User Role
 * 管理员修改用户角色
 * PATCH /api/admin/users/{user_id}/role
 */
export async function updateUserRole(user_id: string | number, data: UpdateUserRoleRequest): Promise<ApiResult<any>> {
  let path: string = `/api/admin/users/${user_id}/role`;
  return api.request<any>(path, { method: 'PATCH', body: JSON.stringify(data) });
}

/**
 * List All Products
 * 获取所有产品（管理后台）
 * GET /api/admin/products
 */
export interface GetAdminProductsParams {
  status?: string | undefined;
}

export async function getAdminProducts(params?: GetAdminProductsParams): Promise<ApiResult<any>> {
  let path: string = `/api/admin/products`;
  const queryParts = [
    (params?.status !== undefined ? `status=${params!.status}` : '')
  ].filter(Boolean);
  if (queryParts.length > 0) {
    path += (path.includes('?') ? '&' : '?') + queryParts.join('&');
  }
  return api.get<any>(path);
}

/**
 * Review Product
 * 审核产品（通过/驳回）
 * PUT /api/admin/products/{product_id}/review
 */
export async function reviewProduct(product_id: string | number, data: ProductReviewRequest): Promise<ApiResult<any>> {
  let path: string = `/api/admin/products/${product_id}/review`;
  return api.put<any>(path, data);
}

/**
 * List Withdrawals
 * 获取提现申请列表
 * GET /api/admin/withdrawals
 */
export interface GetAdminWithdrawalsParams {
  status?: string | undefined;
}

export async function getAdminWithdrawals(params?: GetAdminWithdrawalsParams): Promise<ApiResult<any>> {
  let path: string = `/api/admin/withdrawals`;
  const queryParts = [
    (params?.status !== undefined ? `status=${params!.status}` : '')
  ].filter(Boolean);
  if (queryParts.length > 0) {
    path += (path.includes('?') ? '&' : '?') + queryParts.join('&');
  }
  return api.get<any>(path);
}

/**
 * Review Withdrawal
 * 审核提现申请
 * PUT /api/admin/withdrawals/{withdrawal_id}/review
 */
export async function reviewWithdrawal(withdrawal_id: string | number, data: ProductReviewRequest): Promise<ApiResult<any>> {
  let path: string = `/api/admin/withdrawals/${withdrawal_id}/review`;
  return api.put<any>(path, data);
}

/**
 * Search Products
 * 产品搜索
 * GET /api/search
 */
export interface SearchParams {
  q?: string | undefined;
  category?: string | undefined;
  region?: string | undefined;
  min_price?: number | undefined;
  max_price?: number | undefined;
  sort_by?: string | undefined;
  page?: number | undefined;
  page_size?: number | undefined;
  highlight?: boolean | undefined;
}

export async function search(params?: SearchParams): Promise<ApiResult<any>> {
  let path: string = `/api/search`;
  const queryParts = [
    (params?.q !== undefined ? `q=${params!.q}` : ''),
    (params?.category !== undefined ? `category=${params!.category}` : ''),
    (params?.region !== undefined ? `region=${params!.region}` : ''),
    (params?.min_price !== undefined ? `min_price=${params!.min_price}` : ''),
    (params?.max_price !== undefined ? `max_price=${params!.max_price}` : ''),
    (params?.sort_by !== undefined ? `sort_by=${params!.sort_by}` : ''),
    (params?.page !== undefined ? `page=${params!.page}` : ''),
    (params?.page_size !== undefined ? `page_size=${params!.page_size}` : ''),
    (params?.highlight !== undefined ? `highlight=${params!.highlight}` : '')
  ].filter(Boolean);
  if (queryParts.length > 0) {
    path += (path.includes('?') ? '&' : '?') + queryParts.join('&');
  }
  return api.get<any>(path);
}

/**
 * List Search Categories
 * 获取所有产品分类列表（去重，仅已上架产品）
 * GET /api/search/categories
 */
export async function getSearchCategories(): Promise<ApiResult<any>> {
  let path: string = `/api/search/categories`;
  return api.get<any>(path);
}

/**
 * Search Suggestions
 * 搜索建议（前缀补全），用于搜索框下拉提示
 * GET /api/search/suggestions
 */
export interface GetSearchSuggestionsParams {
  q?: string | undefined;
  limit?: number | undefined;
}

export async function getSearchSuggestions(params?: GetSearchSuggestionsParams): Promise<ApiResult<any>> {
  let path: string = `/api/search/suggestions`;
  const queryParts = [
    (params?.q !== undefined ? `q=${params!.q}` : ''),
    (params?.limit !== undefined ? `limit=${params!.limit}` : '')
  ].filter(Boolean);
  if (queryParts.length > 0) {
    path += (path.includes('?') ? '&' : '?') + queryParts.join('&');
  }
  return api.get<any>(path);
}

/**
 * Import Preview
 * 上传文件 → 解析 → AI识别列名 → 返回预览（前20行）
 * POST /api/imports/preview
 */
export async function importPreview(): Promise<ApiResult<any>> {
  let path: string = `/api/imports/preview`;
  return api.post<any>(path, undefined);
}

/**
 * Import Confirm
 * 确认导入（含去重策略）
 * POST /api/imports/confirm
 */
export async function importConfirm(data: ImportConfirmRequest): Promise<ApiResult<any>> {
  let path: string = `/api/imports/confirm`;
  return api.post<any>(path, data);
}

/**
 * Import History
 * 获取当前用户的导入历史
 * GET /api/imports/history
 */
export interface GetImportHistoryParams {
  page?: number | undefined;
  page_size?: number | undefined;
}

export async function getImportHistory(params?: GetImportHistoryParams): Promise<ApiResult<any>> {
  let path: string = `/api/imports/history`;
  const queryParts = [
    (params?.page !== undefined ? `page=${params!.page}` : ''),
    (params?.page_size !== undefined ? `page_size=${params!.page_size}` : '')
  ].filter(Boolean);
  if (queryParts.length > 0) {
    path += (path.includes('?') ? '&' : '?') + queryParts.join('&');
  }
  return api.get<any>(path);
}

/**
 * List Contacts
 * 获取当前用户的联系人列表（分页，可选按标签筛选）
 * GET /api/contacts
 */
export interface GetContactsParams {
  tag?: string | undefined;
  page?: number | undefined;
  page_size?: number | undefined;
}

export async function getContacts(params?: GetContactsParams): Promise<ApiResult<any>> {
  let path: string = `/api/contacts`;
  const queryParts = [
    (params?.tag !== undefined ? `tag=${params!.tag}` : ''),
    (params?.page !== undefined ? `page=${params!.page}` : ''),
    (params?.page_size !== undefined ? `page_size=${params!.page_size}` : '')
  ].filter(Boolean);
  if (queryParts.length > 0) {
    path += (path.includes('?') ? '&' : '?') + queryParts.join('&');
  }
  return api.get<any>(path);
}

/**
 * Create Contact
 * 创建联系人
 * POST /api/contacts
 */
export async function createContact(data: ContactCreate): Promise<ApiResult<any>> {
  let path: string = `/api/contacts`;
  return api.post<any>(path, data);
}

/**
 * Get Contact
 * 获取联系人详情
 * GET /api/contacts/{contact_id}
 */
export async function getContact(contact_id: string | number): Promise<ApiResult<any>> {
  let path: string = `/api/contacts/${contact_id}`;
  return api.get<any>(path);
}

/**
 * Update Contact
 * 更新联系人
 * PUT /api/contacts/{contact_id}
 */
export async function updateContact(contact_id: string | number, data: ContactUpdate): Promise<ApiResult<any>> {
  let path: string = `/api/contacts/${contact_id}`;
  return api.put<any>(path, data);
}

/**
 * Delete Contact
 * 删除联系人
 * DELETE /api/contacts/{contact_id}
 */
export async function deleteContact(contact_id: string | number): Promise<ApiResult<any>> {
  let path: string = `/api/contacts/${contact_id}`;
  return api.request<any>(path, { method: 'DELETE' });
}

/**
 * Wxpay Unified Order
 * 微信统一下单 (JSAPI)
 * POST /api/payment/wxpay/unified-order
 */
export async function wxpayUnifiedOrder(data: WxPayUnifiedOrderRequest): Promise<ApiResult<any>> {
  let path: string = `/api/payment/wxpay/unified-order`;
  return api.post<any>(path, data);
}

/**
 * Wxpay Query
 * 查询订单支付状态
 * GET /api/payment/wxpay/query/{order_no}
 */
export async function wxpayQueryOrder(order_no: string | number): Promise<ApiResult<any>> {
  let path: string = `/api/payment/wxpay/query/${order_no}`;
  return api.get<any>(path);
}

/**
 * Get Payment Config
 * 获取前端支付配置 (不含密钥)
 * GET /api/payment/config
 */
export async function getPaymentConfig(): Promise<ApiResult<any>> {
  let path: string = `/api/payment/config`;
  return api.get<any>(path);
}

/**
 * List Needs
 * 需求大厅列表（公开，无需登录）
 * GET /api/needs
 */
export interface GetNeedsParams {
  category?: string | undefined;
  status?: string | undefined;
  search?: string | undefined;
  page?: number | undefined;
  page_size?: number | undefined;
}

export async function getNeeds(params?: GetNeedsParams): Promise<ApiResult<any>> {
  let path: string = `/api/needs`;
  const queryParts = [
    (params?.category !== undefined ? `category=${params!.category}` : ''),
    (params?.status !== undefined ? `status=${params!.status}` : ''),
    (params?.search !== undefined ? `search=${params!.search}` : ''),
    (params?.page !== undefined ? `page=${params!.page}` : ''),
    (params?.page_size !== undefined ? `page_size=${params!.page_size}` : '')
  ].filter(Boolean);
  if (queryParts.length > 0) {
    path += (path.includes('?') ? '&' : '?') + queryParts.join('&');
  }
  return api.get<any>(path);
}

/**
 * Create Need
 * 发布需求（需登录）
 * POST /api/needs
 */
export async function createNeed(data: BusinessNeedCreate): Promise<ApiResult<any>> {
  let path: string = `/api/needs`;
  return api.post<any>(path, data);
}

/**
 * Update Need
 * 修改需求（仅发布者或管理员）
 * PUT /api/needs/{need_id}
 */
export async function updateNeed(need_id: string | number, data: BusinessNeedUpdate): Promise<ApiResult<any>> {
  let path: string = `/api/needs/${need_id}`;
  return api.put<any>(path, data);
}

/**
 * Delete Need
 * 删除需求（仅发布者或管理员）
 * DELETE /api/needs/{need_id}
 */
export async function deleteNeed(need_id: string | number): Promise<ApiResult<any>> {
  let path: string = `/api/needs/${need_id}`;
  return api.request<any>(path, { method: 'DELETE' });
}

/**
 * Precreate Recharge
 * 预创建充值单
 * POST /api/recharge/precreate
 */
export async function createRechargePrecreate(data: PrecreateRequest): Promise<ApiResult<any>> {
  let path: string = `/api/recharge/precreate`;
  return api.post<any>(path, data);
}

/**
 * Query Recharge Order
 * 查询充值单状态
 * GET /api/recharge/query/{order_no}
 */
export async function queryRechargeOrder(order_no: string | number): Promise<ApiResult<any>> {
  let path: string = `/api/recharge/query/${order_no}`;
  return api.get<any>(path);
}

/**
 * List Recharge Orders
 * 用户充值记录列表（分页）
 * GET /api/recharge/list
 */
export interface GetRechargeListParams {
  page?: number | undefined;
  limit?: number | undefined;
}

export async function getRechargeList(params?: GetRechargeListParams): Promise<ApiResult<any>> {
  let path: string = `/api/recharge/list`;
  const queryParts = [
    (params?.page !== undefined ? `page=${params!.page}` : ''),
    (params?.limit !== undefined ? `limit=${params!.limit}` : '')
  ].filter(Boolean);
  if (queryParts.length > 0) {
    path += (path.includes('?') ? '&' : '?') + queryParts.join('&');
  }
  return api.get<any>(path);
}

/**
 * Query Balance
 * 查询用户余额 + 最近10条流水
 * GET /api/recharge/balance
 */
export async function getRechargeBalance(): Promise<ApiResult<any>> {
  let path: string = `/api/recharge/balance`;
  return api.get<any>(path);
}

/**
 * List Balance Logs
 * 分页查询余额流水记录
 * GET /api/recharge/balance-logs
 */
export interface GetBalanceLogsParams {
  page?: number | undefined;
  limit?: number | undefined;
}

export async function getBalanceLogs(params?: GetBalanceLogsParams): Promise<ApiResult<any>> {
  let path: string = `/api/recharge/balance-logs`;
  const queryParts = [
    (params?.page !== undefined ? `page=${params!.page}` : ''),
    (params?.limit !== undefined ? `limit=${params!.limit}` : '')
  ].filter(Boolean);
  if (queryParts.length > 0) {
    path += (path.includes('?') ? '&' : '?') + queryParts.join('&');
  }
  return api.get<any>(path);
}

/**
 * 获取用户简要信息
 * 获取用户简要信息（供推广落地页展示推广员姓名）
 * GET /api/users/{user_id}/brief
 */
export async function getUserBrief(user_id: string | number): Promise<ApiResult<any>> {
  let path: string = `/api/users/${user_id}/brief`;
  return api.get<any>(path);
}

/**
 * 首页轮播图
 * 获取小程序首页轮播图列表（无 /api 前缀）
 * GET /banners
 */
export async function getPublicBanners(): Promise<ApiResult<any>> {
  let path: string = `/banners`;
  return api.get<any>(path);
}

/**
 * 首页轮播图（兼容）
 * 获取小程序首页轮播图列表（带 /api 前缀的兼容版本）
 * GET /api/banners
 */
export async function getBanners(): Promise<ApiResult<any>> {
  let path: string = `/api/banners`;
  return api.get<any>(path);
}

/**
 * 通知列表
 * 获取当前用户的通知列表，支持分页和未读筛选
 * GET /api/notifications
 */
export interface GetNotificationsParams {
  page?: number | undefined;
  page_size?: number | undefined;
  unread_only?: boolean | undefined;
}

export async function getNotifications(params?: GetNotificationsParams): Promise<ApiResult<any>> {
  let path: string = `/api/notifications`;
  const queryParts = [
    (params?.page !== undefined ? `page=${params!.page}` : ''),
    (params?.page_size !== undefined ? `page_size=${params!.page_size}` : ''),
    (params?.unread_only !== undefined ? `unread_only=${params!.unread_only}` : '')
  ].filter(Boolean);
  if (queryParts.length > 0) {
    path += (path.includes('?') ? '&' : '?') + queryParts.join('&');
  }
  return api.get<any>(path);
}

/**
 * 获取日志级别
 * 获取当前日志级别（需管理员权限）
 * GET /api/system/log-level
 */
export async function getLogLevel(): Promise<ApiResult<any>> {
  let path: string = `/api/system/log-level`;
  return api.get<any>(path);
}

/**
 * 切换日志级别
 * 动态切换日志级别（需管理员权限）。可选值：DEBUG / INFO / WARNING / ERROR / CRITICAL
 * PUT /api/system/log-level
 */
export async function setLogLevel(level: string): Promise<ApiResult<any>> {
  let path: string = `/api/system/log-level`;
  path += `?level=${level}`;
  return api.put<any>(path, undefined);
}

/**
 * LLM用量汇总
 * 获取LLM调用用量汇总（当日+当月+总计+限额）
 * GET /api/system/cost/usage
 */
export async function getCostUsage(): Promise<ApiResult<any>> {
  let path: string = `/api/system/cost/usage`;
  return api.get<any>(path);
}

/**
 * LLM调用明细
 * 获取LLM调用明细（按模型+按模块+按日明细）
 * GET /api/system/cost/breakdown
 */
export async function getCostBreakdown(): Promise<ApiResult<any>> {
  let path: string = `/api/system/cost/breakdown`;
  return api.get<any>(path);
}

/**
 * LLM模型价格表
 * 获取已注册的LLM模型价格表
 * GET /api/system/cost/models
 */
export async function getCostModels(): Promise<ApiResult<any>> {
  let path: string = `/api/system/cost/models`;
  return api.get<any>(path);
}

/**
 * 深度健康检查
 * 深度健康检查：检查数据库连接池、支付通道可达性、系统资源状态
 * GET /health
 */
export async function healthCheck(): Promise<ApiResult<any>> {
  let path: string = `/health`;
  return api.get<any>(path);
}

/**
 * 存活检查
 * 轻量级存活检查，仅确认服务进程是否运行
 * GET /health/live
 */
export async function healthLiveness(): Promise<ApiResult<any>> {
  let path: string = `/health/live`;
  return api.get<any>(path);
}

/**
 * 就绪检查
 * 就绪检查：确认数据库和支付通道是否可用
 * GET /health/ready
 */
export async function healthReadiness(): Promise<ApiResult<any>> {
  let path: string = `/health/ready`;
  return api.get<any>(path);
}

// ============================================================
// 分组命名空间导出
// ============================================================

export const authApi = {
  login,
  register,
  getCurrentUser,
  refreshToken,
  logout,
  wechatLogin,
};

export const productsApi = {
  getProducts,
  getProduct,
  createProduct,
  updateProduct,
  deleteProduct,
};

export const ordersApi = {
  getOrders,
  createOrder,
  getOrder,
  updateOrderStatus,
};

export const cardsApi = {
  scanCard,
  generateCard,
  listCards,
  getCard,
  deleteCard,
  getCardByToken,
  matchCard,
};

export const searchApi = {
  search,
  vectorSearch,
  getSearchCategories,
  getSearchSuggestions,
};

export const biApi = {
  getOverview,
  getRevenue,
  getTopProducts,
  getUserGrowth,
  getCardStats,
};

export const adminApi = {
  getDashboard,
  getAdminUsers,
  updateUserRole,
  getAdminProducts,
  reviewProduct,
  getAdminWithdrawals,
  reviewWithdrawal,
};

export const contactsApi = {
  getContacts,
  createContact,
  getContact,
  updateContact,
  deleteContact,
};

export const activitiesApi = {
  getActivities,
  createActivity,
};

export const needsApi = {
  getNeeds,
  createNeed,
  updateNeed,
  deleteNeed,
};

export const promoterApi = {
  getEarnings,
  withdraw,
  getWithdrawals,
};

export const importsApi = {
  importPreview,
  importConfirm,
  getImportHistory,
};

export const paymentApi = {
  wxpayUnifiedOrder,
  wxpayQueryOrder,
  getPaymentConfig,
};

export const rechargeApi = {
  getRechargeBalance,
  createRechargePrecreate,
  queryRechargeOrder,
  getRechargeList,
  getBalanceLogs,
};

export const systemApi = {
  getLogLevel,
  setLogLevel,
  getCostUsage,
  getCostBreakdown,
  getCostModels,
};

export const notificationsApi = {
  getNotifications,
};

export const healthApi = {
  healthCheck,
  healthLiveness,
  healthReadiness,
};
