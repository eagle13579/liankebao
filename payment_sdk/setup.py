"""liankebao-payment-sdk — setup.py (兼容 pip install -e .)

推荐使用 pyproject.toml 构建。此 setup.py 仅用于 pip install -e . 开发安装。
"""

from setuptools import find_packages, setup

setup(
    name="liankebao-payment-sdk",
    version="0.1.0",
    description="链客宝AI支付模块独立SDK — 微信支付V2/V3、支付宝（预留）",
    long_description=open("README.md", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    author="链客宝AI团队",
    author_email="support@go-aiport.com",
    license="Proprietary",
    python_requires=">=3.11",
    packages=find_packages(include=["payment_sdk", "payment_sdk.*"]),
    install_requires=[
        "httpx>=0.27.0",
        "cryptography>=42.0.0",
    ],
    extras_require={
        "dev": ["pytest>=8.0", "pytest-asyncio>=0.24"],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
)
