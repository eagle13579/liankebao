with open('/tmp/index_v2.html', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace('四大AI能力，重塑中韩跨境贸易全链路', '五大AI能力，重塑中韩跨境贸易全链路')
content = content.replace('Four AI capabilities', 'Five AI capabilities')
content = content.replace('4가지 AI 역량', '5가지 AI 역량')
content = content.replace('grid-template-columns: repeat(4, 1fr);', 'grid-template-columns: repeat(5, 1fr);')

card5 = '\n\n            <!-- Card 5: AI Digital Business Card -->\n            <a href="https://liankebao.top/business-card" style="text-decoration:none;display:block;padding:32px 24px;text-align:center;" class="glass-card" target="_blank">\n                <div style="width: 56px; height: 56px; border-radius: 16px; background: linear-gradient(135deg, rgba(16,185,129,0.15), rgba(56,189,248,0.10)); display: flex; align-items: center; justify-content: center; margin: 0 auto 20px;">\n                    <i class="bi bi-credit-card-2-front" style="font-size: 26px; color: #10B981;"></i>\n                </div>\n                <h3 class="gold-purple-text" style="font-size: 18px; font-weight: 700; margin-bottom: 10px;"\n                    data-lang-zh="AI数智名片"\n                    data-lang-ko="AI \ub514\uc9c0\ud138 \uba85\ud568"\n                    data-lang-en="AI Digital Business Card">AI\u6570\u667a\u540d\u7247</h3>\n                <p style="font-size: 14px; line-height: 1.7; margin: 0;" class="dark:text-slate-400 light:text-slate-500"\n                   data-lang-zh="\u7528AI\u751f\u6210\u4f01\u4e1a\u6570\u5b57\u540d\u7247\uff0c\u591a\u8bed\u8a00\u5c55\u793a\u3001\u4e00\u952e\u5206\u4eab\u3001\u5fae\u4fe1\u96c6\u6210\u3002\u6570\u636e\u4e0e\u4e2d\u97e9\u51fa\u6d77\u6570\u667a\u6e2f\u5171\u4eab\uff0c\u4e00\u6b21\u521b\u5efa\u5168\u57df\u53ef\u7528"\n                   data-lang-ko="AI\ub85c \uae30\uc5c5 \ub514\uc9c0\ud138 \uba85\ud568\uc744 \uc0dd\uc131\ud558\uace0, \ub2e4\uad6d\uc5b4 \uc9c0\uc6d0, \uc6d0\ud074\ub9ad \uacf5\uc720, \uc704\ucc57 \ud1b5\ud569\uc744 \uc81c\uacf5\ud569\ub2c8\ub2e4."\n                   data-lang-en="Create AI digital business cards with multi-language, one-click share, and WeChat integration. Share data across the entire platform.">\n                   \u7528AI\u751f\u6210\u4f01\u4e1a\u6570\u5b57\u540d\u7247\uff0c\u591a\u8bed\u8a00\u5c55\u793a\u3001\u4e00\u952e\u5206\u4eab\u3001\u5fae\u4fe1\u96c6\u6210\u3002\u6570\u636e\u4e0e\u4e2d\u97e9\u51fa\u6d77\u6570\u667a\u6e2f\u5171\u4eab\uff0c\u4e00\u6b21\u521b\u5efa\u5168\u57df\u53ef\u7528</p>\n            </a>'

content = content.replace('            </a>\n        </div>\n    </div>\n</section>',
                          f'            </a>{card5}\n        </div>\n    </div>\n</section>')

with open('/tmp/index_v2_modified.html', 'w', encoding='utf-8') as f:
    f.write(content)

import os
print(f'Modified: {len(content)} bytes, saved to /tmp/index_v2_modified.html')
