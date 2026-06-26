"""数据安全核心模块 (Core)

包含：
  - sanitizer.py         : 安全消毒引擎 (Unicode/SSRF/SQL/XSS/JSON注入防护)
  - data_contract.py     : 数据契约系统 (ContractYAML/Validator/Manager)
  - data_write_gateway.py: 数据写入验证网关 (5步流水线/熔断/降级)
  - anomaly_scorer.py    : 异常评分引擎 (5维基线检测)
"""
