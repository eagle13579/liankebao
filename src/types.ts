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
  id: number; name: string; description: string; price: number; earn_per_share: number; category: string; stock: number; images?: string; status: string; owner_id: number;
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
