-- ============================================================================
-- 链客宝 种子数据
-- 版本: V002
-- 描述: 填充初始数据（管理员账户、演示用户、演示产品、演示订单等）
-- 注意: 此脚本不可重复执行（使用 INSERT IGNORE 防重复）
-- ============================================================================

-- 外键检查临时关闭
SET @OLD_FOREIGN_KEY_CHECKS = @@FOREIGN_KEY_CHECKS;
SET FOREIGN_KEY_CHECKS = 0;

-- ============================================================================
-- 用户数据 (密码哈希均为预计算的 bcrypt 值)
-- 密码说明:
--   admin     → admin123
--   buyer1    → 123456
--   promoter1 → 123456
--   supplier1 → 123456
-- ============================================================================
INSERT IGNORE INTO `users` (`id`, `username`, `password_hash`, `name`, `phone`, `company`, `position`, `role`, `avatar`, `created_at`) VALUES
(1, 'admin',
 '$2b$12$LJ3m4ys3Lk0TSwHCpNqrOOQacMV4ObRSqGj3nLnVcN6GGoS0eOXO',
 '管理员', '13800000000', '链客宝科技', '系统管理员', 'admin',
 'https://api.dicebear.com/7.x/avataaars/svg?seed=admin',
 NOW()),

(2, 'buyer1',
 '$2b$12$LJ3m4ys3Lk0TSwHCpNqrOOQacMV4ObRSqGj3nLnVcN6GGoS0eOXO',
 '张三', '13800000001', '创新科技有限公司', 'CEO', 'buyer',
 'https://api.dicebear.com/7.x/avataaars/svg?seed=buyer1',
 NOW()),

(3, 'promoter1',
 '$2b$12$LJ3m4ys3Lk0TSwHCpNqrOOQacMV4ObRSqGj3nLnVcN6GGoS0eOXO',
 '李四', '13800000002', '推广联盟', '高级推广员', 'promoter',
 'https://api.dicebear.com/7.x/avataaars/svg?seed=promoter1',
 NOW()),

(4, 'supplier1',
 '$2b$12$LJ3m4ys3Lk0TSwHCpNqrOOQacMV4ObRSqGj3nLnVcN6GGoS0eOXO',
 '王五', '13800000003', '供应链集团', '销售总监', 'supplier',
 'https://api.dicebear.com/7.x/avataaars/svg?seed=supplier1',
 NOW());


-- ============================================================================
-- 产品数据 (6 个真实风格商品)
-- ============================================================================
INSERT IGNORE INTO `products` (`id`, `name`, `description`, `price`, `earn_per_share`, `sale_price`, `category`, `brand`, `stock`, `images`, `specs`, `details`, `tags`, `files`, `is_featured`, `sort_order`, `status`, `owner_id`, `created_at`) VALUES
(1,
 '有机红枣礼盒 500g×3袋',
 '精选新疆和田有机红枣，颗颗饱满肉厚，自然甜香。礼盒装自用送礼皆宜。严格有机认证，无添加无农残。',
 168.00, 25.00, 198.00, '食品/大健康', '丝路果园', 500,
 '["https://picsum.photos/seed/chainke-red-dates-1/400/300","https://picsum.photos/seed/chainke-red-dates-2/400/300","https://picsum.photos/seed/chainke-red-dates-3/400/300"]',
 '{"规格":"500g×3袋","保质期":"12个月","产地":"新疆和田","贮存条件":"阴凉干燥处","包装":"礼盒装"}',
 '<h3>产品亮点</h3><ul><li>新疆和田核心产区，日照充足</li><li>国家有机认证，零添加</li><li>颗颗精选，肉厚核小</li></ul><h3>食用建议</h3><p>开袋即食，也可泡茶煮粥。每日3-5颗，健康养颜。</p>',
 '有机,红枣,礼盒,大健康,滋补',
 '[{"name":"产品质检报告.pdf","url":"/uploads/红枣质检报告.pdf","type":"pdf"},{"name":"有机认证证书.pdf","url":"/uploads/有机认证.pdf","type":"pdf"}]',
 1, 1, 'approved', 4, NOW()),

(2,
 'AI数字名片 Pro版 年卡',
 '基于AI技术的智能数字名片，支持多模板、AI智能推荐、人脉管理、数据统计。企业家商务社交首选，让每一次相遇都有价值。',
 399.00, 80.00, 499.00, '企业家服务', '链客宝', 9999,
 '["https://picsum.photos/seed/chainke-digital-card-1/400/300","https://picsum.photos/seed/chainke-digital-card-2/400/300","https://picsum.photos/seed/chainke-digital-card-3/400/300"]',
 '{"版本":"Pro版年卡","有效期":"购买日起365天","模板数量":"50+精选模板","AI推荐次数":"无限次","人脉容量":"10000人","数据导出":"支持Excel/CSV"}',
 '<h3>核心功能</h3><ul><li>AI智能名片设计</li><li>多模板自由切换</li><li>扫码一键交换</li><li>人脉智能分类管理</li><li>交换数据分析看板</li><li>团队名片统一管理</li></ul><h3>适用人群</h3><p>企业家、销售精英、商务人士、创业者</p>',
 'AI,数字名片,企业家,商务,人脉管理',
 '[{"name":"产品使用手册.pdf","url":"/uploads/数字名片手册.pdf","type":"pdf"},{"name":"功能对比表.xlsx","url":"/uploads/功能对比.xlsx","type":"xlsx"}]',
 1, 2, 'approved', 4, NOW()),

(3,
 '企业法律顾问套餐 年度',
 '全年企业法律顾问服务，含合同审核、法律咨询、风险评估、知识产权保护等。专业律师团队1对1服务，企业法律问题一站式解决。',
 2980.00, 596.00, 3680.00, '企业服务', '法务通', 200,
 '["https://picsum.photos/seed/chainke-legal-1/400/300","https://picsum.photos/seed/chainke-legal-2/400/300","https://picsum.photos/seed/chainke-legal-3/400/300"]',
 '{"服务周期":"12个月","合同审核":"不限次数（≤10页/份）","法律咨询":"不限次数（工作日9:00-18:00）","律师分配":"3人专属服务组","响应时效":"4小时内回复","适用规模":"10-500人企业"}',
 '<h3>服务内容</h3><ul><li>日常法律咨询（电话/微信/邮件）</li><li>合同起草与审核（每年50份内）</li><li>企业规章制度审查</li><li>劳动人事法律支持</li><li>知识产权基础保护</li><li>律师函发送（5次/年）</li></ul><h3>服务流程</h3><p>在线下单 → 分配律师 → 建立服务群 → 全年无忧</p>',
 '法律顾问,企业服务,合同审核,知识产权,法律服务',
 '[{"name":"服务合同模板.pdf","url":"/uploads/法律顾问合同.pdf","type":"pdf"},{"name":"服务内容清单.pdf","url":"/uploads/服务清单.pdf","type":"pdf"}]',
 1, 3, 'approved', 4, NOW()),

(4,
 '筋膜枪 肌肉放松 静音款',
 '专业级肌肉筋膜枪，6档变速调节，超静音设计。运动后肌肉放松、日常疲劳缓解。Type-C快充，续航8小时。',
 298.00, 58.00, 368.00, '大健康', '舒肌宝', 1000,
 '["https://picsum.photos/seed/chainke-massage-gun-1/400/300","https://picsum.photos/seed/chainke-massage-gun-2/400/300","https://picsum.photos/seed/chainke-massage-gun-3/400/300"]',
 '{"型号":"S3 Pro","档位":"6档变速（1200-3200转/分）","噪音":"≤35dB（静音款）","电池":"2600mAh锂电池","续航":"约8小时","充电":"Type-C快充（2小时充满）","配件":"6种按摩头","重量":"约680g"}',
 '<h3>产品特点</h3><ul><li>超静音电机，使用不扰人</li><li>6档智能变速，满足不同需求</li><li>6种专业按摩头，全身适用</li><li>Type-C通用快充</li><li>人体工学手柄，久握不累</li></ul><h3>适用人群</h3><p>运动爱好者、办公室白领、久站人群、中老年人</p>',
 '筋膜枪,肌肉放松,按摩,大健康,运动恢复',
 '[{"name":"产品说明书.pdf","url":"/uploads/筋膜枪说明书.pdf","type":"pdf"},{"name":"CE认证证书.pdf","url":"/uploads/CE认证.pdf","type":"pdf"}]',
 1, 4, 'approved', 4, NOW()),

(5,
 '私域社群运营训练营',
 '21天线上实战训练营，从0到1掌握私域社群运营全流程。含直播授课、社群实操、1v1辅导、结业认证。限时赠送社群运营SOP手册。',
 1980.00, 396.00, 2580.00, '教育培训', '增长学堂', 300,
 '["https://picsum.photos/seed/chainke-training-1/400/300","https://picsum.photos/seed/chainke-training-2/400/300","https://picsum.photos/seed/chainke-training-3/400/300"]',
 '{"学习周期":"21天（含周末）","授课形式":"直播+录播+社群实操","课程数量":"15节主课+5次答疑","辅导形式":"1v1导师辅导","适合人群":"运营从业者/创业者/品牌方","结业认证":"颁发结业证书"}',
 '<h3>课程大纲</h3><ul><li>第一周：私域底层逻辑与定位</li><li>第二周：社群搭建与用户增长</li><li>第三周：转化变现与数据复盘</li></ul><h3>你将获得</h3><ul><li>一套完整的私域运营SOP</li><li>21天实操落地经验</li><li>行业人脉资源对接</li><li>结业证书+优秀学员推荐就业</li></ul>',
 '私域运营,社群运营,训练营,教育培训,增长',
 '[{"name":"课程大纲.pdf","url":"/uploads/训练营大纲.pdf","type":"pdf"},{"name":"讲师介绍.pdf","url":"/uploads/讲师介绍.pdf","type":"pdf"}]',
 1, 5, 'approved', 4, NOW()),

(6,
 '智能考勤一体机 人脸识别',
 'AI人脸识别考勤机，支持口罩识别、活体检测。超大存储容量，WiFi联网，手机APP远程管理。企业/学校/工地通用。',
 1280.00, 256.00, 1580.00, 'SaaS硬件', '云考勤', 800,
 '["https://picsum.photos/seed/chainke-attendance-1/400/300","https://picsum.photos/seed/chainke-attendance-2/400/300","https://picsum.photos/seed/chainke-attendance-3/400/300"]',
 '{"识别方式":"人脸识别（支持口罩识别）","屏幕":"8英寸IPS高清屏","存储":"10000张人脸 / 50000条记录","联网":"WiFi / 以太网","活体检测":"支持","APP管理":"iOS/Android双端","防水等级":"IP65","电源":"DC 12V/2A"}',
 '<h3>产品优势</h3><ul><li>AI深度学习算法，识别率>99.5%</li><li>支持戴口罩识别，防疫无忧</li><li>活体检测防照片/视频作弊</li><li>手机APP实时查看考勤报表</li><li>支持多班次/弹性打卡/加班审批</li></ul><h3>适用场景</h3><p>中小企业、学校、工厂、工地、办公楼</p>',
 '考勤机,人脸识别,智能硬件,企业管理,SaaS',
 '[{"name":"产品安装指南.pdf","url":"/uploads/考勤机安装指南.pdf","type":"pdf"},{"name":"APP操作手册.pdf","url":"/uploads/考勤APP手册.pdf","type":"pdf"},{"name":"3C认证证书.pdf","url":"/uploads/3C认证.pdf","type":"pdf"}]',
 1, 6, 'approved', 4, NOW());


-- ============================================================================
-- 订单数据
-- 订单1: buyer1(2) 购买 有机红枣(1) x2, promoter1(3) 推广
-- 订单2: buyer1(2) 购买 AI数字名片(2) x1, promoter1(3) 推广
-- 订单3: buyer1(2) 购买 筋膜枪(4) x1, 无推广员
-- ============================================================================
INSERT IGNORE INTO `orders` (`id`, `user_id`, `product_id`, `quantity`, `total_price`, `status`, `promoter_id`, `commission`, `created_at`) VALUES
(1, 2, 1, 2, 336.00, 'received', 3, 25.00, NOW()),
(2, 2, 2, 1, 399.00, 'paid',    3, 40.00, NOW()),
(3, 2, 4, 1, 298.00, 'shipped', NULL, 0.00,   NOW());


-- ============================================================================
-- 提现记录
-- 提现1: promoter1(3) 提现 15元, 已通过
-- 提现2: promoter1(3) 提现 10元, 待审核
-- ============================================================================
INSERT IGNORE INTO `withdrawals` (`id`, `user_id`, `amount`, `status`, `bank_info`, `created_at`) VALUES
(1, 3, 15.00, 'approved',
 '{"bank_name":"中国银行","card_number":"6222****1234","holder_name":"李四"}',
 NOW()),
(2, 3, 10.00, 'pending',
 '{"bank_name":"中国银行","card_number":"6222****1234","holder_name":"李四"}',
 NOW());


-- ============================================================================
-- 恢复外键约束检查
-- ============================================================================
SET FOREIGN_KEY_CHECKS = @OLD_FOREIGN_KEY_CHECKS;
