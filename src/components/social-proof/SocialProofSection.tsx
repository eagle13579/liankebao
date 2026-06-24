/**
 * SocialProofSection.tsx — 社交证明组合区块
 *
 * 组合 PartnerLogoWall + SuccessCaseCard + SocialProofDashboard
 * 三个组件为完整的社交证明首页区块。
 * 支持响应式布局和链客宝现有 UI 风格。
 */

import PartnerLogoWall from './PartnerLogoWall';
import SuccessCaseCard from './SuccessCaseCard';
import SocialProofDashboard from './SocialProofDashboard';
import { Sparkles } from 'lucide-react';

interface SocialProofSectionProps {
  /** 是否显示 Logo 墙 */
  showLogos?: boolean;
  /** 是否显示案例 */
  showCases?: boolean;
  /** 是否显示数据看板 */
  showDashboard?: boolean;
  /** 额外类名 */
  className?: string;
}

export default function SocialProofSection({
  showLogos = true,
  showCases = true,
  showDashboard = true,
  className = '',
}: SocialProofSectionProps) {
  return (
    <section className={`w-full ${className}`}>
      {/* Section 装饰标题 */}
      <div className="flex items-center gap-2 mb-5">
        <Sparkles className="w-4 h-4 text-[var(--accent-primary)]" />
        <span className="text-xs font-bold text-[var(--text-muted)] uppercase tracking-widest">
          为什么选择链客宝
        </span>
      </div>

      {/* 数据看板 — 最上方，吸引眼球 */}
      {showDashboard && (
        <div className="mb-6">
          <SocialProofDashboard />
        </div>
      )}

      {/* 案例展示 */}
      {showCases && (
        <div className="mb-6">
          <SuccessCaseCard />
        </div>
      )}

      {/* Logo 墙 — 最下方，建立信任背书 */}
      {showLogos && (
        <div
          className="relative rounded-xl border border-[var(--border-primary)]/40
            bg-[var(--bg-surface)]/20 backdrop-blur-sm p-4 md:p-5
            overflow-hidden"
        >
          {/* 背景光晕 */}
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2
            w-[300px] h-[100px] bg-[var(--accent-primary)]/5 rounded-full blur-[60px] pointer-events-none" />

          <PartnerLogoWall
            title=""
            subtitle=""
            autoScrollSpeed={35}
          />
        </div>
      )}
    </section>
  );
}
