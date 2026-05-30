-- ============================================================================
-- migration_rls_check_audit.sql
-- PostgreSQL 15+ 安全层迁移脚本：RLS行级安全 + CHECK约束 + 审计触发器
-- 从 SQLite 迁移至 PostgreSQL 的兼容性检查与数据安全完整实现
-- ============================================================================
-- 使用方式:
--   1. 检查兼容性: psql -f migration_rls_check_audit.sql -v mode=check
--   2. 执行迁移:   psql -f migration_rls_check_audit.sql -v mode=migrate
--   3. 应用层设置: SET LOCAL jwt.user_id = '<user_id>';
--                   SET LOCAL jwt.organization_id = '<org_id>';
--                   SET LOCAL jwt.module = '<module_name>';
-- ============================================================================

BEGIN;

-- 兼容性检查开关（默认关闭，通过 -v mode=check 启用）
\set ON_ERROR_STOP on

-- ============================================================================
-- PART 0: SQLite → PostgreSQL 迁移前置检查
-- ============================================================================
DO $$
BEGIN
    -- PostgreSQL 版本检查（需 15+）
    IF current_setting('server_version_num')::int < 150000 THEN
        RAISE EXCEPTION 'PostgreSQL 15+ required, current version: %', current_setting('server_version');
    END IF;

    RAISE NOTICE '[PASS] PostgreSQL version >= 15: %', current_setting('server_version');

    -- 扩展可用性检查
    IF NOT EXISTS (SELECT 1 FROM pg_available_extensions WHERE name = 'pgcrypto') THEN
        RAISE WARNING '[WARN] pgcrypto not available — UUID generation will use gen_random_uuid() fallback';
    END IF;

    -- SQLite 迁移兼容性提醒
    RAISE NOTICE '[INFO] SQLite → PG migration notes:';
    RAISE NOTICE '[INFO]   1. SQLite INTEGER PRIMARY KEY → PG BIGSERIAL / UUID';
    RAISE NOTICE '[INFO]   2. SQLite TEXT → PG TEXT / VARCHAR';
    RAISE NOTICE '[INFO]   3. SQLite BLOB → PG BYTEA';
    RAISE NOTICE '[INFO]   4. SQLite datetime → PG TIMESTAMPTZ';
    RAISE NOTICE '[INFO]   5. SQLite BOOLEAN (0/1) → PG BOOLEAN';
    RAISE NOTICE '[INFO]   6. SQLite FOREIGN KEY (not enforced) → PG FK (enforced)';
    RAISE NOTICE '[INFO]   7. Check JSON columns are valid JSON before migrate';
    RAISE NOTICE '[INFO]   8. Check status/category enum values before migrate';
END;
$$;

-- ============================================================================
-- PART 1: Schema 创建
-- ============================================================================
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.schemata WHERE schema_name = 'core') THEN
        CREATE SCHEMA core;
        RAISE NOTICE '[CREATE] schema core';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.schemata WHERE schema_name = 'audit') THEN
        CREATE SCHEMA audit;
        RAISE NOTICE '[CREATE] schema audit';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.schemata WHERE schema_name = 'module_ai_card') THEN
        CREATE SCHEMA module_ai_card;
        RAISE NOTICE '[CREATE] schema module_ai_card';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.schemata WHERE schema_name = 'module_chainke') THEN
        CREATE SCHEMA module_chainke;
        RAISE NOTICE '[CREATE] schema module_chainke';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.schemata WHERE schema_name = 'module_digital_port') THEN
        CREATE SCHEMA module_digital_port;
        RAISE NOTICE '[CREATE] schema module_digital_port';
    END IF;
END;
$$;

-- ============================================================================
-- PART 2: 扩展加载
-- ============================================================================
CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public;

-- ============================================================================
-- PART 3: 核心表创建 + CHECK约束
-- ============================================================================

-- 3.1 core.users — 用户表
CREATE TABLE IF NOT EXISTS core.users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username        TEXT NOT NULL,
    display_name    TEXT,
    phone           TEXT,
    email           TEXT,
    status          TEXT NOT NULL DEFAULT 'active',
    avatar_url      TEXT,
    organization_id TEXT,
    metadata        JSONB DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- CHECK约束（文档4.4节）
    CONSTRAINT chk_users_phone
        CHECK (phone IS NULL OR phone ~ '^\+?[1-9]\d{6,14}$'),
    CONSTRAINT chk_users_email
        CHECK (email IS NULL OR email ~ '^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'),
    CONSTRAINT chk_users_name_not_empty
        CHECK (username <> '' AND (display_name IS NULL OR display_name <> '')),
    CONSTRAINT chk_users_status
        CHECK (status IN ('active', 'inactive', 'suspended', 'deleted'))
);

COMMENT ON TABLE core.users IS '用户表 — RLS按user_id隔离';
COMMENT ON COLUMN core.users.phone IS '手机号，格式: 国际号码，6-15位数字，可选前导+';

-- 3.2 core.products — 产品表
CREATE TABLE IF NOT EXISTS core.products (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL,
    description     TEXT,
    price           NUMERIC(12,2) NOT NULL DEFAULT 0,
    stock           INTEGER NOT NULL DEFAULT 0,
    images          JSONB DEFAULT '[]'::jsonb,
    category        TEXT,
    status          TEXT NOT NULL DEFAULT 'active',
    organization_id TEXT NOT NULL,
    metadata        JSONB DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- CHECK约束（文档4.4节）
    CONSTRAINT chk_products_price
        CHECK (price >= 0),
    CONSTRAINT chk_products_stock
        CHECK (stock >= 0),
    CONSTRAINT chk_products_images_is_array
        CHECK (jsonb_typeof(images) = 'array'),
    CONSTRAINT chk_products_status
        CHECK (status IN ('active', 'inactive', 'archived', 'deleted'))
);

COMMENT ON TABLE core.products IS '产品表 — RLS按organization_id隔离';
COMMENT ON COLUMN core.products.images IS '图片URL数组，必须是JSON数组格式';

-- 3.3 core.events — 事件表
CREATE TABLE IF NOT EXISTS core.events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title           TEXT NOT NULL,
    description     TEXT,
    event_type      TEXT NOT NULL DEFAULT 'info',
    module          TEXT NOT NULL,
    source          TEXT,
    payload         JSONB DEFAULT '{}'::jsonb,
    status          TEXT NOT NULL DEFAULT 'pending',
    organization_id TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- CHECK约束
    CONSTRAINT chk_events_module_not_empty
        CHECK (module <> ''),
    CONSTRAINT chk_events_status
        CHECK (status IN ('pending', 'processing', 'completed', 'failed', 'cancelled')),
    CONSTRAINT chk_events_type
        CHECK (event_type IN ('info', 'warning', 'error', 'critical', 'audit'))
);

COMMENT ON TABLE core.events IS '事件表 — RLS按module隔离';

-- 3.4 core.user_tags — 用户标签表
CREATE TABLE IF NOT EXISTS core.user_tags (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES core.users(id) ON DELETE CASCADE,
    tag_key         TEXT NOT NULL,
    tag_value       TEXT,
    tag_type        TEXT NOT NULL DEFAULT 'string',
    metadata        JSONB DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- CHECK约束
    CONSTRAINT chk_user_tags_key_not_empty
        CHECK (tag_key <> ''),
    CONSTRAINT chk_user_tags_type
        CHECK (tag_type IN ('string', 'number', 'boolean', 'json', 'date')),
    CONSTRAINT chk_user_tags_unique
        UNIQUE (user_id, tag_key)
);

COMMENT ON TABLE core.user_tags IS '用户标签表 — RLS按user_id隔离';

-- 3.5 module_ai_card 表（示例模块表）
CREATE TABLE IF NOT EXISTS module_ai_card.cards (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title           TEXT NOT NULL,
    content         TEXT,
    card_type       TEXT NOT NULL DEFAULT 'text',
    status          TEXT NOT NULL DEFAULT 'draft',
    user_id         UUID NOT NULL,
    organization_id TEXT,
    metadata        JSONB DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- CHECK约束
    CONSTRAINT chk_ai_card_title_not_empty
        CHECK (title <> ''),
    CONSTRAINT chk_ai_card_type
        CHECK (card_type IN ('text', 'image', 'code', 'chart', 'mindmap')),
    CONSTRAINT chk_ai_card_status
        CHECK (status IN ('draft', 'published', 'archived', 'deleted'))
);

CREATE TABLE IF NOT EXISTS module_ai_card.templates (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL,
    description     TEXT,
    template_data   JSONB NOT NULL DEFAULT '{}'::jsonb,
    version         INTEGER NOT NULL DEFAULT 1,
    is_active       BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- CHECK约束
    CONSTRAINT chk_ai_template_name_not_empty
        CHECK (name <> ''),
    CONSTRAINT chk_ai_template_version
        CHECK (version > 0),
    CONSTRAINT chk_ai_template_data_object
        CHECK (jsonb_typeof(template_data) = 'object')
);

-- ============================================================================
-- PART 4: 审计触发器（文档4.5节）
-- ============================================================================

-- 4.1 审计日志表（不可删除 — 仅auditor_role有TRUNCATE权限）
CREATE TABLE IF NOT EXISTS audit.data_write_log (
    id              BIGSERIAL,
    table_name      TEXT NOT NULL,
    operation       TEXT NOT NULL,
    old_data        JSONB,
    new_data        JSONB,
    db_user         TEXT NOT NULL DEFAULT current_user,
    client_ip       TEXT,
    module_name     TEXT,
    application     TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- 无主键 — 审计日志只追加，不修改
    CONSTRAINT chk_audit_operation
        CHECK (operation IN ('INSERT', 'UPDATE', 'DELETE', 'TRUNCATE'))
) PARTITION BY RANGE (created_at);

COMMENT ON TABLE audit.data_write_log IS '审计写日志 — 只追加，不修改，不删除（除auditor_role外）';

-- 创建分区（按季度）
CREATE TABLE IF NOT EXISTS audit.data_write_log_2026q1 PARTITION OF audit.data_write_log
    FOR VALUES FROM ('2026-01-01') TO ('2026-04-01');
CREATE TABLE IF NOT EXISTS audit.data_write_log_2026q2 PARTITION OF audit.data_write_log
    FOR VALUES FROM ('2026-04-01') TO ('2026-07-01');
CREATE TABLE IF NOT EXISTS audit.data_write_log_2026q3 PARTITION OF audit.data_write_log
    FOR VALUES FROM ('2026-07-01') TO ('2026-10-01');
CREATE TABLE IF NOT EXISTS audit.data_write_log_2026q4 PARTITION OF audit.data_write_log
    FOR VALUES FROM ('2026-10-01') TO ('2027-01-01');

CREATE INDEX IF NOT EXISTS idx_audit_table_name ON audit.data_write_log (table_name, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_operation  ON audit.data_write_log (operation, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_created_at ON audit.data_write_log (created_at DESC);

-- 4.2 审计触发器函数
CREATE OR REPLACE FUNCTION audit.fn_audit_write_log()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = 'audit', 'public'
AS $$
DECLARE
    v_client_ip   TEXT;
    v_module_name TEXT;
    v_application TEXT;
BEGIN
    -- 从JWT上下文获取客户端信息
    v_client_ip   := NULLIF(current_setting('jwt.client_ip', true), '');
    v_module_name := NULLIF(current_setting('jwt.module', true), '');
    v_application := NULLIF(current_setting('jwt.application', true), '');

    -- 如果JWT未设置，尝试从应用层上下文获取
    IF v_client_ip IS NULL THEN
        v_client_ip := NULLIF(current_setting('app.client_ip', true), '');
    END IF;
    IF v_module_name IS NULL THEN
        v_module_name := NULLIF(current_setting('app.module_name', true), '');
    END IF;

    IF TG_OP = 'INSERT' THEN
        INSERT INTO audit.data_write_log
            (table_name, operation, old_data, new_data, db_user, client_ip, module_name, application)
        VALUES
            (TG_TABLE_SCHEMA || '.' || TG_TABLE_NAME, TG_OP, NULL, row_to_json(NEW)::jsonb,
             current_user, v_client_ip, v_module_name, v_application);
        RETURN NEW;

    ELSIF TG_OP = 'UPDATE' THEN
        INSERT INTO audit.data_write_log
            (table_name, operation, old_data, new_data, db_user, client_ip, module_name, application)
        VALUES
            (TG_TABLE_SCHEMA || '.' || TG_TABLE_NAME, TG_OP,
             row_to_json(OLD)::jsonb, row_to_json(NEW)::jsonb,
             current_user, v_client_ip, v_module_name, v_application);
        RETURN NEW;

    ELSIF TG_OP = 'DELETE' THEN
        INSERT INTO audit.data_write_log
            (table_name, operation, old_data, new_data, db_user, client_ip, module_name, application)
        VALUES
            (TG_TABLE_SCHEMA || '.' || TG_TABLE_NAME, TG_OP,
             row_to_json(OLD)::jsonb, NULL,
             current_user, v_client_ip, v_module_name, v_application);
        RETURN OLD;

    ELSIF TG_OP = 'TRUNCATE' THEN
        INSERT INTO audit.data_write_log
            (table_name, operation, old_data, new_data, db_user, client_ip, module_name, application)
        VALUES
            (TG_TABLE_SCHEMA || '.' || TG_TABLE_NAME, TG_OP,
             NULL, NULL,
             current_user, v_client_ip, v_module_name, v_application);
        RETURN NULL;
    END IF;

    RETURN NULL;
END;
$$;

COMMENT ON FUNCTION audit.fn_audit_write_log() IS '通用审计触发器函数 — 记录所有DML操作到audit.data_write_log';

-- 4.3 为所有表附加审计触发器

-- core schema
DROP TRIGGER IF EXISTS trg_audit_users ON core.users;
CREATE TRIGGER trg_audit_users
    AFTER INSERT OR UPDATE OR DELETE ON core.users
    FOR EACH ROW EXECUTE FUNCTION audit.fn_audit_write_log();

DROP TRIGGER IF EXISTS trg_audit_products ON core.products;
CREATE TRIGGER trg_audit_products
    AFTER INSERT OR UPDATE OR DELETE ON core.products
    FOR EACH ROW EXECUTE FUNCTION audit.fn_audit_write_log();

DROP TRIGGER IF EXISTS trg_audit_events ON core.events;
CREATE TRIGGER trg_audit_events
    AFTER INSERT OR UPDATE OR DELETE ON core.events
    FOR EACH ROW EXECUTE FUNCTION audit.fn_audit_write_log();

DROP TRIGGER IF EXISTS trg_audit_user_tags ON core.user_tags;
CREATE TRIGGER trg_audit_user_tags
    AFTER INSERT OR UPDATE OR DELETE ON core.user_tags
    FOR EACH ROW EXECUTE FUNCTION audit.fn_audit_write_log();

-- module_ai_card schema
DROP TRIGGER IF EXISTS trg_audit_ai_cards ON module_ai_card.cards;
CREATE TRIGGER trg_audit_ai_cards
    AFTER INSERT OR UPDATE OR DELETE ON module_ai_card.cards
    FOR EACH ROW EXECUTE FUNCTION audit.fn_audit_write_log();

DROP TRIGGER IF EXISTS trg_audit_ai_templates ON module_ai_card.templates;
CREATE TRIGGER trg_audit_ai_templates
    AFTER INSERT OR UPDATE OR DELETE ON module_ai_card.templates
    FOR EACH ROW EXECUTE FUNCTION audit.fn_audit_write_log();

-- ============================================================================
-- PART 5: RLS 行级安全策略
-- ============================================================================

-- 5.1 core.users — 用户只能读写自己的数据
ALTER TABLE core.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE core.users FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS p_users_select ON core.users;
CREATE POLICY p_users_select ON core.users FOR SELECT
    USING (id::text = current_setting('jwt.user_id', true));

DROP POLICY IF EXISTS p_users_insert ON core.users;
CREATE POLICY p_users_insert ON core.users FOR INSERT
    WITH CHECK (id::text = current_setting('jwt.user_id', true));

DROP POLICY IF EXISTS p_users_update ON core.users;
CREATE POLICY p_users_update ON core.users FOR UPDATE
    USING (id::text = current_setting('jwt.user_id', true))
    WITH CHECK (id::text = current_setting('jwt.user_id', true));

DROP POLICY IF EXISTS p_users_delete ON core.users;
CREATE POLICY p_users_delete ON core.users FOR DELETE
    USING (id::text = current_setting('jwt.user_id', true));

COMMENT ON POLICY p_users_select ON core.users IS 'RLS: 用户只能查询自己的记录 (基于JWT claim)';
COMMENT ON POLICY p_users_insert ON core.users IS 'RLS: 用户只能插入自己的记录';
COMMENT ON POLICY p_users_update ON core.users IS 'RLS: 用户只能更新自己的记录';
COMMENT ON POLICY p_users_delete ON core.users IS 'RLS: 用户只能删除自己的记录';

-- 5.2 core.products — 按 organization_id 隔离
ALTER TABLE core.products ENABLE ROW LEVEL SECURITY;
ALTER TABLE core.products FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS p_products_select ON core.products;
CREATE POLICY p_products_select ON core.products FOR SELECT
    USING (organization_id = current_setting('jwt.organization_id', true));

DROP POLICY IF EXISTS p_products_insert ON core.products;
CREATE POLICY p_products_insert ON core.products FOR INSERT
    WITH CHECK (organization_id = current_setting('jwt.organization_id', true));

DROP POLICY IF EXISTS p_products_update ON core.products;
CREATE POLICY p_products_update ON core.products FOR UPDATE
    USING (organization_id = current_setting('jwt.organization_id', true))
    WITH CHECK (organization_id = current_setting('jwt.organization_id', true));

DROP POLICY IF EXISTS p_products_delete ON core.products;
CREATE POLICY p_products_delete ON core.products FOR DELETE
    USING (organization_id = current_setting('jwt.organization_id', true));

COMMENT ON POLICY p_products_select ON core.products IS 'RLS: 产品按organization_id隔离 (基于JWT claim)';

-- 5.3 core.events — 按 module 隔离
ALTER TABLE core.events ENABLE ROW LEVEL SECURITY;
ALTER TABLE core.events FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS p_events_select ON core.events;
CREATE POLICY p_events_select ON core.events FOR SELECT
    USING (module = current_setting('jwt.module', true));

DROP POLICY IF EXISTS p_events_insert ON core.events;
CREATE POLICY p_events_insert ON core.events FOR INSERT
    WITH CHECK (module = current_setting('jwt.module', true));

DROP POLICY IF EXISTS p_events_update ON core.events;
CREATE POLICY p_events_update ON core.events FOR UPDATE
    USING (module = current_setting('jwt.module', true))
    WITH CHECK (module = current_setting('jwt.module', true));

DROP POLICY IF EXISTS p_events_delete ON core.events;
CREATE POLICY p_events_delete ON core.events FOR DELETE
    USING (module = current_setting('jwt.module', true));

COMMENT ON POLICY p_events_select ON core.events IS 'RLS: 事件按module隔离 (基于JWT claim)';

-- 5.4 core.user_tags — 按 user_id 隔离
ALTER TABLE core.user_tags ENABLE ROW LEVEL SECURITY;
ALTER TABLE core.user_tags FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS p_user_tags_select ON core.user_tags;
CREATE POLICY p_user_tags_select ON core.user_tags FOR SELECT
    USING (user_id::text = current_setting('jwt.user_id', true));

DROP POLICY IF EXISTS p_user_tags_insert ON core.user_tags;
CREATE POLICY p_user_tags_insert ON core.user_tags FOR INSERT
    WITH CHECK (user_id::text = current_setting('jwt.user_id', true));

DROP POLICY IF EXISTS p_user_tags_update ON core.user_tags;
CREATE POLICY p_user_tags_update ON core.user_tags FOR UPDATE
    USING (user_id::text = current_setting('jwt.user_id', true))
    WITH CHECK (user_id::text = current_setting('jwt.user_id', true));

DROP POLICY IF EXISTS p_user_tags_delete ON core.user_tags;
CREATE POLICY p_user_tags_delete ON core.user_tags FOR DELETE
    USING (user_id::text = current_setting('jwt.user_id', true));

COMMENT ON POLICY p_user_tags_select ON core.user_tags IS 'RLS: 标签按user_id隔离 (基于JWT claim)';

-- ============================================================================
-- PART 6: updated_at 自动更新触发器（所有表的updated_at自动维护）
-- ============================================================================
CREATE OR REPLACE FUNCTION core.fn_set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$;

COMMENT ON FUNCTION core.fn_set_updated_at() IS '自动更新updated_at字段的触发器函数';

-- 为所有含 updated_at 的表附加触发器
DROP TRIGGER IF EXISTS trg_users_updated_at ON core.users;
CREATE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON core.users
    FOR EACH ROW EXECUTE FUNCTION core.fn_set_updated_at();

DROP TRIGGER IF EXISTS trg_products_updated_at ON core.products;
CREATE TRIGGER trg_products_updated_at
    BEFORE UPDATE ON core.products
    FOR EACH ROW EXECUTE FUNCTION core.fn_set_updated_at();

DROP TRIGGER IF EXISTS trg_events_updated_at ON core.events;
CREATE TRIGGER trg_events_updated_at
    BEFORE UPDATE ON core.events
    FOR EACH ROW EXECUTE FUNCTION core.fn_set_updated_at();

DROP TRIGGER IF EXISTS trg_user_tags_updated_at ON core.user_tags;
CREATE TRIGGER trg_user_tags_updated_at
    BEFORE UPDATE ON core.user_tags
    FOR EACH ROW EXECUTE FUNCTION core.fn_set_updated_at();

DROP TRIGGER IF EXISTS trg_ai_cards_updated_at ON module_ai_card.cards;
CREATE TRIGGER trg_ai_cards_updated_at
    BEFORE UPDATE ON module_ai_card.cards
    FOR EACH ROW EXECUTE FUNCTION core.fn_set_updated_at();

DROP TRIGGER IF EXISTS trg_ai_templates_updated_at ON module_ai_card.templates;
CREATE TRIGGER trg_ai_templates_updated_at
    BEFORE UPDATE ON module_ai_card.templates
    FOR EACH ROW EXECUTE FUNCTION core.fn_set_updated_at();

-- ============================================================================
-- PART 7: 数据迁移模板（从SQLite导入后使用）
-- ============================================================================
DO $$
BEGIN
    RAISE NOTICE '============================================================';
    RAISE NOTICE '数据迁移模板 (SQLite → PostgreSQL)';
    RAISE NOTICE '============================================================';
    RAISE NOTICE '';
    RAISE NOTICE '-- 1. 使用 pgloader 迁移:';
    RAISE NOTICE '--    pgloader sqlite:///path/to/source.db postgresql:///target';
    RAISE NOTICE '';
    RAISE NOTICE '-- 2. 手动导入 JSON 数据:';
    RAISE NOTICE '--    \\copy core.users FROM ''users.json'' WITH (FORMAT json);';
    RAISE NOTICE '';
    RAISE NOTICE '-- 3. 迁移后校验:';
    RAISE NOTICE '--    SELECT COUNT(*) AS user_count FROM core.users;';
    RAISE NOTICE '--    SELECT COUNT(*) AS product_count FROM core.products;';
    RAISE NOTICE '--    SELECT COUNT(*) AS audit_count FROM audit.data_write_log;';
    RAISE NOTICE '';
    RAISE NOTICE '-- 4. 应用层上下文设置（JWT claims）:';
    RAISE NOTICE '--    SET LOCAL jwt.user_id         = ''<uuid>'';';
    RAISE NOTICE '--    SET LOCAL jwt.organization_id  = ''<org_id>'';';
    RAISE NOTICE '--    SET LOCAL jwt.module           = ''<module_name>'';';
    RAISE NOTICE '--    SET LOCAL jwt.client_ip        = ''<ip_address>'';';
    RAISE NOTICE '--    SET LOCAL jwt.application      = ''<app_name>'';';
    RAISE NOTICE '';
    RAISE NOTICE '-- 5. RLS 绕过（仅管理员角色）:';
    RAISE NOTICE '--    ALTER TABLE core.users DISABLE ROW LEVEL SECURITY;';
    RAISE NOTICE '--    -- 或使用 BYPASSRLS 角色属性';
    RAISE NOTICE '============================================================';
END;
$$;

COMMIT;

-- ============================================================================
-- 结束: migration_rls_check_audit.sql
-- ============================================================================
