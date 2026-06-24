export type TransitionType = 'push' | 'push_back' | 'slide_up' | 'none';

export interface NavigationState {
  from?: string;
  transition?: TransitionType;
}

// API返回类型
export interface User {
  id: number; username: string; name: string; role: string; phone?: string; company?: string; position?: string;
}
export interface ProductItem {
  id: number; name: string; description: string; price: number; earn_per_share: number; category: string; stock: number; images?: string; status: string; owner_id: number; tags?: string;
}
export interface OrderItem {
  id: number; product_id: number; product_name?: string; quantity: number; total_price: number; status: string; created_at: string;
}

// ===== 人脉管理类型 =====

export interface Contact {
  id: number
  name: string
  phone?: string
  wechat_id?: string
  company?: string
  position?: string
  email?: string
  tags?: string[]
  source?: string
  notes?: string
  avatar?: string
  created_at: string
  updated_at: string
}

export interface Activity {
  id: number
  contact_id: number
  action_type: string
  summary?: string
  detail?: string
  created_at: string
}

export interface ImportPreview {
  headers: string[]
  rows: Record<string, string>[]
  column_mapping: Record<string, string>
  total_rows: number
  duplicates: DuplicateGroup[]
}

export interface DuplicateGroup {
  new_row: number
  existing: Contact
  score: number
}

export interface ContactListResponse {
  total: number
  items: Contact[]
  page: number
  page_size: number
}

export interface ContactSearchParams {
  search?: string
  tags?: string
  page?: number
  page_size?: number
}

// ===== 供需匹配类型 =====

// ===== 推广分润类型 =====

export interface PromoterEarnings {
  total_earnings: number
  withdrawn: number
  pending: number
  available: number
  order_count: number
}

export interface WithdrawalItem {
  id: number
  user_id: number
  amount: number
  status: string
  bank_info?: string
  created_at: string
  updated_at?: string
}

// ===== 管理后台增强类型 =====

export interface AdminDashboardData {
  total_users: number
  total_products: number
  total_orders: number
  total_revenue: number
  today_orders: number
  pending_review_products: number
  pending_withdrawals: number
}

export interface AdminUserItem {
  id: number
  username: string
  name: string
  role: string
  phone?: string
  company?: string
  position?: string
  created_at: string
}

export interface AdminProductItem {
  id: number
  name: string
  company?: string
  price: number
  status: string
  created_at: string
}

export interface AdminWithdrawalItem {
  id: number
  user_name: string
  amount: number
  status: string
  created_at: string
}

export interface GlobalActivity {
  id: number
  user_id?: number
  user_name?: string
  action_type: string
  summary?: string
  detail?: string
  related_type?: string
  related_id?: number
  created_at: string
}

export interface NeedItem {
  id: number
  user_id: number
  title: string
  description?: string
  category?: string
  budget?: string
  region?: string
  contact_name: string
  contact_phone?: string
  status: string
  created_at: string
  updated_at: string
  user?: { id: number; name: string; company?: string; avatar?: string }
}

// ===== 交易履约类型 =====

export interface ContractItem {
  id: number
  user_id: number
  title: string
  template_id?: string
  status: string
  status_label: string
  party_a_name: string
  party_b_name: string
  party_a_id_number?: string
  party_b_id_number?: string
  party_a_contact?: string
  party_b_contact?: string
  contract_amount: number
  variables?: Record<string, any>
  contract_text?: string
  esign_contract_id?: string
  sign_url?: string
  payment_status?: string
  related_order_id?: number
  signed_at?: string
  started_at?: string
  completed_at?: string
  terminated_at?: string
  notes?: string
  created_at: string
  updated_at: string
}

export interface ContractListResponse {
  total: number
  page: number
  page_size: number
  items: ContractItem[]
}

export interface PaymentTransactionItem {
  id: number
  transaction_no?: string
  platform?: string
  amount: number
  status: string
  trade_type?: string
  description?: string
  paid_at?: string
  created_at: string
}

export interface ContractTransactionsResponse {
  contract_id: number
  contract_title: string
  total: number
  items: PaymentTransactionItem[]
}
