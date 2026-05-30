-- ============================================================================
-- migration_roles_permissions.sql
-- PostgreSQL 15+ 角色权限矩阵 + Schema创建
-- 文档4.2节：账号权限矩阵的完整实现
-- ============================================================================
-- 使用方式:
--   1. psql -U postgres -f migration_roles_permissions.sql
--   2. 授予用户角色:
--      GRANT module_ai_card_role TO specific_user;
--   3. 验证:
--      SELECT * FROM information_schema.role_table_grants WHERE grantee LIKE '%role%';
-- ============================================================================

BEGIN;

-- ============================================================================
-- PART 1: Schema 创建（与migration_rls_check_audit.sql同步，schema已经存在时跳过）
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

    IF NOT EXISTS (SELECT 1 FROM information_schema.schemata WHERE schema_name = 'module_knowledge_base') THEN
        CREATE SCHEMA module_knowledge_base;
        RAISE NOTICE '[CREATE] schema module_knowledge_base';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.schemata WHERE schema_name = 'module_risk_control') THEN
        CREATE SCHEMA module_risk_control;
        RAISE NOTICE '[CREATE] schema module_risk_control';
    END IF;
END;
$$;

-- ============================================================================
-- PART 2: 角色创建（文档4.2节 — 账号权限矩阵）
-- ============================================================================

-- 2.1 模块角色：每个模块独立操作权限
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'module_ai_card_role') THEN
        CREATE ROLE module_ai_card_role;
        RAISE NOTICE '[CREATE ROLE] module_ai_card_role';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'module_chainke_role') THEN
        CREATE ROLE module_chainke_role;
        RAISE NOTICE '[CREATE ROLE] module_chainke_role';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'module_digital_port_role') THEN
        CREATE ROLE module_digital_port_role;
        RAISE NOTICE '[CREATE ROLE] module_digital_port_role';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'module_knowledge_base_role') THEN
        CREATE ROLE module_knowledge_base_role;
        RAISE NOTICE '[CREATE ROLE] module_knowledge_base_role';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'module_risk_control_role') THEN
        CREATE ROLE module_risk_control_role;
        RAISE NOTICE '[CREATE ROLE] module_risk_control_role';
    END IF;
END
$$;

-- 2.2 网关角色
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dwg_gateway_role') THEN
        CREATE ROLE dwg_gateway_role WITH NOINHERIT;
        RAISE NOTICE '[CREATE ROLE] dwg_gateway_role';
    END IF;
END
$$;

-- 2.3 审计角色
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'auditor_role') THEN
        CREATE ROLE auditor_role WITH NOINHERIT;
        RAISE NOTICE '[CREATE ROLE] auditor_role';
    END IF;
END
$$;

-- 2.4 管理员角色
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'admin_role') THEN
        CREATE ROLE admin_role WITH NOINHERIT LOGIN BYPASSRLS;
        RAISE NOTICE '[CREATE ROLE] admin_role (BYPASSRLS)';
    END IF;
END
$$;

-- 2.5 应用服务角色（连接池使用）
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_service_role') THEN
        CREATE ROLE app_service_role WITH NOINHERIT LOGIN;
        RAISE NOTICE '[CREATE ROLE] app_service_role';
    END IF;
END
$$;

-- ============================================================================
-- PART 3: Schema 级别权限
-- ============================================================================

-- 3.1 授予 USAGE 权限到各模块角色
GRANT USAGE ON SCHEMA core              TO module_ai_card_role, module_chainke_role,
                                           module_digital_port_role, module_knowledge_base_role,
                                           module_risk_control_role, dwg_gateway_role,
                                           auditor_role, admin_role, app_service_role;

GRANT USAGE ON SCHEMA module_ai_card    TO module_ai_card_role, admin_role, app_service_role;
GRANT USAGE ON SCHEMA module_chainke    TO module_chainke_role, admin_role, app_service_role;
GRANT USAGE ON SCHEMA module_digital_port TO module_digital_port_role, admin_role, app_service_role;
GRANT USAGE ON SCHEMA module_knowledge_base TO module_knowledge_base_role, admin_role, app_service_role;
GRANT USAGE ON SCHEMA module_risk_control TO module_risk_control_role, admin_role, app_service_role;
GRANT USAGE ON SCHEMA audit             TO auditor_role, admin_role, app_service_role;

-- 3.2 网关角色 — 只读 core schema
GRANT USAGE ON SCHEMA core TO dwg_gateway_role;

-- ============================================================================
-- PART 4: 表级别权限
-- ============================================================================

-- 4.1 module_ai_card_role — 对其模块 schema 全表 CRUD
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA module_ai_card TO module_ai_card_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA module_ai_card
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO module_ai_card_role;

-- 4.2 module_chainke_role — 对其模块 schema 全表 CRUD
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA module_chainke TO module_chainke_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA module_chainke
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO module_chainke_role;

-- 4.3 module_digital_port_role — 对其模块 schema 全表 CRUD
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA module_digital_port TO module_digital_port_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA module_digital_port
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO module_digital_port_role;

-- 4.4 module_knowledge_base_role
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA module_knowledge_base TO module_knowledge_base_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA module_knowledge_base
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO module_knowledge_base_role;

-- 4.5 module_risk_control_role
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA module_risk_control TO module_risk_control_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA module_risk_control
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO module_risk_control_role;

-- 4.6 core schema 表 — 模块角色只能读自己的数据（RLS控制写操作）
GRANT SELECT, INSERT, UPDATE, DELETE ON core.users      TO module_ai_card_role, module_chainke_role,
                                                             module_digital_port_role, module_knowledge_base_role,
                                                             module_risk_control_role, app_service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON core.products   TO module_ai_card_role, module_chainke_role,
                                                             module_digital_port_role, module_knowledge_base_role,
                                                             module_risk_control_role, app_service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON core.events     TO module_ai_card_role, module_chainke_role,
                                                             module_digital_port_role, module_knowledge_base_role,
                                                             module_risk_control_role, app_service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON core.user_tags  TO module_ai_card_role, module_chainke_role,
                                                             module_digital_port_role, module_knowledge_base_role,
                                                             module_risk_control_role, app_service_role;

-- 4.7 dwg_gateway_role — 只读 core schema
GRANT SELECT ON ALL TABLES IN SCHEMA core TO dwg_gateway_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA core
    GRANT SELECT ON TABLES TO dwg_gateway_role;

-- 4.8 auditor_role — 审计日志只读权限 + TRUNCATE权限
GRANT SELECT ON ALL TABLES IN SCHEMA core   TO auditor_role;
GRANT SELECT ON ALL TABLES IN SCHEMA audit  TO auditor_role;

-- 审计日志表 — 特殊权限管控
-- auditor_role 有 TRUNCATE 权限（但不可INSERT/UPDATE/DELETE单行）
GRANT SELECT, TRUNCATE ON audit.data_write_log TO auditor_role;
GRANT SELECT, TRUNCATE ON audit.data_write_log_2026q1 TO auditor_role;
GRANT SELECT, TRUNCATE ON audit.data_write_log_2026q2 TO auditor_role;
GRANT SELECT, TRUNCATE ON audit.data_write_log_2026q3 TO auditor_role;
GRANT SELECT, TRUNCATE ON audit.data_write_log_2026q4 TO auditor_role;

ALTER DEFAULT PRIVILEGES IN SCHEMA audit
    GRANT SELECT, TRUNCATE ON TABLES TO auditor_role;

-- 4.9 admin_role — 所有权限
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA core TO admin_role;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA audit TO admin_role;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA module_ai_card TO admin_role;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA module_chainke TO admin_role;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA module_digital_port TO admin_role;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA module_knowledge_base TO admin_role;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA module_risk_control TO admin_role;

ALTER DEFAULT PRIVILEGES IN SCHEMA core, audit, module_ai_card, module_chainke,
    module_digital_port, module_knowledge_base, module_risk_control
    GRANT ALL ON TABLES TO admin_role;

-- 4.10 app_service_role — 应用层服务，全表CRUD（RLS由应用层通过SET LOCAL控制）
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA core TO app_service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA module_ai_card TO app_service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA module_chainke TO app_service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA module_digital_port TO app_service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA module_knowledge_base TO app_service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA module_risk_control TO app_service_role;

ALTER DEFAULT PRIVILEGES IN SCHEMA core, audit, module_ai_card, module_chainke,
    module_digital_port, module_knowledge_base, module_risk_control
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_service_role;

-- ============================================================================
-- PART 5: 序列权限
-- ============================================================================
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA audit TO auditor_role, admin_role, app_service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA audit GRANT USAGE, SELECT ON SEQUENCES TO auditor_role;

GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA core TO admin_role, app_service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA core GRANT USAGE, SELECT ON SEQUENCES TO admin_role, app_service_role;

-- ============================================================================
-- PART 6: 函数/存储过程执行权限
-- ============================================================================
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA core  TO module_ai_card_role, module_chainke_role,
                                                     module_digital_port_role, module_knowledge_base_role,
                                                     module_risk_control_role, admin_role, app_service_role;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA audit TO auditor_role, admin_role, app_service_role;

ALTER DEFAULT PRIVILEGES IN SCHEMA core
    GRANT EXECUTE ON FUNCTIONS TO module_ai_card_role, module_chainke_role,
                                   module_digital_port_role, module_knowledge_base_role,
                                   module_risk_control_role, admin_role, app_service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA audit
    GRANT EXECUTE ON FUNCTIONS TO auditor_role, admin_role, app_service_role;

-- ============================================================================
-- PART 7: 角色层级关系
-- ============================================================================

-- 网关角色 → 应用服务（读 core + 通过应用层执行其他操作）
-- 注意：dwg_gateway_role 不继承其他角色，使用 SET ROLE 切换

-- 管理员角色拥有所有模块角色的权限
GRANT module_ai_card_role       TO admin_role;
GRANT module_chainke_role       TO admin_role;
GRANT module_digital_port_role  TO admin_role;
GRANT module_knowledge_base_role TO admin_role;
GRANT module_risk_control_role  TO admin_role;
GRANT auditor_role              TO admin_role;

-- 应用服务角色拥有所有模块角色的权限（数据库连接池使用）
GRANT module_ai_card_role       TO app_service_role;
GRANT module_chainke_role       TO app_service_role;
GRANT module_digital_port_role  TO app_service_role;
GRANT module_knowledge_base_role TO app_service_role;
GRANT module_risk_control_role  TO app_service_role;

-- ============================================================================
-- PART 8: 迁移权限检查 & 验证
-- ============================================================================
DO $$
BEGIN
    RAISE NOTICE '============================================================';
    RAISE NOTICE '角色权限矩阵迁移完成';
    RAISE NOTICE '============================================================';
    RAISE NOTICE '';
    RAISE NOTICE '已创建的角色:';
    RAISE NOTICE '  - module_ai_card_role        (AI卡片模块)';
    RAISE NOTICE '  - module_chainke_role        (链客模块)';
    RAISE NOTICE '  - module_digital_port_role   (数字门户模块)';
    RAISE NOTICE '  - module_knowledge_base_role (知识库模块)';
    RAISE NOTICE '  - module_risk_control_role   (风控模块)';
    RAISE NOTICE '  - dwg_gateway_role           (只读网关)';
    RAISE NOTICE '  - auditor_role               (审计员 — 审计日志TRUNCATE权限)';
    RAISE NOTICE '  - admin_role                 (管理员 — BYPASSRLS)';
    RAISE NOTICE '  - app_service_role           (应用服务)';
    RAISE NOTICE '';
    RAISE NOTICE '权限验证查询:';
    RAISE NOTICE '  SELECT grantee, table_schema, table_name, privilege_type';
    RAISE NOTICE '  FROM information_schema.role_table_grants';
    RAISE NOTICE '  WHERE table_schema IN (''core'',''audit'',''module_ai_card'')';
    RAISE NOTICE '  ORDER BY grantee, table_schema, table_name;';
    RAISE NOTICE '';
    RAISE NOTICE '角色成员查询:';
    RAISE NOTICE '  SELECT r.rolname AS role_name, m.rolname AS member_name';
    RAISE NOTICE '  FROM pg_roles r';
    RAISE NOTICE '  JOIN pg_auth_members am ON r.oid = am.roleid';  
    RAISE NOTICE '  JOIN pg_roles m ON m.oid = am.member';
    RAISE NOTICE '  ORDER BY r.rolname;';
    RAISE NOTICE '============================================================';
END;
$$;

COMMIT;

-- ============================================================================
-- 结束: migration_roles_permissions.sql
-- ============================================================================
