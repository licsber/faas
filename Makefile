# FaaS 通用部署工具
# 支持多函数管理，支持 CPU/GPU 双配置
# 支持 DRYRUN 模式: make deploy DRYRUN=true

.PHONY: help dashboard deploy list status clean

# 可配置变量
# FUNCTION 为空时部署所有函数
FUNCTION    ?=
NAMESPACE   ?= nuclio
CUDA        ?= false
DRYRUN      ?= false

# 颜色定义
BLUE   := \033[36m
GREEN  := \033[32m
YELLOW := \033[33m
RED    := \033[31m
RESET  := \033[0m

# 检测 Docker 权限
# 如果当前用户无法直接访问 docker，则使用 sudo
DOCKER_CHECK := $(shell docker ps > /dev/null 2>&1 && echo "ok" || echo "no")
ifeq ($(DOCKER_CHECK),ok)
  DOCKER_PREFIX :=
  NUCTL_PREFIX  :=
else
  DOCKER_PREFIX := sudo
  NUCTL_PREFIX  := sudo
  $(info $(YELLOW)ℹ️  检测到当前用户没有 Docker 权限，将自动使用 sudo$(RESET))
endif

# 执行或打印命令的宏
# 简单命令的执行/打印宏（仅用于单行命令）
ifeq ($(DRYRUN),true)
  RUN = @echo "[DRYRUN] $1"
else
  RUN = @echo "> $1" && $1
endif

# 获取所有函数名称
ALL_FUNCTIONS := $(shell ls -1 functions/ 2>/dev/null)

help:
	@echo "$(BLUE)╔══════════════════════════════════════════════════════╗$(RESET)"
	@echo "$(BLUE)║         AI 检测平台 - FaaS 部署工具                  ║$(RESET)"
	@echo "$(BLUE)╚══════════════════════════════════════════════════════╝$(RESET)"
	@echo ""
	@echo "$(GREEN)基础命令:$(RESET)"
	@echo "  $(YELLOW)make dashboard$(RESET)              启动 Dashboard"
	@echo "  $(YELLOW)make deploy$(RESET)                 部署所有检测器 (CPU)"
	@echo "  $(YELLOW)make deploy CUDA=true$(RESET)       部署所有检测器 (GPU)"
	@echo "  $(YELLOW)make list$(RESET)                   列出本地可用检测器"
	@echo "  $(YELLOW)make status$(RESET)                 查看远程检测器状态"
	@echo "  $(YELLOW)make clean$(RESET)                  删除所有检测器"
	@echo ""
	@echo "$(GREEN)预构建镜像命令:$(RESET)"
	@echo "  $(YELLOW)make deploy-prebuilt FUNCTION=xxx$(RESET)       使用预构建镜像部署"
	@echo "  $(YELLOW)make build-image FUNCTION=xxx$(RESET)           本地构建镜像"
	@echo ""
	@echo "$(GREEN)开发命令:$(RESET)"
	@echo "  $(YELLOW)make new-function NAME=xxx$(RESET)  基于模板创建新检测器"
	@echo ""
	@echo "$(GREEN)带参数用法:$(RESET)"
	@echo "  $(YELLOW)make deploy FUNCTION=xxx$(RESET)              部署指定检测器"
	@echo "  $(YELLOW)make deploy FUNCTION=xxx CUDA=true$(RESET)    GPU部署指定检测器"
	@echo "  $(YELLOW)make list NAMESPACE=default$(RESET)            指定命名空间"
	@echo "  $(YELLOW)make status FUNCTION=xxx$(RESET)               查看指定检测器"
	@echo ""
	@echo "$(GREEN)DRYRUN 模式 (只打印命令，不执行):$(RESET)"
	@echo "  $(YELLOW)make deploy DRYRUN=true$(RESET)                预览部署命令"
	@echo "  $(YELLOW)make clean DRYRUN=true$(RESET)                 预览清理命令"
	@echo ""
	@echo "$(GREEN)可用检测器:$(RESET)"
	@ls -1 functions/ 2>/dev/null | sed 's/^/  • /' || echo "  (暂无)"

dashboard:
	@echo "$(BLUE)启动 Nuclio Dashboard...$(RESET)"
ifeq ($(DRYRUN),true)
	@echo "$(YELLOW)[DRYRUN]$(RESET) 检查 Dashboard 是否已运行"
	@echo "$(YELLOW)[DRYRUN]$(RESET) $(DOCKER_PREFIX) docker ps --filter name=nuclio-dashboard --filter status=running -q"
	@echo "$(YELLOW)[DRYRUN]$(RESET) $(DOCKER_PREFIX) docker run -d -p 8070:8070 -v /var/run/docker.sock:/var/run/docker.sock --name nuclio-dashboard quay.io/nuclio/dashboard:stable-amd64"
else
	@container_id=$$($(DOCKER_PREFIX) docker ps --filter name=nuclio-dashboard --filter status=running -q); \
	if [ -n "$$container_id" ]; then \
		echo "$(GREEN)✓ Dashboard 已在运行: http://localhost:8070$(RESET)"; \
	else \
		stopped=$$($(DOCKER_PREFIX) docker ps -a --filter name=nuclio-dashboard --filter status=exited -q); \
		if [ -n "$$stopped" ]; then \
			echo "$(YELLOW)检测到 Dashboard 容器已停止，正在启动...$(RESET)"; \
			$(DOCKER_PREFIX) docker start nuclio-dashboard; \
			echo "$(GREEN)✓ Dashboard 已启动: http://localhost:8070$(RESET)"; \
		else \
			echo "> $(DOCKER_PREFIX) docker run -d -p 8070:8070 -v /var/run/docker.sock:/var/run/docker.sock --name nuclio-dashboard quay.io/nuclio/dashboard:stable-amd64"; \
			$(DOCKER_PREFIX) docker run -d \
				-p 8070:8070 \
				-v /var/run/docker.sock:/var/run/docker.sock \
				--name nuclio-dashboard \
				quay.io/nuclio/dashboard:stable-amd64; \
			echo "$(GREEN)✓ Dashboard 已创建: http://localhost:8070$(RESET)"; \
		fi; \
	fi
endif

# 部署函数（FUNCTION 为空时部署所有）
deploy:
ifeq ($(FUNCTION),)
	@echo "$(BLUE)部署所有函数 ($(if $(filter true,$(CUDA)),GPU,CPU))...$(RESET)"
	@echo "$(YELLOW)提示: nuctl 会生成本机架构的镜像$(RESET)"
	@for func in $(ALL_FUNCTIONS); do \
		$(MAKE) deploy FUNCTION=$$func CUDA=$(CUDA) DRYRUN=$(DRYRUN); \
	done
else
	@echo "$(BLUE)部署 $(FUNCTION) ($(if $(filter true,$(CUDA)),GPU,CPU))...$(RESET)"
	$(if $(filter true,$(DRYRUN)),@echo "$(YELLOW)[DRYRUN]$(RESET) nuctl deploy $(FUNCTION)",\
		$(call _deploy_single,$(FUNCTION),$(CUDA)))
endif

define _deploy_single
	@config_file="functions/$(1)/function$(if $(filter true,$(2)),-gpu,).yaml"; \
	func_name="$(1)$(if $(filter true,$(2)),-gpu,)"; \
	echo "$(BLUE)>$(RESET) $(NUCTL_PREFIX) nuctl deploy $$func_name --file $$config_file --path functions/$(1) --namespace $(NAMESPACE)"; \
	$(NUCTL_PREFIX) nuctl deploy $$func_name \
		--file $$config_file \
		--path functions/$(1) \
		--namespace $(NAMESPACE) \
		--project-name default \
		--no-pull
endef

# 使用预构建镜像部署（适合国内服务器）
deploy-prebuilt:
ifeq ($(FUNCTION),)
	@echo "$(RED)错误: 使用预构建镜像时必须指定 FUNCTION$(RESET)"
	@echo "用法: $(YELLOW)make deploy-prebuilt FUNCTION=nsfw-detector$(RESET)"
	@exit 1
endif
	@echo "$(BLUE)部署 $(FUNCTION) (使用预构建镜像)...$(RESET)"
	@echo "$(YELLOW)提示: 确保已设置 Docker Hub 镜像地址$(RESET)"
	@config_file="functions/$(FUNCTION)/function-prebuilt.yaml"; \
	if [ ! -f "$$config_file" ]; then \
		echo "$(RED)错误: 预构建配置文件不存在: $$config_file$(RESET)"; \
		exit 1; \
	fi; \
	echo "$(BLUE)>$(RESET) $(NUCTL_PREFIX) nuctl deploy $(FUNCTION) --file $$config_file --namespace $(NAMESPACE)"; \
	$(NUCTL_PREFIX) nuctl deploy $(FUNCTION) \
		--file $$config_file \
		--namespace $(NAMESPACE) \
		--project-name default

# 手动构建并推送镜像（本地使用）
build-image:
ifeq ($(FUNCTION),)
	@echo "$(RED)错误: 必须指定 FUNCTION$(RESET)"
	@echo "用法: $(YELLOW)make build-image FUNCTION=nsfw-detector REGISTRY=your-registry$(RESET)"
	@exit 1
endif
	@registry="$(if $(REGISTRY),$(REGISTRY),docker.io/licsber)"; \
	echo "$(BLUE)构建 $(FUNCTION) 镜像...$(RESET)"; \
	docker build \
		-f docker/Dockerfile.$(FUNCTION) \
		-t $$registry/faas-$(FUNCTION):latest \
		--platform linux/amd64 \
		.; \
	echo "$(GREEN)✓ 镜像构建成功: $$registry/faas-$(FUNCTION):latest$(RESET)"; \
	echo "$(YELLOW)推送命令: docker push $$registry/faas-$(FUNCTION):latest$(RESET)"

list:
	@echo "$(BLUE)本地可用函数:$(RESET)"
	@echo ""
	@for dir in functions/*/; do \
		if [ -f "$$dir/function.yaml" ]; then \
			name=$$(basename "$$dir"); \
			desc=$$(grep "description:" "$$dir/function.yaml" | head -1 | sed 's/.*description: *//' | tr -d '"' || echo "无描述"); \
			echo "  $(YELLOW)• $$name$(RESET)"; \
			echo "    $$desc"; \
			if [ -f "$$dir/function-gpu.yaml" ]; then \
				echo "    $(GREEN)✓ 支持 GPU 版本$(RESET)"; \
			fi; \
			echo ""; \
		fi \
	done
	@echo "$(GREEN)部署命令:$(RESET)"
	@echo "  make deploy                    # 部署所有函数 (CPU)"
	@echo "  make deploy FUNCTION=<name>    # 部署指定函数"

status:
ifeq ($(FUNCTION),)
	@echo "$(BLUE)查看所有函数状态:$(RESET)"
	@$(call RUN,$(NUCTL_PREFIX) nuctl get function -n $(NAMESPACE) 2>/dev/null || echo "$(RED)未找到函数$(RESET)")
else
	@echo "$(BLUE)查看 $(FUNCTION) 状态:$(RESET)"
	@$(call RUN,$(NUCTL_PREFIX) nuctl get function $(FUNCTION) -n $(NAMESPACE) -o wide 2>/dev/null || \
		echo "$(RED)函数未找到$(RESET)")
endif

clean:
	@echo "$(YELLOW)清理所有检测器...$(RESET)"
	@functions=$$($(NUCTL_PREFIX) nuctl get function -n $(NAMESPACE) -o json 2>/dev/null | python3 -c "import sys,json; data=json.load(sys.stdin); print(' '.join([f.get('metadata',{}).get('name','') for f in data]))" 2>/dev/null); \
	for func in $$functions; do \
		if [ -n "$$func" ]; then \
			echo "删除: $$func"; \
			$(NUCTL_PREFIX) nuctl delete function $$func -n $(NAMESPACE) 2>/dev/null || echo "跳过: $$func"; \
		fi; \
	done
	@echo "$(GREEN)✓ 清理完成$(RESET)"

# 创建新检测器
new-function:
ifndef NAME
	@echo "$(RED)错误: 请提供 NAME 参数$(RESET)"
	@echo "用法: $(YELLOW)make new-function NAME=my-detector$(RESET)"
	@exit 1
endif
	@if [ -d "functions/$(NAME)" ]; then \
		echo "$(RED)错误: 检测器 '$(NAME)' 已存在$(RESET)"; \
		exit 1; \
	fi
	@echo "$(BLUE)创建新检测器: $(NAME)...$(RESET)"
	@cp -r templates/python-detector functions/$(NAME)
	@# 替换模板中的占位符
	@sed -i '' 's/your-detector-name/$(NAME)/g' functions/$(NAME)/function.yaml 2>/dev/null || sed -i 's/your-detector-name/$(NAME)/g' functions/$(NAME)/function.yaml
	@sed -i '' 's/your-detector-name/$(NAME)/g' functions/$(NAME)/function-gpu.yaml 2>/dev/null || sed -i 's/your-detector-name/$(NAME)/g' functions/$(NAME)/function-gpu.yaml
	@sed -i '' 's|./functions/your-detector-name|./functions/$(NAME)|g' functions/$(NAME)/function.yaml 2>/dev/null || sed -i 's|./functions/your-detector-name|./functions/$(NAME)|g' functions/$(NAME)/function.yaml
	@sed -i '' 's|./functions/your-detector-name|./functions/$(NAME)|g' functions/$(NAME)/function-gpu.yaml 2>/dev/null || sed -i 's|./functions/your-detector-name|./functions/$(NAME)|g' functions/$(NAME)/function-gpu.yaml
	@echo "$(GREEN)✓ 检测器 '$(NAME)' 创建成功$(RESET)"
	@echo ""
	@echo "$(YELLOW)下一步:$(RESET)"
	@echo "  1. 编辑 $(YELLOW)functions/$(NAME)/main.py$(RESET) 实现检测逻辑"
	@echo "  2. 编辑 $(YELLOW)functions/$(NAME)/function.yaml$(RESET) 修改配置"
	@echo "  3. 部署测试: $(YELLOW)make deploy FUNCTION=$(NAME)$(RESET)"
