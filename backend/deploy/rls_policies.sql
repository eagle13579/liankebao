-- ============================================================================
-- 链客宝 PostgreSQL Row-Level Security (RLS) 策略部署脚本
-- 版本: 1.0
-- 日期: 2026-06-10
-- 说明:
--   当 IS_MULTI_TENANT=true 且数据库为 PostgreSQL 时，
--   在数据库层面强制按 organization_id 做行级隔离。
--   管理员 (role='admin') 可跨组织查看。
--   回滚: 关闭 IS_MULTI_TENANT 环境变量即可。
--
-- 执行方式:
--   psql -U <user> -d <db> -f rls_policies.sql
--   或
--   psql -U <user> -d <db> -c "\i rls_policies.sql"
-- ============================================================================

BEGIN;

-- ============================================================================
-- 第1步: 创建 app schema（用于存放辅助函数，不污染 public）
-- ============================================================================
CREATE SCHEMA IF NOT EXISTS app AUTHORIZATION CURRENT_USER;

-- ============================================================================
-- 第2步: 辅助函数
-- ============================================================================

-- 2.1 判断多租户是否活跃
CREATE OR REPLACE FUNCTION app._rls_is_active()
RETURNS boolean
LANGUAGE plpgsql
STABLE
AS $$
BEGIN
    RETURN current_setting('app.is_multi_tenant', true) = '1';
END;
$$;

-- 2.2 获取当前组织 ID（安全转型 text → int）
CREATE OR REPLACE FUNCTION app._rls_current_org_id()
RETURNS int
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    val text;
BEGIN
    val := NULLIF(current_setting('app.current_org_id', true), '');
    IF val IS NULL THEN
        RETURN NULL;
    END IF;
    RETURN val::int;
EXCEPTION
    WHEN OTHERS THEN
        RETURN NULL;
END;
$$;

-- 2.3 判断当前用户是否为全局管理员
CREATE OR REPLACE FUNCTION app._rls_is_admin()
RETURNS boolean
LANGUAGE plpgsql
STABLE
AS $$
BEGIN
    RETURN NULLIF(current_setting('app.current_user_role', true), '') = 'admin';
END;
$$;

-- ============================================================================
-- 第3步: 核心 RLS 策略宏（通过 DO 块逐表应用）
-- ============================================================================

DO $$
DECLARE
    tbl text;
    tables text[] := ARRAY[
        'users',
        'brochures',
        'products',
        'orders',
        'payments',
        'discussions',
        'hypotheses',
        'experiments',
        'opportunities',
        'design_reviews',
        'aesthetic_scores',
        'messages',
        'notifications',
        'settings',
        'audit_logs',
        'sessions',
        'api_keys',
        'templates'
    ];
BEGIN
    FOREACH tbl IN ARRAY tables
    LOOP
        -- 只在表存在时执行（部分表可能尚未创建）
        IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = tbl) THEN

            -- 3a. 启用行级安全
            EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY;', tbl);

            -- 3b. 删除旧策略（幂等）
            BEGIN
                EXECUTE format('DROP POLICY IF EXISTS tenant_isolation_%s ON public.%I;', tbl, tbl);
            EXCEPTION WHEN OTHERS THEN
                -- 忽略（策略可能还不存在）
            END;

            -- 3c. 创建 RLS 策略
            --     逻辑: 多租户未启用 → 放行
            --           管理员 → 放行
            --           organization_id 为空 → 放行
            --           organization_id 匹配当前 org_id → 放行
            EXECUTE format(
                'CREATE POLICY tenant_isolation_%1$s ON public.%1$I '
                'FOR ALL '
                'USING ( '
                '    NOT app._rls_is_active() '
                '    OR app._rls_is_admin() '
                '    OR organization_id IS NULL '
                '    OR organization_id = app._rls_current_org_id() '
                ') '
                'WITH CHECK ( '
                '    NOT app._rls_is_active() '
                '    OR app._rls_is_admin() '
                '    OR app._rls_current_org_id() IS NULL '
                '    OR organization_id = app._rls_current_org_id() '
                ');',
                tbl
            );

            RAISE NOTICE 'RLS policy applied: tenant_isolation_%', tbl;
        ELSE
            RAISE WARNING 'Table public.% does not exist yet — RLS policy skipped (will need manual application after table creation)', tbl;
        END IF;
    END LOOP;
END;
$$;

-- ============================================================================
-- 第4步: 验证部署结果
-- ============================================================================

DO $$
DECLARE
    tbl text;
    tables text[] := ARRAY[
        'users', 'brochures', 'products', 'orders', 'payments',
        'discussions', 'hypotheses', 'experiments', 'opportunities',
        'design_reviews', 'aesthetic_scores', 'messages', 'notifications',
        'settings', 'audit_logs', 'sessions', 'api_keys', 'templates'
    ];
    rls_enabled_count int := 0;
    rls_total_count int := 0;
BEGIN
    FOREACH tbl IN ARRAY tables
    LOOP
        IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = tbl) THEN
            rls_total_count := rls_total_count + 1;
            IF EXISTS (
                SELECT 1 FROM pg_tables
                WHERE schemaname = 'public'
                  AND tablename = tbl
                  AND rowsecurity = true
            ) THEN
                rls_enabled_count := rls_enabled_count + 1;
                RAISE NOTICE '✅ RLS enabled: public.%', tbl;
            ELSE
                RAISE WARNING '❌ RLS NOT enabled: public.%', tbl;
            END IF;
        END IF;
    END LOOP;
    RAISE NOTICE 'RLS deployment summary: %/% tables enabled (skipped % non-existent tables)',
        rls_enabled_count, rls_total_count, array_length(tables, 1) - rls_total_count;
END;
$$;

COMMIT;
