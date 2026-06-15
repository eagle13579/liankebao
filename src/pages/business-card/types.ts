export interface CardFields {
  name?: string;
  position?: string;
  company?: string;
  phone?: string;
  email?: string;
  wechat?: string;
  address?: string;
  website?: string;
  [key: string]: string | undefined;
}

export interface AlbumPage {
  type: "cover" | "contact" | "company" | "qrcode";
  content: Record<string, string>;
}

export interface AlbumMeta {
  title: string;
  bio: string;
  tags: string[];
  theme: "modern" | "classic" | "minimal";
}

export interface CardData {
  id: number;
  user_id: string;
  fields: CardFields;
  album_pages: AlbumPage[];
  album_meta: AlbumMeta;
  created_at: string;
}

export interface MatchItem {
  id: number;
  name: string;
  company: string;
  position: string;
  match_score: number;
  common_contacts: number;
  tags: string[];
}

export type Step = "upload" | "review" | "preview" | "matched";
