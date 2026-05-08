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
