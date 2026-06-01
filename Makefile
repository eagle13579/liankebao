SHELL := /bin/bash
.PHONY: install dev build test lint clean docker-up docker-down migrate help

BACKEND_DIR := backend
VENV_DIR := $(BACKEND_DIR)/venv_new
PYTHON := $(VENV_DIR)/bin/python
PIP := $(VENV_DIR)/bin/pip
UVICORN := $(VENV_DIR)/bin/uvicorn

help: ## 显示帮助信息
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\\033[36m%-20s\\033[0m %s\\n", $$1, $$2}'

install: ## 安装后端依赖
	$(PIP) install -r $(BACKEND_DIR)/requirements.txt
	$(PIP) install ruff pre-commit pytest pytest-asyncio pytest-cov bandit
	pre-commit install

dev: ## 启动后端开发服务器（热重载）
	$(UVICORN) app.main:app --reload --host 0.0.0.0 --port 8000

build: ## 构建前端静态文件
	cd $(BACKEND_DIR)/.. && npm run build

test: ## 运行后端测试
	cd $(BACKEND_DIR) && $(PYTHON) -m pytest tests/ -v

test-cov: ## 运行后端测试并生成覆盖率
	cd $(BACKEND_DIR) && $(PYTHON) -m pytest tests/ -v --cov=app --cov-report=term --cov-report=html

test-cov-min: ## 运行测试并检查覆盖率>=30%
	cd $(BACKEND_DIR) && $(PYTHON) -m pytest tests/ -v --cov=app --cov-fail-under=30

lint: ## 运行 ruff 代码检查
	cd $(BACKEND_DIR) && ruff check . --fix
	cd $(BACKEND_DIR) && ruff format .

lint-check: ## 仅检查代码（不自动修复）
	cd $(BACKEND_DIR) && ruff check .
	cd $(BACKEND_DIR) && ruff format --check .

security: ## 运行安全检查
	cd $(BACKEND_DIR) && bandit -c pyproject.toml -r app/ || true

security-all: ## 运行所有安全检查（含预提交和审计脚本）
	cd $(BACKEND_DIR) && bandit -c pyproject.toml -r app/ || true
	bash scripts/security-check.sh || true

industrialize: ## 运行工业化全景扫描与评分
	cd $(BACKEND_DIR)/.. && python scripts/industrialize_score.py

clean: ## 清理缓存和临时文件
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	rm -rf .coverage htmlcov

docker-up: ## 启动 Docker 服务（生产）
	docker compose up -d

docker-down: ## 停止 Docker 服务
	docker compose down

migrate: ## 运行数据库迁移
	cd $(BACKEND_DIR) && alembic upgrade head

migrate-new: ## 创建新的数据库迁移
	cd $(BACKEND_DIR) && alembic revision --autogenerate -m "$(name)"

pre-commit-run: ## 手动运行 pre-commit 检查
	pre-commit run --all-files

pipeline: ## 运行完整工业化流水线（lint → test → security → score）
	@echo "=== 链客宝 工业化流水线 ==="
	@echo ""
	@echo "--- Step 1: Lint ---"
	$(MAKE) lint-check || true
	@echo ""
	@echo "--- Step 2: Test ---"
	$(MAKE) test-cov-min || true
	@echo ""
	@echo "--- Step 3: Security ---"
	$(MAKE) security-all || true
	@echo ""
	@echo "--- Step 4: Industrialize Score ---"
	$(MAKE) industrialize || true
	@echo ""
	@echo "=== 流水线完成 ==="
