"""
链客宝 多语言路由配置
为每个语言创建独立URL路径 (/zh/ /en/ /ko/)
"""
import os
import json

SUPPORTED_LANGS = {
    "zh": {
        "code": "zh-CN",
        "name": "中文",
        "hreflang": "zh-CN",
        "domain": "liankebao.top",
        "path_prefix": "/zh"
    },
    "en": {
        "code": "en",
        "name": "English",
        "hreflang": "en",
        "domain": "liankebao.top",
        "path_prefix": "/en"
    },
    "ko": {
        "code": "ko",
        "name": "한국어",
        "hreflang": "ko",
        "domain": "liankebao.top",
        "path_prefix": "/ko"
    }
}

NGINX_HREFLANG_CONFIG = """
# ========================================
# 链客宝 多语言 + hreflang 配置
# ========================================

# 语言检测 (Cookie > Accept-Language > 默认中文)
map $cookie_lang $lang {
    default "zh";
    ~*zh "zh";
    ~*en "en";
    ~*ko "ko";
}

map $lang $lang_suffix {
    zh "";
    en "/en";
    ko "/ko";
}

# 多语言前端路由
location ~* ^/(zh|en|ko)(/.*)?$ {
    set $lang_code $1;
    set $original_path $2;
    if ($original_path = "") {
        set $original_path "/";
    }
    
    # 设置语言cookie
    add_header Set-Cookie "lang=$lang_code; Path=/; Max-Age=2592000; SameSite=Lax";
    
    # hreflang headers
    add_header Link '<https://liankebao.top{path}> rel="alternate" hreflang="zh-CN"';
    add_header Link '<https://liankebao.top/en{path}> rel="alternate" hreflang="en"';
    add_header Link '<https://liankebao.top/ko{path}> rel="alternate" hreflang="ko"';
    add_header Link '<https://liankebao.top{path}> rel="alternate" hreflang="x-default"';
    
    try_files $uri $uri/ /index.html;
}

# 根路径: 根据语言检测重定向
location = / {
    if ($lang != "zh") {
        rewrite ^ /$lang$uri redirect;
    }
    try_files $uri $uri/ /index.html;
}

# 默认SPA路由
location / {
    try_files $uri $uri/ /index.html;
}
"""


def generate_hreflang_config():
    """生成hreflang nginx配置"""
    config_path = os.path.join(os.path.dirname(__file__), "..", "deploy", "nginx", "hreflang.conf")
    with open(config_path, 'w', encoding='utf-8') as f:
        f.write(NGINX_HREFLANG_CONFIG)
    print(f"hreflang nginx配置已生成: {config_path}")

    # 同时更新chainke.conf中的hreflang部分
    chainke_conf = os.path.join(os.path.dirname(__file__), "..", "deploy", "nginx", "chainke.conf")
    include_line = "\n# 多语言hreflang配置\ninclude /etc/nginx/hreflang.conf;\n"
    
    if os.path.exists(chainke_conf):
        with open(chainke_conf, 'r', encoding='utf-8') as f:
            content = f.read()
        if 'hreflang.conf' not in content:
            # Add include at appropriate location
            content = content.replace(
                "error_page 500 502 503 504 /50x.html;",
                f"error_page 500 502 503 504 /50x.html;{include_line}"
            )
            with open(chainke_conf, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"chainke.conf 已更新: 添加hreflang include")


def generate_frontend_i18n_router_config():
    """生成前端多语言路由配置"""
    config = {
        "supported_langs": list(SUPPORTED_LANGS.keys()),
        "default_lang": "zh",
        "lang_config": SUPPORTED_LANGS,
        "cookie_name": "lang",
        "local_storage_key": "chainke_lang",
        "url_strategy": "path_prefix",  # path_prefix | subdomain | query_param
    }
    config_path = os.path.join(os.path.dirname(__file__), "..", "src", "i18n", "router_config.json")
    with open(config_path, 'w', encoding='utf-8', ensure_ascii=False) as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    print(f"前端路由配置已生成: {config_path}")


if __name__ == "__main__":
    print("=" * 50)
    print("链客宝 多语言路由生成器")
    print("=" * 50)
    generate_hreflang_config()
    generate_frontend_i18n_router_config()
    lang_list = [f'{v["name"]}({k})' for k, v in SUPPORTED_LANGS.items()]
    print(f"\n支持语言: {', '.join(lang_list)}")
