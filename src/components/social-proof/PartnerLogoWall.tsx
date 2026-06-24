/**
 * PartnerLogoWall.tsx — 合作企业Logo墙
 *
 * 展示合作企业 Logo 的横向滚动墙，支持：
 * - 配置化数据源（props direct / API fetch）
 * - 自动横向滚动动画
 * - 响应式布局
 * - 深色/亮色主题适配
 */

import { useState, useEffect, useRef } from 'react';
import { api } from '../../api/client';

export interface PartnerLogoItem {
  id: string;
  name: string;
  logo_url: string;
  website?: string;
  category?: string;
  sort_order?: number;
}

interface PartnerLogoWallProps {
  /** 自定义数据（可选，不传则从 API 获取） */
  logos?: PartnerLogoItem[];
  /** 标题 */
  title?: string;
  /** 副标题 */
  subtitle?: string;
  /** 自动滚动速度（秒，0=禁用） */
  autoScrollSpeed?: number;
  /** 额外类名 */
  className?: string;
}

const FALLBACK_LOGOS: PartnerLogoItem[] = [
  { id: '1', name: '华为云', logo_url: '', category: '云计算' },
  { id: '2', name: '腾讯云', logo_url: '', category: '云计算' },
  { id: '3', name: '阿里巴巴', logo_url: '', category: '电商' },
  { id: '4', name: '百度AI', logo_url: '', category: '人工智能' },
  { id: '5', name: '字节跳动', logo_url: '', category: '科技' },
  { id: '6', name: '京东云', logo_url: '', category: '云计算' },
  { id: '7', name: '网易', logo_url: '', category: '互联网' },
  { id: '8', name: '美团', logo_url: '', category: '生活服务' },
  { id: '9', name: '小米', logo_url: '', category: '智能硬件' },
  { id: '10', name: '科大讯飞', logo_url: '', category: '人工智能' },
  { id: '11', name: '用友', logo_url: '', category: '企业服务' },
  { id: '12', name: '金蝶', logo_url: '', category: '企业服务' },
];

/** 获取企业名称首字母作为 fallback 图标 */
function getInitials(name: string): string {
  return name.charAt(0);
}

export default function PartnerLogoWall({
  logos: propLogos,
  title = '合作企业',
  subtitle = '数千家企业信赖的选择',
  autoScrollSpeed = 30,
  className = '',
}: PartnerLogoWallProps) {
  const [logos, setLogos] = useState<PartnerLogoItem[]>(propLogos || FALLBACK_LOGOS);
  const [loading, setLoading] = useState(!propLogos);
  const scrollRef = useRef<HTMLDivElement>(null);

  // 从 API 获取
  useEffect(() => {
    if (propLogos) {
      setLogos(propLogos);
      setLoading(false);
      return;
    }
    let cancelled = false;
    api.get<{ items: PartnerLogoItem[] }>('/api/social-proof/logos')
      .then(res => {
        if (!cancelled && res.data?.items && res.data.items.length > 0) {
          setLogos(res.data.items);
        }
        // 即使 API 返回空也保留 fallback
      })
      .catch(() => { /* 静默降级到 fallback */ })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [propLogos]);

  // 如果无数据，展示 fallback
  const displayLogos = logos.length > 0 ? logos : FALLBACK_LOGOS;

  return (
    <section className={`w-full ${className}`}>
      {/* 标题 */}
      {title && (
        <div className="text-center mb-6">
          <h2 className="text-lg md:text-xl font-bold text-[var(--text-primary)]">
            {title}
          </h2>
          {subtitle && (
            <p className="text-xs md:text-sm text-[var(--text-muted)] mt-1">
              {subtitle}
            </p>
          )}
        </div>
      )}

      {/* Logo 墙 — 双组无缝滚动 */}
      <div
        ref={scrollRef}
        className="relative overflow-hidden"
        style={{
          maskImage: 'linear-gradient(to right, transparent, black 5%, black 95%, transparent)',
          WebkitMaskImage: 'linear-gradient(to right, transparent, black 5%, black 95%, transparent)',
        }}
      >
        {loading ? (
          <div className="flex gap-6 justify-center py-4">
            {[1,2,3,4,5,6].map(i => (
              <div key={i} className="w-24 h-12 bg-[var(--bg-surface)] rounded-lg animate-pulse" />
            ))}
          </div>
        ) : (
          <div
            className="flex gap-8 md:gap-12 py-4"
            style={{
              animation: autoScrollSpeed > 0
                ? `logo-scroll ${autoScrollSpeed}s linear infinite`
                : 'none',
            }}
          >
            {/* 第一组 */}
            {displayLogos.map(logo => (
              <LogoItem key={logo.id} logo={logo} />
            ))}
            {/* 第二组（复制用于无缝滚动） */}
            {displayLogos.map(logo => (
              <LogoItem key={`dup-${logo.id}`} logo={logo} />
            ))}
          </div>
        )}
      </div>

      {/* 滚动动画 keyframes */}
      <style>{`
        @keyframes logo-scroll {
          0% { transform: translateX(0); }
          100% { transform: translateX(-50%); }
        }
      `}</style>
    </section>
  );
}

/** 单个 Logo 项 */
function LogoItem({ logo }: { logo: PartnerLogoItem }) {
  const [imgError, setImgError] = useState(false);

  return (
    <div
      className="flex-shrink-0 flex items-center justify-center h-10 md:h-12 px-4 md:px-6
        bg-[var(--bg-surface)]/50 backdrop-blur-sm rounded-xl border border-[var(--border-primary)]/60
        hover:border-[var(--accent-primary)]/40 hover:bg-[var(--bg-surface)]/80
        transition-all duration-300 group cursor-default"
      title={logo.name}
    >
      {logo.logo_url && !imgError ? (
        <img
          src={logo.logo_url}
          alt={logo.name}
          className="max-h-6 md:max-h-7 max-w-20 md:max-w-28 object-contain opacity-60 group-hover:opacity-90 transition-opacity duration-300 grayscale group-hover:grayscale-0"
          onError={() => setImgError(true)}
          loading="lazy"
        />
      ) : (
        <span className="text-xs md:text-sm font-bold text-[var(--text-muted)] group-hover:text-[var(--accent-primary)] transition-colors duration-300 whitespace-nowrap">
          {getInitials(logo.name)}
        </span>
      )}
    </div>
  );
}
