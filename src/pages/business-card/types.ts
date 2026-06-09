export interface CardFields {
  name?: string;
  position?: string;
  company?: string;
  phone?: string;
  email?: string;
  wechat?: string;
  address?: string;
  website?: string;
  cover_image?: string;
}

export interface AlbumPage {
  page: number;
  type: string;
  title: string;
  subtitle?: string;
  fields?: { label: string; value: string }[];
  content?: Record<string, string>;
  style: {
    background: string;
    textColor: string;
    accentColor: string;
  };
}

export interface AlbumSettings {
  turn_animation: string;
  page_width: number;
  page_height: number;
  corner_radius: number;
  shadow: boolean;
}

export interface AlbumMeta {
  total_pages: number;
  pages: AlbumPage[];
  settings: AlbumSettings;
}

export interface CardData {
  id: number;
  share_token: string;
  share_url: string;
  name: string;
  fields: CardFields;
  cover_image?: string;
  album_meta: AlbumMeta;
  created_at: string;
  view_count: number;
}

export interface MatchItem {
  type: 'need' | 'product';
  id: number;
  title: string;
  category?: string;
  score: number;
  reasons: string[];
}

export type Step = 'upload' | 'review' | 'preview' | 'matched';
