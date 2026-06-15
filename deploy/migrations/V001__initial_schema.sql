-- ============================================================================
-- 链客宝 数据库初始表结构
-- 版本: V001
-- 描述: 创建所有业务表、索引、外键约束
-- 目标: MySQL 8.0+ (InnoDB, utf8mb4)
-- ============================================================================

-- 启用外键约束检查
SET @OLD_FOREIGN_KEY_CHECKS = @@FOREIGN_KEY_CHECKS;
SET FOREIGN_KEY_CHECKS = 0;

-- ============================================================================
-- 1. users — 用户表
-- ============================================================================
CREATE TABLE IF NOT EXISTS `users` (
    `id`              INT             NOT NULL AUTO_INCREMENT  COMMENT '用户ID',
    `username`        VARCHAR(50)     NOT NULL                COMMENT '用户名',
    `password_hash`   VARCHAR(255)    NOT NULL                COMMENT '密码哈希(bcrypt)',
    `wechat_openid`   VARCHAR(100)    DEFAULT NULL            COMMENT '微信OpenID',
    `name`            VARCHAR(100)    NOT NULL                COMMENT '真实姓名',
    `phone`           VARCHAR(20)     DEFAULT NULL            COMMENT '手机号',
    `company`         VARCHAR(200)    DEFAULT NULL            COMMENT '公司',
    `position`        VARCHAR(100)    DEFAULT NULL            COMMENT '职位',
    `role`            VARCHAR(20)     NOT NULL DEFAULT 'buyer' COMMENT '角色: buyer/promoter/supplier/admin',
    `avatar`          VARCHAR(500)    DEFAULT NULL            COMMENT '头像URL',
    `created_at`      DATETIME        DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_username` (`username`),
    UNIQUE KEY `uk_wechat_openid` (`wechat_openid`),
    KEY `idx_role` (`role`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户表';


-- ============================================================================
-- 2. products — 产品表
-- ============================================================================
CREATE TABLE IF NOT EXISTS `products` (
    `id`              INT             NOT NULL AUTO_INCREMENT  COMMENT '产品ID',
    `name`            VARCHAR(200)    NOT NULL                COMMENT '产品名称',
    `description`     TEXT            DEFAULT NULL            COMMENT '产品简介',
    `price`           FLOAT           NOT NULL DEFAULT 0.0    COMMENT '价格(分销价)',
    `earn_per_share`  FLOAT           NOT NULL DEFAULT 0.0    COMMENT '推广分润/每单',
    `category`        VARCHAR(100)    DEFAULT NULL            COMMENT '分类',
    `stock`           INT             NOT NULL DEFAULT 0      COMMENT '库存',
    `images`          TEXT            DEFAULT NULL            COMMENT '图片URL列表(JSON数组)',
    `status`          VARCHAR(20)     NOT NULL DEFAULT 'pending' COMMENT '状态: pending/approved/rejected',
    `owner_id`        INT             NOT NULL                COMMENT '所属用户ID',
    `created_at`      DATETIME        DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    -- 新增商品富字段
    `specs`           TEXT            DEFAULT NULL            COMMENT '规格参数(JSON对象)',
    `details`         TEXT            DEFAULT NULL            COMMENT '富文本详情(HTML)',
    `brand`           VARCHAR(100)    DEFAULT NULL            COMMENT '品牌',
    `sale_price`      FLOAT           DEFAULT NULL            COMMENT '建议零售价',
    `video_url`       VARCHAR(500)    DEFAULT NULL            COMMENT '产品视频URL',
    `tags`            VARCHAR(500)    DEFAULT NULL            COMMENT '逗号分隔标签',
    `files`           TEXT            DEFAULT NULL            COMMENT '关联文件资料(JSON数组)',
    `is_featured`     TINYINT         DEFAULT 0               COMMENT '是否推荐: 0/1',
    `sort_order`      INT             DEFAULT 0               COMMENT '排序权重',
    PRIMARY KEY (`id`),
    KEY `idx_owner_id` (`owner_id`),
    KEY `idx_status` (`status`),
    KEY `idx_category` (`category`),
    KEY `idx_featured_sort` (`is_featured`, `sort_order`),
    CONSTRAINT `fk_products_owner` FOREIGN KEY (`owner_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='产品表';


-- ============================================================================
-- 3. orders — 订单表
-- ============================================================================
CREATE TABLE IF NOT EXISTS `orders` (
    `id`                INT             NOT NULL AUTO_INCREMENT  COMMENT '订单ID',
    `user_id`           INT             NOT NULL                COMMENT '下单用户ID',
    `product_id`        INT             NOT NULL                COMMENT '产品ID',
    `quantity`          INT             NOT NULL DEFAULT 1      COMMENT '数量',
    `total_price`       FLOAT           NOT NULL                COMMENT '总价',
    `status`            VARCHAR(20)     NOT NULL DEFAULT 'pending' COMMENT '状态: pending/paid/shipped/received/refunded',
    `promoter_id`       INT             DEFAULT NULL            COMMENT '推广员用户ID',
    `commission`        FLOAT           NOT NULL DEFAULT 0.0    COMMENT '佣金金额',
    -- 支付字段
    `payment_platform`  VARCHAR(10)     DEFAULT NULL            COMMENT '支付平台: wxpay/alipay',
    `wx_transaction_id` VARCHAR(100)    DEFAULT NULL            COMMENT '微信支付交易号(V2)',
    `transaction_id`    VARCHAR(100)    DEFAULT NULL            COMMENT '第三方支付订单号',
    `prepay_id`         VARCHAR(100)    DEFAULT NULL            COMMENT '微信预支付ID',
    `payment_time`      DATETIME        DEFAULT NULL            COMMENT '支付完成时间',
    `refund_id`         VARCHAR(100)    DEFAULT NULL            COMMENT '退款单号',
    `refund_time`       DATETIME        DEFAULT NULL            COMMENT '退款时间',
    `pay_time`          DATETIME        DEFAULT NULL            COMMENT '旧字段-支付时间(兼容)',
    `created_at`        DATETIME        DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (`id`),
    KEY `idx_user_id` (`user_id`),
    KEY `idx_product_id` (`product_id`),
    KEY `idx_promoter_id` (`promoter_id`),
    KEY `idx_status` (`status`),
    KEY `idx_transaction_id` (`transaction_id`),
    CONSTRAINT `fk_orders_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_orders_product` FOREIGN KEY (`product_id`) REFERENCES `products` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_orders_promoter` FOREIGN KEY (`promoter_id`) REFERENCES `users` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='订单表';


-- ============================================================================
-- 4. contacts — 联系人表
-- ============================================================================
CREATE TABLE IF NOT EXISTS `contacts` (
    `id`              INT             NOT NULL AUTO_INCREMENT  COMMENT '联系人ID',
    `owner_id`        INT             NOT NULL                COMMENT '所属用户ID',
    `name`            VARCHAR(100)    NOT NULL                COMMENT '联系人姓名',
    `phone`           VARCHAR(50)     DEFAULT NULL            COMMENT '手机号',
    `wechat_id`       VARCHAR(100)    DEFAULT NULL            COMMENT '微信号',
    `company`         VARCHAR(200)    DEFAULT NULL            COMMENT '公司',
    `position`        VARCHAR(100)    DEFAULT NULL            COMMENT '职位',
    `email`           VARCHAR(200)    DEFAULT NULL            COMMENT '邮箱',
    `notes`           TEXT            DEFAULT NULL            COMMENT '备注',
    `tags`            VARCHAR(500)    DEFAULT NULL            COMMENT '标签',
    `source`          VARCHAR(50)     DEFAULT 'import'        COMMENT '来源: import/manual/wechat',
    `import_batch_id` VARCHAR(36)     DEFAULT NULL            COMMENT '导入批次UUID',
    `created_at`      DATETIME        DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at`      DATETIME        DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`id`),
    KEY `idx_owner_id` (`owner_id`),
    KEY `idx_phone` (`phone`),
    KEY `idx_wechat_id` (`wechat_id`),
    KEY `idx_import_batch_id` (`import_batch_id`),
    CONSTRAINT `fk_contacts_owner` FOREIGN KEY (`owner_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='联系人表';


-- ============================================================================
-- 5. activities — 联系人活动时间线
-- ============================================================================
CREATE TABLE IF NOT EXISTS `activities` (
    `id`          INT             NOT NULL AUTO_INCREMENT  COMMENT '活动ID',
    `contact_id`  INT             NOT NULL                COMMENT '联系人ID',
    `action_type` VARCHAR(50)     NOT NULL                COMMENT '活动类型: note/call/meeting/email/wechat/order/import',
    `summary`     VARCHAR(500)    DEFAULT NULL            COMMENT '活动摘要',
    `detail`      TEXT            DEFAULT NULL            COMMENT '活动详情',
    `created_at`  DATETIME        DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (`id`),
    KEY `idx_contact_id` (`contact_id`),
    KEY `idx_action_type` (`action_type`),
    KEY `idx_created_at` (`created_at`),
    CONSTRAINT `fk_activities_contact` FOREIGN KEY (`contact_id`) REFERENCES `contacts` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='联系人活动时间线';


-- ============================================================================
-- 6. import_history — 导入历史记录
-- ============================================================================
CREATE TABLE IF NOT EXISTS `import_history` (
    `id`              INT             NOT NULL AUTO_INCREMENT  COMMENT '记录ID',
    `user_id`         INT             NOT NULL                COMMENT '用户ID',
    `filename`        VARCHAR(255)    NOT NULL                COMMENT '文件名',
    `file_type`       VARCHAR(10)     NOT NULL                COMMENT '文件类型: csv/vcf',
    `total_rows`      INT             NOT NULL DEFAULT 0      COMMENT '总行数',
    `imported_rows`   INT             NOT NULL DEFAULT 0      COMMENT '成功导入行数',
    `skipped_rows`    INT             NOT NULL DEFAULT 0      COMMENT '跳过的行数',
    `merged_rows`     INT             NOT NULL DEFAULT 0      COMMENT '合并的行数',
    `duplicate_count` INT             NOT NULL DEFAULT 0      COMMENT '重复数',
    `field_mapping`   TEXT            DEFAULT NULL            COMMENT '列名映射关系(JSON)',
    `strategy`        VARCHAR(20)     NOT NULL DEFAULT 'skip'  COMMENT '重复策略: skip/merge/update',
    `status`          VARCHAR(20)     NOT NULL DEFAULT 'completed' COMMENT '状态: pending/processing/completed/failed',
    `error_message`   TEXT            DEFAULT NULL            COMMENT '错误信息',
    `batch_id`        VARCHAR(36)     NOT NULL                COMMENT '批次UUID',
    `created_at`      DATETIME        DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (`id`),
    KEY `idx_user_id` (`user_id`),
    KEY `idx_batch_id` (`batch_id`),
    KEY `idx_status` (`status`),
    CONSTRAINT `fk_import_history_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='导入历史记录表';


-- ============================================================================
-- 7. business_needs — 需求表（供需匹配）
-- ============================================================================
CREATE TABLE IF NOT EXISTS `business_needs` (
    `id`            INT             NOT NULL AUTO_INCREMENT  COMMENT '需求ID',
    `user_id`       INT             NOT NULL                COMMENT '发布用户ID',
    `title`         VARCHAR(200)    NOT NULL                COMMENT '需求标题',
    `description`   TEXT            DEFAULT NULL            COMMENT '需求描述',
    `category`      VARCHAR(50)     DEFAULT NULL            COMMENT '分类: 大健康/企业服务/科技产品/教育培训/消费品',
    `budget`        VARCHAR(100)    DEFAULT NULL            COMMENT '预算范围',
    `region`        VARCHAR(100)    DEFAULT NULL            COMMENT '地区',
    `contact_name`  VARCHAR(100)    NOT NULL                COMMENT '联系人姓名',
    `contact_phone` VARCHAR(20)     DEFAULT NULL            COMMENT '联系电话',
    `status`        VARCHAR(20)     NOT NULL DEFAULT 'open'  COMMENT '状态: open/closed',
    `created_at`    DATETIME        DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at`    DATETIME        DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`id`),
    KEY `idx_user_id` (`user_id`),
    KEY `idx_category` (`category`),
    KEY `idx_status` (`status`),
    CONSTRAINT `fk_business_needs_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='需求表(供需匹配)';


-- ============================================================================
-- 8. withdrawals — 提现记录表
-- ============================================================================
CREATE TABLE IF NOT EXISTS `withdrawals` (
    `id`          INT             NOT NULL AUTO_INCREMENT  COMMENT '提现ID',
    `user_id`     INT             NOT NULL                COMMENT '用户ID',
    `amount`      FLOAT           NOT NULL                COMMENT '提现金额',
    `status`      VARCHAR(20)     NOT NULL DEFAULT 'pending' COMMENT '状态: pending/approved/rejected',
    `bank_info`   TEXT            DEFAULT NULL            COMMENT '银行信息(JSON)',
    `created_at`  DATETIME        DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (`id`),
    KEY `idx_user_id` (`user_id`),
    KEY `idx_status` (`status`),
    CONSTRAINT `fk_withdrawals_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='提现记录表';


-- ============================================================================
-- 9. user_balances — 用户余额表（充值模块）
-- ============================================================================
CREATE TABLE IF NOT EXISTS `user_balances` (
    `id`              INT             NOT NULL AUTO_INCREMENT  COMMENT '余额ID',
    `user_id`         INT             NOT NULL                COMMENT '用户ID',
    `balance`         DECIMAL(12,2)   NOT NULL DEFAULT 0.00   COMMENT '当前余额',
    `total_recharged` DECIMAL(12,2)   NOT NULL DEFAULT 0.00   COMMENT '累计充值',
    `total_consumed`  DECIMAL(12,2)   NOT NULL DEFAULT 0.00   COMMENT '累计消费',
    `frozen_amount`   DECIMAL(12,2)   NOT NULL DEFAULT 0.00   COMMENT '冻结金额',
    `version`         BIGINT         NOT NULL DEFAULT 1       COMMENT '乐观锁版本号',
    `updated_at`      DATETIME        DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_user_id` (`user_id`),
    CONSTRAINT `fk_user_balances_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户余额表';


-- ============================================================================
-- 10. recharge_orders — 充值订单表（充值模块）
-- ============================================================================
CREATE TABLE IF NOT EXISTS `recharge_orders` (
    `id`          INT             NOT NULL AUTO_INCREMENT  COMMENT '充值订单ID',
    `user_id`     INT             NOT NULL                COMMENT '用户ID',
    `order_no`    VARCHAR(64)     NOT NULL                COMMENT '充值单号(RC前缀)',
    `amount`      DECIMAL(12,2)   NOT NULL                COMMENT '充值金额(元)',
    `platform`    VARCHAR(10)     NOT NULL DEFAULT 'wxpay' COMMENT '支付平台: wxpay/alipay',
    `prepay_id`   VARCHAR(128)    DEFAULT NULL            COMMENT '微信预支付ID',
    `status`      VARCHAR(20)     NOT NULL DEFAULT 'pending' COMMENT '状态: pending/paid/cancelled/refunded',
    `paid_at`     DATETIME        DEFAULT NULL            COMMENT '支付完成时间',
    `created_at`  DATETIME        DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at`  DATETIME        DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_order_no` (`order_no`),
    KEY `idx_user_id` (`user_id`),
    KEY `idx_status` (`status`),
    CONSTRAINT `fk_recharge_orders_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='充值订单表';


-- ============================================================================
-- 11. balance_logs — 余额流水日志表（充值模块）
-- ============================================================================
CREATE TABLE IF NOT EXISTS `balance_logs` (
    `id`              INT             NOT NULL AUTO_INCREMENT  COMMENT '日志ID',
    `user_id`         INT             NOT NULL                COMMENT '用户ID',
    `amount`          DECIMAL(12,2)   NOT NULL                COMMENT '变动金额(正数)',
    `balance_before`  DECIMAL(12,2)   NOT NULL                COMMENT '变动前余额',
    `balance_after`   DECIMAL(12,2)   NOT NULL                COMMENT '变动后余额',
    `direction`       VARCHAR(10)     NOT NULL                COMMENT '方向: IN(收入)/OUT(支出)',
    `biz_type`        VARCHAR(20)     NOT NULL                COMMENT '业务类型: recharge/consume/refund/adjust/grant',
    `biz_id`          VARCHAR(128)    DEFAULT NULL            COMMENT '关联业务ID(订单号/充值单号)',
    `remark`          VARCHAR(500)    DEFAULT NULL            COMMENT '备注说明',
    `created_at`      DATETIME        DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (`id`),
    KEY `idx_user_id` (`user_id`),
    KEY `idx_biz_type` (`biz_type`),
    KEY `idx_balance_logs_user_time` (`user_id`, `created_at`),
    CONSTRAINT `fk_balance_logs_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='余额流水日志表';


-- ============================================================================
-- 恢复外键约束检查
-- ============================================================================
SET FOREIGN_KEY_CHECKS = @OLD_FOREIGN_KEY_CHECKS;
