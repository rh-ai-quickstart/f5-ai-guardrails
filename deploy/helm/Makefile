# Makefile for RAG Deployment
# Replaces the original deploy.sh script with additional uninstall functionality

# Use bash if available, otherwise use sh
SHELL := $(shell which bash 2>/dev/null || which sh)

# Color definitions (using tput for better portability, fallback to ANSI)
BLUE := $(shell tput setaf 4 2>/dev/null || echo '\033[0;34m')
GREEN := $(shell tput setaf 2 2>/dev/null || echo '\033[0;32m')
YELLOW := $(shell tput setaf 3 2>/dev/null || echo '\033[0;33m')
RED := $(shell tput setaf 1 2>/dev/null || echo '\033[0;31m')
NC := $(shell tput sgr0 2>/dev/null || echo '\033[0m')

# NAMESPACE check will be done in individual targets that need it

MAKEFLAGS += --no-print-directory

# Set default target
.DEFAULT_GOAL := help

# Default values
VERSION ?= 0.2.22
POSTGRES_USER ?= postgres
POSTGRES_PASSWORD ?= rag_password
POSTGRES_DBNAME ?= rag_blueprint
# HF_TOKEN will be managed by the get_hf_token helper function
RAG_CHART := rag
TOLERATIONS_TEMPLATE=[{"key":"$(1)","effect":"NoSchedule","operator":"Exists"}]

# F5 AI Guardrails teardown (used by uninstall; keep in sync with F5_* namespace overrides)
SECURITYOPERATOR_NAME ?= security-operator-demo
F5_AI_SECURITY_NAMESPACE ?= f5-ai-sec
F5_MODERATOR_NS ?= cai-moderator
F5_PREFECT_NS ?= prefect
F5_INFERENCE_NS ?= f5-ai-sec-inference
# Operator installs the inference Helm release with this name in F5_INFERENCE_NS (override only if F5 changes it).
F5_INFERENCE_HELM_RELEASE ?= f5-ai-sec-inference
F5_OPERATOR_NS ?= $(F5_AI_SECURITY_NAMESPACE)
CAI_MODERATOR_NS ?= $(F5_MODERATOR_NS)
OPERATOR_SUBSCRIPTION ?= f5-ai-security-operator
GUARDRAILS_PROJECT_NS ?= $(F5_AI_SECURITY_NAMESPACE) $(F5_MODERATOR_NS) $(F5_INFERENCE_NS) $(F5_PREFECT_NS)

# F5 AI Security Operator + Guardrails (Helm chart in ./f5-ai-security)
F5_AI_SECURITY_CHART ?= f5-ai-security
F5_AI_SECURITY_VALUES ?= f5-ai-security-values.yaml
F5_AI_SECURITY_VALUES_EXAMPLE ?= f5-ai-security-values.yaml.example
F5_AI_SECURITY_RELEASE ?= f5-ai-security
OPERATOR_CSV ?= f5-ai-security-operator.v0.8.1
# Optional: extra helm --set/--set-string/--set-file for F5 chart (quoted as needed)
EXTRA_HELM_F5_ARGS ?=
# First install: --create-namespace plus chart Namespace manifests can race; --take-ownership smooths adoption (Helm 3.13+). Clear with F5_HELM_FLAGS=
F5_HELM_FLAGS ?= --take-ownership
# F5 helm first-pass retries (namespace / API races on cold clusters)
F5_HELM_MAX_ATTEMPTS ?= 8
F5_HELM_RETRY_SLEEP ?= 6
# OpenShift: pre-apply inference model SCC (operator SA cannot create SCCs). Set to 1 to skip.
SKIP_F5_INFERENCE_SCC ?= 0
# After install: delete Pending KubeAI model pods once after a wait (transient Insufficient cpu/gpu only). Set 1 to enable.
F5_INFERENCE_PENDING_POD_DELETE ?= 0
F5_INFERENCE_SCHEDULE_WAIT_SECONDS ?= 90
# Set REQUIRE_GPU=1 so validate-infra fails if no node advertises nvidia.com/gpu (default: warn only)
# SKIP_INFRA_CHECK=1 skips validate-infra before install / install-f5-ai-security
# KServe webhooks need backing pods; CRDs alone are not enough (avoid "no endpoints" on helm install)
KSERVE_WEBHOOK_NAMESPACE ?= redhat-ods-applications
KSERVE_WEBHOOK_SERVICE ?= kserve-webhook-server-service
KSERVE_WEBHOOK_WAIT_SECONDS ?= 300
# Moderator public URL: first DNS label + oc get ingress.config cluster (.spec.domain). Set MODERATOR_HOST_AUTO=false
# to use securityOperator.moderator.baseUrl and routes.hostname from values only. Clear prefix: make ... MODERATOR_HOST_PREFIX=
MODERATOR_HOST_AUTO ?= true
MODERATOR_HOST_PREFIX ?= aisec

# Values file management
VALUES_FILE := rag-values.yaml
VALUES_EXAMPLE := rag-values.yaml.example

# Repo root (this file is deploy/helm/Makefile) and frontend for local UI
REPO_ROOT := $(abspath $(dir $(abspath $(lastword $(MAKEFILE_LIST))))/../..)
FRONTEND_DIR := $(REPO_ROOT)/frontend
UI_PIDFILE := $(REPO_ROOT)/.f5-guardrails-ui-local.pid
UI_LOGFILE := $(REPO_ROOT)/.f5-guardrails-ui-local.log

# Helper function to check and create values file
define check_values_file
	@if [ ! -f "$(VALUES_FILE)" ]; then \
		if [ -f "$(VALUES_EXAMPLE)" ]; then \
			echo -e "$(YELLOW)[INFO]$(NC) Values file not found. Creating from example..."; \
			cp "$(VALUES_EXAMPLE)" "$(VALUES_FILE)"; \
			if [ -z "$(LLM)" ]; then \
				echo -e ""; \
				echo -e "$(GREEN)╔══════════════════════════════════════════════════════════════════════════╗$(NC)"; \
				echo -e "$(GREEN)║                                                                          ║$(NC)"; \
				echo -e "$(GREEN)║  $(YELLOW)⚠️  IMPORTANT: Configuration Required$(GREEN)      	                           ║$(NC)"; \
				echo -e "$(GREEN)║                                                                          ║$(NC)"; \
				echo -e "$(GREEN)║  $(NC)Configuration file has been initialized: $(BLUE)rag-values.yaml$(GREEN)     	   ║$(NC)"; \
				echo -e "$(GREEN)║                                                                          ║$(NC)"; \
				echo -e "$(GREEN)║  $(YELLOW)Before continuing, you MUST configure at least:$(GREEN)                         ║$(NC)"; \
				echo -e "$(GREEN)║                                                                          ║$(NC)"; \
				echo -e "$(GREEN)║  $(RED)1. Enable at least ONE model$(GREEN) in the global.models section               ║$(NC)"; \
				echo -e "$(GREEN)║     $(NC)Set $(BLUE)enabled: true$(NC) for your chosen model$(GREEN)                              ║$(NC)"; \
				echo -e "$(GREEN)║                                                                          ║$(NC)"; \
				echo -e "$(GREEN)║  $(YELLOW)2. Add your Hugging Face token$(GREEN) (required for model downloads)           ║$(NC)"; \
				echo -e "$(GREEN)║     $(NC)Get token from: $(BLUE)https://huggingface.co/settings/tokens$(GREEN)               ║$(NC)"; \
				echo -e "$(GREEN)║                                                                          ║$(NC)"; \
				echo -e "$(GREEN)║  $(BLUE)📝 ACTION REQUIRED:$(GREEN)                                                     ║$(NC)"; \
				echo -e "$(GREEN)║     $(NC)Open a new terminal window and edit the configuration file:$(GREEN)          ║$(NC)"; \
				echo -e "$(GREEN)║     $(BLUE)nano rag-values.yaml$(GREEN)  or  $(BLUE)vim rag-values.yaml$(GREEN)                        ║$(NC)"; \
				echo -e "$(GREEN)║                                                                          ║$(NC)"; \
				echo -e "$(GREEN)║     $(NC)After editing, save the file and return here to continue.$(GREEN)            ║$(NC)"; \
				echo -e "$(GREEN)║                                                                          ║$(NC)"; \
				echo -e "$(GREEN)╚══════════════════════════════════════════════════════════════════════════╝$(NC)"; \
				echo -e ""; \
				echo -e "$(YELLOW)[WAITING]$(NC) Configure rag-values.yaml in another terminal, then press Enter..."; \
				read -p "" continue; \
				echo -e "$(BLUE)[INFO]$(NC) Continuing with installation..."; \
				echo -e ""; \
			else \
				echo -e "$(GREEN)[SUCCESS]$(NC) Using LLM model from command line: $(LLM)"; \
				echo -e ""; \
			fi; \
		else \
			echo -e "$(RED)[ERROR]$(NC) Neither $(VALUES_FILE) nor $(VALUES_EXAMPLE) found."; \
			echo -e "$(BLUE)[INFO]$(NC) Please create $(VALUES_FILE) with your configuration."; \
			exit 1; \
		fi; \
	fi; \
	$(call validate_values_file)
endef

# Helper function to validate values file
define validate_values_file
	echo -e "$(BLUE)[INFO]$(NC) Validating configuration values..."; \
	HF_TOKEN=$$(grep -A 40 "^llm-service:" "$(VALUES_FILE)" | grep "hf_token:" | head -1 | sed 's/.*hf_token: *//' | tr -d '"' | tr -d ' '); \
	UPDATED=0; \
	if [ -z "$$HF_TOKEN" ] || [ "$$HF_TOKEN" = "" ]; then \
		echo -e "$(YELLOW)[WARNING]$(NC) Hugging Face token is not set. Model downloads may fail."; \
		echo -e "$(BLUE)[INFO]$(NC) Get your token from: https://huggingface.co/settings/tokens"; \
		echo -e ""; \
		read -p "Enter your Hugging Face token (or press Enter to skip): " hf_input; \
		if [ -n "$$hf_input" ]; then \
			sed -i.bak "/^llm-service:/,/^[^ ]/ s|hf_token:.*|hf_token: \"$$hf_input\"|" "$(VALUES_FILE)"; \
			echo -e "$(GREEN)[SUCCESS]$(NC) Hugging Face token saved to configuration."; \
			UPDATED=1; \
		else \
			echo -e "$(YELLOW)[WARNING]$(NC) Hugging Face token not provided. Model downloads may fail."; \
		fi; \
		echo -e ""; \
	fi; \
	if [ $$UPDATED -eq 1 ]; then \
		echo -e "$(GREEN)[SUCCESS]$(NC) Configuration updated. Proceeding with installation..."; \
		echo -e ""; \
	fi; \
	rm -f "$(VALUES_FILE).bak" 2>/dev/null || true
endef

# If using extra tools that require API Keys set the LLAMA_STACK_ENV variable with key, value pairs
# LLAMA_STACK_ENV ?= {Key1: "Value1", Key2: "Value2" etc.}


helm_pgvector_args = \
    --set pgvector.secret.user=$(POSTGRES_USER) \
    --set pgvector.secret.password=$(POSTGRES_PASSWORD) \
    --set pgvector.secret.dbname=$(POSTGRES_DBNAME)

helm_llm_service_args = \
    --set llm-service.secret.hf_token=$(HF_TOKEN) \
    $(if $(DEVICE),--set llm-service.device='$(DEVICE)',) \
    $(if $(LLM),--set global.models.$(LLM).enabled=true,) \
    $(if $(SAFETY),--set global.models.$(SAFETY).enabled=true,) \
    $(if $(LLM_TOLERATION),--set-json global.models.$(LLM).tolerations='$(call TOLERATIONS_TEMPLATE,$(LLM_TOLERATION))',) \
    $(if $(SAFETY_TOLERATION),--set-json global.models.$(SAFETY).tolerations='$(call TOLERATIONS_TEMPLATE,$(SAFETY_TOLERATION))',) \
    $(if $(RAW_DEPLOYMENT),--set llm-service.rawDeploymentMode=$(RAW_DEPLOYMENT),)

helm_llama_stack_args = \
    $(if $(LLM),--set global.models.$(LLM).enabled=true,) \
    $(if $(SAFETY),--set global.models.$(SAFETY).enabled=true,) \
    $(if $(LLM_URL),--set global.models.$(LLM).url='$(LLM_URL)',) \
    $(if $(SAFETY_URL),--set global.models.$(SAFETY).url='$(SAFETY_URL)',) \
    $(if $(LLM_API_TOKEN),--set global.models.$(LLM).apiToken='$(LLM_API_TOKEN)',) \
    $(if $(SAFETY_API_TOKEN),--set global.models.$(SAFETY).apiToken='$(SAFETY_API_TOKEN)',) \
    $(if $(LLAMA_STACK_ENV),--set-json llama-stack.secrets='$(LLAMA_STACK_ENV)',) \
    $(if $(RAW_DEPLOYMENT),--set llama-stack.rawDeploymentMode=$(RAW_DEPLOYMENT),)


# Default target
.PHONY: help
help: ## Show this help message
	@echo -e "$(BLUE)RAG Stack Helm Deployment$(NC)"
	@echo -e ""
	@echo -e "$(GREEN)Usage:$(NC) make [TARGET]"
	@echo -e ""
	@echo -e "$(GREEN)Main Targets:$(NC)"
	@echo -e "  install       - Install RAG chart, then F5 AI Security chart (see SKIP_F5_GUARDRAILS)"
	@echo -e "  uninstall     - Uninstall RAG + F5 AI Guardrails operator/namespaces"
	@echo -e "  install-f5-ai-security - Install only the f5-ai-security Helm chart"
	@echo -e "  print-moderator-host - Print routes hostname + baseUrl for current MODERATOR_HOST_PREFIX (needs oc)"
	@echo -e "  status        - Check deployment status"
	@echo -e "  logs          - Show application logs"
	@echo -e "  health        - Check health of all services"
	@echo -e ""
	@echo -e "$(GREEN)Development Targets:$(NC)"
	@echo -e "  validate      - Validate RAG and f5-ai-security Helm charts"
	@echo -e "  validate-infra - Preflight: oc login, ingress, KServe CRDs + webhook endpoints, optional GPU"
	@echo -e "  validate-config - Validate configuration values"
	@echo -e "  monitor       - Monitor deployment status"
	@echo -e "  config        - Show current configuration"
	@echo -e "  deploy-ui-local  - Start Streamlit UI in background (alias: ui-local)"
	@echo -e "  undeploy-ui-local - Stop background UI (pid file in repo root)"
	@echo -e "  deploy-ui-local-foreground - Run UI in foreground (blocks terminal; same as direct script)"
	@echo -e "                    Optional: NAMESPACE=... PORT_FORWARD=1 (see frontend/dev-on-cluster.sh)"
	@echo -e ""
	@echo -e "$(GREEN)F5 XC Targets:$(NC)"
	@echo -e "  f5-deploy     - Deploy F5 XC Customer Edge mesh (Ansible)"
	@echo -e "  f5-clean      - Remove F5 XC deployment and cluster resources"
	@echo -e ""
	@echo -e "$(GREEN)Management Targets:$(NC)"
	@echo -e "  clean         - Clean up all resources including namespace"
	@echo -e "  init-config   - Initialize configuration from example"
	@echo -e "  configure-keys - Interactively configure API keys"
	@echo -e "  edit-config   - Edit configuration file"
	@echo -e "  show-config   - Show current configuration"
	@echo -e ""
	@echo -e "$(GREEN)Configuration:$(NC)"
	@echo -e "  NAMESPACE     - RAG / LlamaStack namespace (required for install/uninstall/...)"
	@echo -e "  VALUES_FILE   - Configuration file (default: rag-values.yaml)"
	@echo -e "  F5_AI_SECURITY_VALUES - F5 chart values (default: f5-ai-security-values.yaml)"
	@echo -e "  F5_AI_SECURITY_NAMESPACE - Operator / Helm release namespace (default: f5-ai-sec)"
	@echo -e "  F5_MODERATOR_NS / F5_PREFECT_NS / F5_INFERENCE_NS - Product namespaces (defaults match docs)"
	@echo -e "  MODERATOR_HOST_AUTO - If false, do not set routes/baseUrl from cluster (default: true)"
	@echo -e "  MODERATOR_HOST_PREFIX - First DNS label for Moderator host (default: aisec); empty disables auto URL"
	@echo -e "  SKIP_F5_GUARDRAILS - If set (non-empty), install skips the F5 chart"
	@echo -e "  SKIP_F5_OPERATOR_WAIT - If 1, skip oc wait for operator CSV after F5 chart"
	@echo -e "  F5_HELM_FLAGS - Extra flags for F5 helm (default: --take-ownership; set empty to disable)"
	@echo -e "  F5_HELM_MAX_ATTEMPTS / F5_HELM_RETRY_SLEEP - F5 helm first-pass retry tuning (defaults: 8 / 6)"
	@echo -e "  SKIP_INFRA_CHECK - If 1, skip validate-infra before install / install-f5-ai-security"
	@echo -e "  REQUIRE_GPU - If 1, validate-infra fails when no nvidia.com/gpu allocatable (default: warn only)"
	@echo -e "  KSERVE_WEBHOOK_NAMESPACE / KSERVE_WEBHOOK_SERVICE - webhook Service for validate-infra wait"
	@echo -e "  KSERVE_WEBHOOK_WAIT_SECONDS - wait for webhook endpoints (default 300; 0 = one check only)"
	@echo -e "  EXTRA_HELM_F5_ARGS - Extra arguments passed to helm for the F5 chart"
	@echo -e ""
	@echo -e "  Optional env (same pattern as HF_TOKEN for RAG): if set, passed as --set-string to F5 chart"
	@echo -e "    DOCKER_USERNAME DOCKER_PASSWORD DOCKER_EMAIL F5_LICENSE MODERATOR_BASE_URL ROUTES_HOSTNAME"
	@echo -e ""
	@echo -e "$(GREEN)Command-Line Parameters (override values file):$(NC)"
	@echo -e "  LLM           - Enable specific LLM model (e.g., llama-3-2-3b-instruct)"
	@echo -e "  SAFETY        - Enable specific safety model (e.g., llama-guard-3-8b)"
	@echo -e "  LLM_TOLERATION - Set toleration for LLM model (e.g., nvidia.com/gpu)"
	@echo -e "  SAFETY_TOLERATION - Set toleration for safety model"
	@echo -e "  DEVICE        - Set device type: cpu, gpu, or hpu (default: gpu)"
	@echo -e "  HF_TOKEN      - Hugging Face token for model downloads"
	@echo -e "  LLM_URL       - URL for remote LLM service"
	@echo -e "  SAFETY_URL    - URL for remote safety service"
	@echo -e "  LLM_API_TOKEN - API token for remote LLM service"
	@echo -e "  SAFETY_API_TOKEN - API token for remote safety service"
	@echo -e ""
	@echo -e "$(GREEN)Quick Start:$(NC)"
	@echo -e "  $(BLUE)Option 1:$(NC) Using values file (recommended)"
	@echo -e "    1. make init-config  # Create configuration from example"
	@echo -e "    2. make configure-keys  # Set up API keys interactively"
	@echo -e "    3. make validate-infra  # Optional: confirm OpenShift AI + cluster (recommended on fresh clusters)"
	@echo -e "    4. make install NAMESPACE=my-rag  # Install with your config"
	@echo -e ""
	@echo -e "  $(BLUE)Option 2:$(NC) Using command-line parameters"
	@echo -e "    make install NAMESPACE=my-rag LLM=llama-3-2-3b-instruct LLM_TOLERATION=\"nvidia.com/gpu\""

# Dependency checks
.PHONY: check-deps
check-deps: ## Check required dependencies
	@command -v helm >/dev/null 2>&1 || { echo -e "$(RED)[ERROR]$(NC) helm is not installed"; exit 1; }
	@command -v oc >/dev/null 2>&1 || { echo -e "$(RED)[ERROR]$(NC) oc is not installed"; exit 1; }
	@echo -e "$(GREEN)[SUCCESS]$(NC) All dependencies are installed."

# Namespace validation
.PHONY: check-namespace
check-namespace: ## Check if namespace exists and is accessible
	@oc get namespace $(NAMESPACE) >/dev/null 2>&1 || { echo -e "$(RED)[ERROR]$(NC) Namespace $(NAMESPACE) does not exist or is not accessible"; exit 1; }

# Cluster preflight (OpenShift AI / KServe, routes, optional GPU)
.PHONY: validate-infra
validate-infra: check-deps ## Preflight cluster for RAG + F5 (run before install on fresh clusters)
	@echo -e "$(BLUE)[INFO]$(NC) Validating cluster infrastructure..."
	@oc whoami >/dev/null 2>&1 || { echo -e "$(RED)[ERROR]$(NC) Not logged in. Run: oc login ..."; exit 1; }; \
	echo -e "$(GREEN)[OK]$(NC) OpenShift auth: $$(oc whoami)"; \
	DOMAIN=$$(oc get ingress.config cluster -o jsonpath='{.spec.domain}' 2>/dev/null || true); \
	if [ -z "$$DOMAIN" ]; then \
		echo -e "$(RED)[ERROR]$(NC) ingress.config/cluster has no .spec.domain (cluster API unreachable?)"; \
		exit 1; \
	fi; \
	echo -e "$(GREEN)[OK]$(NC) Ingress domain: $$DOMAIN"; \
	for crd in inferenceservices.serving.kserve.io servingruntimes.serving.kserve.io; do \
		if ! oc get crd "$$crd" >/dev/null 2>&1; then \
			echo -e "$(RED)[ERROR]$(NC) Missing CRD $$crd (install OpenShift AI / model serving / KServe first)."; \
			exit 1; \
		fi; \
	done; \
	echo -e "$(GREEN)[OK]$(NC) KServe CRDs present (InferenceService, ServingRuntime)"; \
	KWNNS="$(KSERVE_WEBHOOK_NAMESPACE)"; KWSVC="$(KSERVE_WEBHOOK_SERVICE)"; KWMAX=$(KSERVE_WEBHOOK_WAIT_SECONDS); KWSTEP=10; KWELAPSED=0; \
	echo -e "$(BLUE)[INFO]$(NC) Waiting for KServe webhook endpoints ($$KWNNS/$$KWSVC, up to $$KWMAX s)..."; \
	while true; do \
		EP=$$(oc get endpoints "$$KWSVC" -n "$$KWNNS" -o jsonpath='{.subsets[*].addresses[*].ip}' 2>/dev/null || true); \
		if [ -n "$$EP" ]; then \
			echo -e "$(GREEN)[OK]$(NC) KServe webhook service has endpoints"; \
			break; \
		fi; \
		if [ "$$KWELAPSED" -ge "$$KWMAX" ]; then \
			echo -e "$(RED)[ERROR]$(NC) No endpoints for $$KWNNS/$$KWSVC after $$KWMAX s (webhooks will reject InferenceService/ServingRuntime)."; \
			echo -e "$(BLUE)[INFO]$(NC) Wait for OpenShift AI / KServe pods, then retry. Check: oc get pods -n $$KWNNS | grep -i kserve"; \
			exit 1; \
		fi; \
		if ! oc get svc "$$KWSVC" -n "$$KWNNS" >/dev/null 2>&1; then \
			echo -e "$(YELLOW)[WARN]$(NC) Service $$KWSVC not in $$KWNNS yet ($$KWELAPSED/$$KWMAX s)..."; \
		else \
			echo -e "$(YELLOW)[WARN]$(NC) Service exists but no endpoints yet ($$KWELAPSED/$$KWMAX s)..."; \
		fi; \
		sleep $$KWSTEP; \
		KWELAPSED=$$((KWELAPSED + KWSTEP)); \
	done; \
	if ! helm upgrade --help 2>/dev/null | grep -q -- '--take-ownership'; then \
		echo -e "$(RED)[ERROR]$(NC) Helm does not support --take-ownership (need Helm 3.13+). Upgrade Helm for reliable F5 install."; \
		exit 1; \
	fi; \
	echo -e "$(GREEN)[OK]$(NC) Helm supports --take-ownership"; \
	GPU_LINES=$$(oc get nodes -o jsonpath='{range .items[*]}{.status.allocatable.nvidia\.com/gpu}{"\n"}{end}' 2>/dev/null | grep -E '^[1-9]' || true); \
	if [ -z "$$GPU_LINES" ]; then \
		if [ "$(REQUIRE_GPU)" = "1" ]; then \
			echo -e "$(RED)[ERROR]$(NC) No node with allocatable nvidia.com/gpu (install NVIDIA GPU Operator and GPU workers, or set DEVICE=cpu in values)."; \
			exit 1; \
		else \
			echo -e "$(YELLOW)[WARN]$(NC) No allocatable nvidia.com/gpu yet — GPU model pods may stay Pending until the GPU Operator exposes GPUs."; \
		fi; \
	else \
		echo -e "$(GREEN)[OK]$(NC) At least one node advertises nvidia.com/gpu"; \
	fi; \
	if [ -z "$(SKIP_F5_GUARDRAILS)" ] && [ ! -f "$(F5_AI_SECURITY_VALUES)" ]; then \
		echo -e "$(RED)[ERROR]$(NC) Missing $(F5_AI_SECURITY_VALUES). Run: make init-f5-config"; \
		exit 1; \
	fi; \
	if [ -n "$(SKIP_F5_GUARDRAILS)" ]; then \
		echo -e "$(BLUE)[INFO]$(NC) SKIP_F5_GUARDRAILS set; skipping F5 values file check."; \
	else \
		echo -e "$(GREEN)[OK]$(NC) F5 values file: $(F5_AI_SECURITY_VALUES)"; \
	fi; \
	echo -e "$(GREEN)[SUCCESS]$(NC) Infrastructure checks passed."

# Configuration management
.PHONY: config
config: ## Show current configuration
	@echo -e "$(BLUE)[INFO]$(NC) Current configuration:"
	@echo -e "  Namespace: $(NAMESPACE)"
	@echo -e "  Values file: $(VALUES_FILE)"
	@if [ -f "$(VALUES_FILE)" ]; then \
		echo -e "  Configuration: Found"; \
		echo -e "$(BLUE)[INFO]$(NC) Key settings from $(VALUES_FILE):"; \
		grep -E "^(hf_token):" "$(VALUES_FILE)" 2>/dev/null || echo -e "  No API keys found"; \
		echo -e "$(BLUE)[INFO]$(NC) Model configuration:"; \
		grep -A 5 "global:" "$(VALUES_FILE)" 2>/dev/null | grep -E "(models|enabled)" || echo -e "  No models configured"; \
	else \
		echo -e "  Configuration: Not found"; \
		echo -e "$(YELLOW)[WARNING]$(NC) Run 'make init-config' to create configuration file"; \
	fi

.PHONY: init-config
init-config: ## Initialize configuration from example
	@if [ -f "$(VALUES_FILE)" ]; then \
		echo -e "$(YELLOW)[WARNING]$(NC) $(VALUES_FILE) already exists."; \
		echo -e "$(BLUE)[INFO]$(NC) Use 'make edit-config' to modify it, or remove it first."; \
	else \
		if [ -f "$(VALUES_EXAMPLE)" ]; then \
			cp "$(VALUES_EXAMPLE)" "$(VALUES_FILE)"; \
			echo -e "$(GREEN)[SUCCESS]$(NC) Created $(VALUES_FILE) from $(VALUES_EXAMPLE)"; \
			echo -e "$(BLUE)[INFO]$(NC) Please edit $(VALUES_FILE) with your configuration:"; \
			echo -e "  - llm-service.secret.hf_token: Your Hugging Face token"; \
			echo -e "  - global.models: Configure your LLM and safety models"; \
			echo -e ""; \
			echo -e "$(BLUE)[INFO]$(NC) You can edit it with: make edit-config"; \
		else \
			echo -e "$(RED)[ERROR]$(NC) $(VALUES_EXAMPLE) not found."; \
			exit 1; \
		fi; \
	fi

.PHONY: edit-config
edit-config: ## Edit configuration file
	@if [ -f "$(VALUES_FILE)" ]; then \
		echo -e "$(BLUE)[INFO]$(NC) Opening $(VALUES_FILE) for editing..."; \
		$${EDITOR:-nano} "$(VALUES_FILE)"; \
	else \
		echo -e "$(YELLOW)[WARNING]$(NC) $(VALUES_FILE) not found. Creating from example..."; \
		$(MAKE) init-config; \
		$${EDITOR:-nano} "$(VALUES_FILE)"; \
	fi

.PHONY: show-config
show-config: ## Show configuration file contents
	@if [ -f "$(VALUES_FILE)" ]; then \
		echo -e "$(BLUE)[INFO]$(NC) Contents of $(VALUES_FILE):"; \
		echo -e ""; \
		cat "$(VALUES_FILE)"; \
	else \
		echo -e "$(YELLOW)[WARNING]$(NC) $(VALUES_FILE) not found."; \
		echo -e "$(BLUE)[INFO]$(NC) Run 'make init-config' to create it."; \
	fi

# Configuration validation (moved to validation section)


# Create namespace and deploy
namespace:
	@echo -e "$(BLUE)[INFO]$(NC) Creating namespace $(NAMESPACE)..."
	@oc create namespace $(NAMESPACE) &> /dev/null && oc label namespace $(NAMESPACE) modelmesh-enabled=false ||:
	@oc project $(NAMESPACE) &> /dev/null ||:
	@echo -e "$(GREEN)[SUCCESS]$(NC) Namespace $(NAMESPACE) is ready"

# Validation targets
.PHONY: validate
validate: check-deps ## Validate Helm chart before installation
	@echo -e "$(BLUE)[INFO]$(NC) Validating Helm charts..."
	@helm lint $(RAG_CHART)
	@helm template $(RAG_CHART) --dry-run >/dev/null
	@helm lint $(F5_AI_SECURITY_CHART)
	@helm template $(F5_AI_SECURITY_RELEASE) $(F5_AI_SECURITY_CHART) >/dev/null
	@helm template $(F5_AI_SECURITY_RELEASE) $(F5_AI_SECURITY_CHART) --set securityOperator.waitForCrd=false \
		--set-string securityOperator.moderator.baseUrl=https://helm-lint.local \
		--set-string securityOperator.moderator.license=helm-lint >/dev/null
	@echo -e "$(GREEN)[SUCCESS]$(NC) Helm chart validation passed"

.PHONY: validate-config
validate-config: ## Validate configuration values
	@if [ ! -f "$(VALUES_FILE)" ]; then \
		echo -e "$(RED)[ERROR]$(NC) Configuration file $(VALUES_FILE) not found."; \
		echo -e "$(BLUE)[INFO]$(NC) Run 'make init-config' to create it from example."; \
		exit 1; \
	fi
	@$(call validate_values_file)

.PHONY: configure-keys
configure-keys: ## Interactively configure API keys
	@if [ ! -f "$(VALUES_FILE)" ]; then \
		echo -e "$(RED)[ERROR]$(NC) Configuration file $(VALUES_FILE) not found."; \
		echo -e "$(BLUE)[INFO]$(NC) Run 'make init-config' to create it from example."; \
		exit 1; \
	fi
	@echo -e "$(BLUE)[INFO]$(NC) Interactive API key configuration..."; \
	echo -e ""; \
	read -p "Enter your Hugging Face token (or press Enter to skip): " hf_input; \
	if [ -n "$$hf_input" ]; then \
		sed -i.bak "/^llm-service:/,/^[^ ]/ s|hf_token:.*|hf_token: \"$$hf_input\"|" "$(VALUES_FILE)"; \
		echo -e "$(GREEN)[SUCCESS]$(NC) Hugging Face token saved to configuration."; \
	else \
		echo -e "$(YELLOW)[WARNING]$(NC) Hugging Face token not provided."; \
	fi; \
	echo -e ""; \
	echo -e "$(GREEN)[SUCCESS]$(NC) Configuration updated."; \
	rm -f "$(VALUES_FILE).bak" 2>/dev/null || true

# Monitoring targets
.PHONY: monitor
monitor: ## Monitor deployment status
	@if [ -z "$(NAMESPACE)" ]; then echo -e "$(RED)[ERROR]$(NC) NAMESPACE is required for monitor"; exit 1; fi
	@echo -e "$(BLUE)[INFO]$(NC) Monitoring deployment status (press Ctrl+C to stop)..."
	@watch -n 5 "oc get pods -n $(NAMESPACE)"

# Logging targets
.PHONY: logs
logs: ## Show logs for all pods
	@if [ -z "$(NAMESPACE)" ]; then echo -e "$(RED)[ERROR]$(NC) NAMESPACE is required for logs"; exit 1; fi
	@echo -e "$(BLUE)[INFO]$(NC) Showing logs for all pods..."
	@oc logs -n $(NAMESPACE) -l app=llamastack --tail=100

.PHONY: logs-llm
logs-llm: ## Show logs for LLM service
	@if [ -z "$(NAMESPACE)" ]; then echo -e "$(RED)[ERROR]$(NC) NAMESPACE is required for logs-llm"; exit 1; fi
	@echo -e "$(BLUE)[INFO]$(NC) Showing logs for LLM service..."
	@oc logs -n $(NAMESPACE) -l app=llm-service --tail=100

# Health check targets
.PHONY: health
health: ## Check health of all services
	@if [ -z "$(NAMESPACE)" ]; then echo -e "$(RED)[ERROR]$(NC) NAMESPACE is required for health"; exit 1; fi
	@echo -e "$(BLUE)[INFO]$(NC) Checking service health..."
	@oc get pods -n $(NAMESPACE) -o wide
	@echo -e ""
	@echo -e "$(BLUE)[INFO]$(NC) Checking service endpoints..."
	@oc get svc -n $(NAMESPACE)
	@echo -e ""
	@echo -e "$(BLUE)[INFO]$(NC) Checking routes..."
	@oc get routes -n $(NAMESPACE)

# Cleanup targets
.PHONY: clean
clean: ## Clean up all resources including namespace
	@if [ -z "$(NAMESPACE)" ]; then echo -e "$(RED)[ERROR]$(NC) NAMESPACE is required for clean"; exit 1; fi
	@echo -e "$(BLUE)[INFO]$(NC) Cleaning up all resources..."
	@$(MAKE) uninstall
	@oc delete project $(NAMESPACE) || true
	@echo -e "$(GREEN)[SUCCESS]$(NC) Cleanup completed"

# Configuration file management
.PHONY: clean-config
clean-config: ## Remove configuration file
	@if [ -f "$(VALUES_FILE)" ]; then \
		rm "$(VALUES_FILE)"; \
		echo -e "$(GREEN)[SUCCESS]$(NC) Configuration file $(VALUES_FILE) removed."; \
	else \
		echo -e "$(BLUE)[INFO]$(NC) No configuration file found."; \
	fi

.PHONY: depend
depend: ## Update Helm dependencies
	@echo -e "$(BLUE)[INFO]$(NC) Updating Helm dependencies..."
	@helm dependency update $(RAG_CHART) &> /dev/null
	@echo -e "$(GREEN)[SUCCESS]$(NC) Helm dependencies updated"

.PHONY: list-models
list-models: depend ## List available models
	@echo -e "$(BLUE)[INFO]$(NC) Listing available models..."
	@helm template dummy-release $(RAG_CHART) --set llm-service._debugListModels=true | grep ^model:

.PHONY: install
install: ## Install the RAG deployment
	@if [ -z "$(NAMESPACE)" ]; then echo -e "$(RED)[ERROR]$(NC) NAMESPACE is required for install"; exit 1; fi
	@if [ "$(SKIP_INFRA_CHECK)" != "1" ]; then $(MAKE) validate-infra; else $(MAKE) check-deps; fi
	@$(MAKE) namespace
	@$(MAKE) depend
	@$(MAKE) delete-jobs
	@$(call check_values_file)
	@echo -e "$(BLUE)[INFO]$(NC) Installing $(RAG_CHART) helm chart with $(VALUES_FILE)..."
	@HELM_ARGS="-f $(VALUES_FILE)"; \
	if [ -n "$(LLM)" ]; then \
		echo -e "$(BLUE)[INFO]$(NC) Enabling LLM model: $(LLM)"; \
		HELM_ARGS="$$HELM_ARGS --set global.models.$(LLM).enabled=true"; \
		if [ -n "$(LLM_TOLERATION)" ]; then \
			echo -e "$(BLUE)[INFO]$(NC) Setting LLM toleration: $(LLM_TOLERATION)"; \
			HELM_ARGS="$$HELM_ARGS --set global.models.$(LLM).tolerations[0].key=$(LLM_TOLERATION)"; \
			HELM_ARGS="$$HELM_ARGS --set global.models.$(LLM).tolerations[0].effect=NoSchedule"; \
			HELM_ARGS="$$HELM_ARGS --set global.models.$(LLM).tolerations[0].operator=Exists"; \
		fi; \
		if [ -n "$(LLM_URL)" ]; then \
			echo -e "$(BLUE)[INFO]$(NC) Setting LLM URL: $(LLM_URL)"; \
			HELM_ARGS="$$HELM_ARGS --set global.models.$(LLM).url='$(LLM_URL)'"; \
		fi; \
		if [ -n "$(LLM_API_TOKEN)" ]; then \
			echo -e "$(BLUE)[INFO]$(NC) Setting LLM API token"; \
			HELM_ARGS="$$HELM_ARGS --set global.models.$(LLM).apiToken='$(LLM_API_TOKEN)'"; \
		fi; \
	fi; \
	if [ -n "$(SAFETY)" ]; then \
		echo -e "$(BLUE)[INFO]$(NC) Enabling SAFETY model: $(SAFETY)"; \
		HELM_ARGS="$$HELM_ARGS --set global.models.$(SAFETY).enabled=true"; \
		if [ -n "$(SAFETY_TOLERATION)" ]; then \
			echo -e "$(BLUE)[INFO]$(NC) Setting SAFETY toleration: $(SAFETY_TOLERATION)"; \
			HELM_ARGS="$$HELM_ARGS --set global.models.$(SAFETY).tolerations[0].key=$(SAFETY_TOLERATION)"; \
			HELM_ARGS="$$HELM_ARGS --set global.models.$(SAFETY).tolerations[0].effect=NoSchedule"; \
			HELM_ARGS="$$HELM_ARGS --set global.models.$(SAFETY).tolerations[0].operator=Exists"; \
		fi; \
		if [ -n "$(SAFETY_URL)" ]; then \
			echo -e "$(BLUE)[INFO]$(NC) Setting SAFETY URL: $(SAFETY_URL)"; \
			HELM_ARGS="$$HELM_ARGS --set global.models.$(SAFETY).url='$(SAFETY_URL)'"; \
		fi; \
		if [ -n "$(SAFETY_API_TOKEN)" ]; then \
			echo -e "$(BLUE)[INFO]$(NC) Setting SAFETY API token"; \
			HELM_ARGS="$$HELM_ARGS --set global.models.$(SAFETY).apiToken='$(SAFETY_API_TOKEN)'"; \
		fi; \
	fi; \
	if [ -n "$(DEVICE)" ]; then \
		echo -e "$(BLUE)[INFO]$(NC) Setting device: $(DEVICE)"; \
		HELM_ARGS="$$HELM_ARGS --set llm-service.device='$(DEVICE)'"; \
	fi; \
	if [ -n "$(HF_TOKEN)" ]; then \
		echo -e "$(BLUE)[INFO]$(NC) Setting HF_TOKEN from command line"; \
		HELM_ARGS="$$HELM_ARGS --set llm-service.secret.hf_token=$(HF_TOKEN)"; \
	fi; \
	if [ -n "$(RAW_DEPLOYMENT)" ]; then \
		echo -e "$(BLUE)[INFO]$(NC) Setting raw deployment mode: $(RAW_DEPLOYMENT)"; \
		HELM_ARGS="$$HELM_ARGS --set llm-service.rawDeploymentMode=$(RAW_DEPLOYMENT)"; \
		HELM_ARGS="$$HELM_ARGS --set llama-stack.rawDeploymentMode=$(RAW_DEPLOYMENT)"; \
	fi; \
	if [ -n "$(LLAMA_STACK_ENV)" ]; then \
		echo -e "$(BLUE)[INFO]$(NC) Setting Llama Stack environment variables"; \
		HELM_ARGS="$$HELM_ARGS --set-json llama-stack.secrets='$(LLAMA_STACK_ENV)'"; \
	fi; \
	HELM_ARGS="$$HELM_ARGS $(EXTRA_HELM_ARGS)"; \
	helm -n $(NAMESPACE) upgrade --install $(RAG_CHART) $(RAG_CHART) -n $(NAMESPACE) $$HELM_ARGS
	@echo -e "$(BLUE)[INFO]$(NC) Waiting for model services and llamastack to deploy. It may take around 10-15 minutes depending on the size of the model..."
	@oc rollout status deploy/llamastack -n $(NAMESPACE) --timeout=900s
	@echo -e "$(GREEN)[SUCCESS]$(NC) $(RAG_CHART) installed successfully"
	@if [ -n "$(SKIP_F5_GUARDRAILS)" ]; then \
		echo -e "$(YELLOW)[INFO]$(NC) SKIP_F5_GUARDRAILS is set; skipping F5 AI Security chart."; \
	else \
		$(MAKE) install-f5-ai-security; \
	fi

.PHONY: init-f5-config
init-f5-config: ## Create f5-ai-security-values.yaml from example if missing
	@if [ -f "$(F5_AI_SECURITY_VALUES)" ]; then \
		echo -e "$(YELLOW)[INFO]$(NC) $(F5_AI_SECURITY_VALUES) already exists."; \
	else \
		cp "$(F5_AI_SECURITY_VALUES_EXAMPLE)" "$(F5_AI_SECURITY_VALUES)"; \
		echo -e "$(GREEN)[SUCCESS]$(NC) Created $(F5_AI_SECURITY_VALUES) from $(F5_AI_SECURITY_VALUES_EXAMPLE)"; \
		echo -e "$(BLUE)[INFO]$(NC) Edit registry credentials, license; set routes + baseUrl or use MODERATOR_HOST_PREFIX= (see README)."; \
	fi

.PHONY: print-moderator-host
print-moderator-host: check-deps ## Print routes.hostname and moderator.baseUrl (default prefix aisec; requires oc)
	@PREFIX="$(MODERATOR_HOST_PREFIX)"; \
	if [ -z "$$PREFIX" ]; then PREFIX=aisec; fi; \
	DOMAIN=$$(oc get ingress.config cluster -o jsonpath='{.spec.domain}' 2>/dev/null || true); \
	if [ -z "$$DOMAIN" ]; then \
		echo -e "$(RED)[ERROR]$(NC) Could not read ingress.config/cluster .spec.domain (oc login?)"; \
		exit 1; \
	fi; \
	HOST="$$PREFIX.$$DOMAIN"; \
	echo -e "$(GREEN)routes.hostname:$(NC) $$HOST"; \
	echo -e "$(GREEN)securityOperator.moderator.baseUrl:$(NC) https://$$HOST"

.PHONY: install-f5-ai-security
install-f5-ai-security: ## Install F5 AI Security / Guardrails Helm chart only
	@if [ "$(SKIP_INFRA_CHECK)" != "1" ]; then $(MAKE) validate-infra; else $(MAKE) check-deps; fi
	@set -e; \
	if [ ! -f "$(F5_AI_SECURITY_VALUES)" ]; then \
		echo -e "$(RED)[ERROR]$(NC) Missing $(F5_AI_SECURITY_VALUES)."; \
		echo -e "$(BLUE)[INFO]$(NC) Run: $(BLUE)make init-f5-config$(NC) then edit $(F5_AI_SECURITY_VALUES)"; \
		exit 1; \
	fi; \
	echo -e "$(BLUE)[INFO]$(NC) Installing $(F5_AI_SECURITY_CHART) (operator ns: $(F5_AI_SECURITY_NAMESPACE), moderator: $(F5_MODERATOR_NS))..."; \
	F5_NS_SET="--set-string productNamespaces.operator=$(F5_AI_SECURITY_NAMESPACE) \
		--set-string productNamespaces.moderator=$(F5_MODERATOR_NS) \
		--set-string productNamespaces.prefect=$(F5_PREFECT_NS) \
		--set-string productNamespaces.inference=$(F5_INFERENCE_NS)"; \
	AUTO_HOST=""; \
	MA="$(MODERATOR_HOST_AUTO)"; \
	if [ -z "$$MA" ]; then MA=true; fi; \
	if [ "$$MA" != "false" ]; then \
		PREFIX="$(MODERATOR_HOST_PREFIX)"; \
		if [ -z "$$PREFIX" ]; then PREFIX=aisec; fi; \
		DOMAIN=$$(oc get ingress.config cluster -o jsonpath='{.spec.domain}' 2>/dev/null || true); \
		if [ -z "$$DOMAIN" ]; then \
			echo -e "$(RED)[ERROR]$(NC) MODERATOR_HOST_AUTO is true but ingress.config/cluster .spec.domain is empty or unreadable."; \
			exit 1; \
		fi; \
		HOST="$$PREFIX.$$DOMAIN"; \
		echo -e "$(BLUE)[INFO]$(NC) Moderator URL (prefix=$$PREFIX): routes.hostname=$$HOST securityOperator.moderator.baseUrl=https://$$HOST"; \
		AUTO_HOST="--set-string routes.hostname=$$HOST --set-string securityOperator.moderator.baseUrl=https://$$HOST"; \
	fi; \
	ENV_SET=""; \
	if [ -n "$${DOCKER_USERNAME:-}" ]; then ENV_SET="$$ENV_SET --set-string registry.username=$${DOCKER_USERNAME}"; fi; \
	if [ -n "$${DOCKER_PASSWORD:-}" ]; then ENV_SET="$$ENV_SET --set-string registry.password=$${DOCKER_PASSWORD}"; fi; \
	if [ -n "$${DOCKER_EMAIL:-}" ]; then ENV_SET="$$ENV_SET --set-string registry.email=$${DOCKER_EMAIL}"; fi; \
	if [ -n "$${F5_LICENSE:-}" ]; then ENV_SET="$$ENV_SET --set-string securityOperator.moderator.license=$${F5_LICENSE}"; fi; \
	if [ -n "$${MODERATOR_BASE_URL:-}" ]; then ENV_SET="$$ENV_SET --set-string securityOperator.moderator.baseUrl=$${MODERATOR_BASE_URL}"; fi; \
	if [ -n "$${ROUTES_HOSTNAME:-}" ]; then ENV_SET="$$ENV_SET --set-string routes.hostname=$${ROUTES_HOSTNAME}"; fi; \
	HELM_EXTRAS="$$F5_NS_SET $$AUTO_HOST $$ENV_SET --set namespaces.manageOperatorNamespace=false $(EXTRA_HELM_F5_ARGS)"; \
	echo -e "$(BLUE)[INFO]$(NC) Installing $(F5_AI_SECURITY_CHART) (Helm --create-namespace; retries if API race)..."; \
	ATTEMPT=1; \
	while [ $$ATTEMPT -le $(F5_HELM_MAX_ATTEMPTS) ]; do \
		if helm upgrade --install $(F5_AI_SECURITY_RELEASE) $(F5_AI_SECURITY_CHART) \
			-n $(F5_AI_SECURITY_NAMESPACE) --create-namespace \
			$(F5_HELM_FLAGS) \
			-f "$(F5_AI_SECURITY_VALUES)" $$HELM_EXTRAS; then \
			break; \
		fi; \
		if [ $$ATTEMPT -eq $(F5_HELM_MAX_ATTEMPTS) ]; then \
			echo -e "$(RED)[ERROR]$(NC) Helm install failed after $(F5_HELM_MAX_ATTEMPTS) attempts."; \
			exit 1; \
		fi; \
		echo -e "$(YELLOW)[INFO]$(NC) Helm retry $$ATTEMPT/$(F5_HELM_MAX_ATTEMPTS) (e.g. namespace or API race)..."; \
		ATTEMPT=$$((ATTEMPT + 1)); \
		sleep $(F5_HELM_RETRY_SLEEP); \
	done; \
	if [ "$(SKIP_F5_OPERATOR_WAIT)" = "1" ]; then \
		echo -e "$(YELLOW)[INFO]$(NC) SKIP_F5_OPERATOR_WAIT=1; not waiting for CSV."; \
	else \
		echo -e "$(BLUE)[INFO]$(NC) Waiting for operator CSV $(OPERATOR_CSV) (best-effort, 600s)..."; \
		oc wait "csv/$(OPERATOR_CSV)" -n "$(F5_AI_SECURITY_NAMESPACE)" --for=jsonpath='{.status.phase}'=Succeeded --timeout=600s 2>/dev/null \
			|| echo -e "$(YELLOW)[INFO]$(NC) CSV not Succeeded yet (first install or subscription disabled). Check: oc get csv -n $(F5_AI_SECURITY_NAMESPACE)"; \
	fi; \
	echo -e "$(BLUE)[INFO]$(NC) Waiting for SecurityOperator CRD (up to 120s)..."; \
	W=0; \
	while [ $$W -lt 60 ]; do \
		if oc get crd securityoperators.ai.security.f5.com >/dev/null 2>&1; then \
			echo -e "$(GREEN)[OK]$(NC) CRD securityoperators.ai.security.f5.com is present"; \
			break; \
		fi; \
		W=$$((W+1)); \
		sleep 2; \
	done; \
	if ! oc get crd securityoperators.ai.security.f5.com >/dev/null 2>&1; then \
		echo -e "$(YELLOW)[WARN]$(NC) CRD not visible after 120s; continuing (Helm uses CRD lookup for SecurityOperator manifest)"; \
	fi; \
	if [ "$(SKIP_F5_INFERENCE_SCC)" != "1" ] && oc get scc restricted-v2 >/dev/null 2>&1; then \
		INFER_SCC="$(CURDIR)/$(F5_AI_SECURITY_CHART)/extras/openshift-inference-models-scc.yaml"; \
		if [ -f "$$INFER_SCC" ]; then \
			echo -e "$(BLUE)[INFO]$(NC) Applying Inference OpenShift SCC (cluster-admin oc apply; operator cannot create SCCs)..."; \
			sed -e "s|__F5_INFERENCE_NAMESPACE__|$(F5_INFERENCE_NS)|g" \
				-e "s|__F5_INFERENCE_HELM_RELEASE_NAME__|$(F5_INFERENCE_HELM_RELEASE)|g" \
				-e "s|__F5_INFERENCE_HELM_RELEASE_NAMESPACE__|$(F5_INFERENCE_NS)|g" \
				"$$INFER_SCC" | oc apply -f -; \
		else \
			echo -e "$(YELLOW)[WARN]$(NC) Missing $$INFER_SCC; skip inference SCC pre-apply."; \
		fi; \
	fi; \
	echo -e "$(BLUE)[INFO]$(NC) Re-applying chart so SecurityOperator is created once the CRD is registered..."; \
	R2=1; \
	while [ $$R2 -le 5 ]; do \
		if helm upgrade --install $(F5_AI_SECURITY_RELEASE) $(F5_AI_SECURITY_CHART) \
			-n $(F5_AI_SECURITY_NAMESPACE) --create-namespace \
			$(F5_HELM_FLAGS) \
			-f "$(F5_AI_SECURITY_VALUES)" $$HELM_EXTRAS; then \
			break; \
		fi; \
		if [ $$R2 -eq 5 ]; then \
			echo -e "$(RED)[ERROR]$(NC) Second Helm apply failed after 5 attempts."; \
			exit 1; \
		fi; \
		echo -e "$(YELLOW)[INFO]$(NC) Second Helm apply retry $$R2/5..."; \
		R2=$$((R2 + 1)); \
		sleep $(F5_HELM_RETRY_SLEEP); \
	done; \
	if [ "$(F5_INFERENCE_PENDING_POD_DELETE)" != "0" ] && oc get ns "$(F5_INFERENCE_NS)" >/dev/null 2>&1; then \
		echo -e "$(BLUE)[INFO]$(NC) If KubeAI model pods are Pending (capacity race), delete once after $(F5_INFERENCE_SCHEDULE_WAIT_SECONDS)s..."; \
		sleep "$(F5_INFERENCE_SCHEDULE_WAIT_SECONDS)"; \
		PEND=$$(oc get pods -n "$(F5_INFERENCE_NS)" --no-headers 2>/dev/null | awk '$$3=="Pending" && $$1 ~ /^model-/{print $$1}' || true); \
		if [ -n "$$PEND" ]; then \
			echo "$$PEND" | while read -r p; do \
				if [ -n "$$p" ]; then oc delete pod -n "$(F5_INFERENCE_NS)" "$$p" --wait=false || true; fi; \
			done; \
			echo -e "$(BLUE)[INFO]$(NC) Deleted Pending model pod(s): $$(echo $$PEND | tr '\n' ' ')"; \
		fi; \
	fi; \
	echo -e "$(GREEN)[SUCCESS]$(NC) $(F5_AI_SECURITY_CHART) release $(F5_AI_SECURITY_RELEASE) applied"

# Uninstall the deployment and clean up
.PHONY: uninstall
uninstall: ## Uninstall the RAG deployment and clean up resources
	@if [ -z "$(NAMESPACE)" ]; then echo -e "$(RED)[ERROR]$(NC) NAMESPACE is required for uninstall"; exit 1; fi
	@echo -e "$(BLUE)[INFO]$(NC) Uninstalling $(RAG_CHART) helm chart..."
	@helm -n $(NAMESPACE) uninstall $(RAG_CHART)
	@echo -e "$(BLUE)[INFO]$(NC) Removing pgvector PVCs from $(NAMESPACE)..."
	@oc get pvc -n $(NAMESPACE) -o custom-columns=NAME:.metadata.name | grep -E '^pg-data' | xargs -I {} oc delete pvc -n $(NAMESPACE) {} ||:
	@echo -e "$(BLUE)[INFO]$(NC) Deleting remaining pods in namespace $(NAMESPACE)..."
	@oc delete pods -n $(NAMESPACE) --all || true
	@echo -e "$(YELLOW)[INFO]$(NC) Remaining resources in namespace $(NAMESPACE) (before operator teardown):"
	@$(MAKE) status || true
	@echo -e "$(BLUE)[INFO]$(NC) Removing F5 AI Security Helm release (if present)..."
	@helm -n $(F5_AI_SECURITY_NAMESPACE) uninstall $(F5_AI_SECURITY_RELEASE) 2>/dev/null || true
	@echo -e "$(BLUE)[INFO]$(NC) Removing F5 AI Guardrails (SecurityOperator, subscription, CSV, namespaces)..."
	@oc delete securityoperator $(SECURITYOPERATOR_NAME) -n $(CAI_MODERATOR_NS) --ignore-not-found 2>/dev/null || true
	@oc delete subscription $(OPERATOR_SUBSCRIPTION) -n $(F5_OPERATOR_NS) --ignore-not-found 2>/dev/null || true
	@for csv in $$(oc get csv -n $(F5_OPERATOR_NS) -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}' 2>/dev/null | grep '^$(OPERATOR_SUBSCRIPTION)' || true); do \
		oc delete csv "$$csv" -n $(F5_OPERATOR_NS) --ignore-not-found 2>/dev/null || true; \
	done
	@for ns in $(GUARDRAILS_PROJECT_NS); do \
		oc delete project "$$ns" --wait=false 2>/dev/null || true; \
	done
	@oc delete project "$(NAMESPACE)" --wait=false 2>/dev/null || true
	@echo -e "$(GREEN)[SUCCESS]$(NC) Uninstall completed (namespaces may stay Terminating until the cluster finishes cleanup)"

# Check deployment status
.PHONY: status
status: ## Check status of the deployment
	@if [ -z "$(NAMESPACE)" ]; then echo -e "$(RED)[ERROR]$(NC) NAMESPACE is required for status"; exit 1; fi
	@echo -e "$(BLUE)[INFO]$(NC) Listing pods..."
	@oc get pods -n $(NAMESPACE) || true
	@echo -e ""
	@echo -e "$(BLUE)[INFO]$(NC) Listing services..."
	@oc get svc -n $(NAMESPACE) || true
	@echo -e ""
	@echo -e "$(BLUE)[INFO]$(NC) Listing routes..."
	@oc get routes -n $(NAMESPACE) || true
	@echo -e ""
	@echo -e "$(BLUE)[INFO]$(NC) Listing secrets..."
	@oc get secrets -n $(NAMESPACE) | grep huggingface-secret || true
	@echo -e ""
	@echo -e "$(BLUE)[INFO]$(NC) Listing pvcs..."
	@oc get pvc -n $(NAMESPACE) || true


# Delete all jobs in the namespace
.PHONY: delete-jobs
delete-jobs: ## Delete all jobs in the namespace
	@echo -e "$(BLUE)[INFO]$(NC) Deleting all jobs in namespace $(NAMESPACE)..."
	@oc delete jobs -n $(NAMESPACE) --all ||:
	@echo -e "$(GREEN)[SUCCESS]$(NC) Job deletion completed"

# --- Local Streamlit UI (runs frontend/dev-on-cluster.sh) ---
.PHONY: deploy-ui-local ui-local deploy-ui-local-foreground undeploy-ui-local

deploy-ui-local ui-local: ## Start Streamlit at http://localhost:8501 in background (nohup + pid file)
	@if [ ! -f "$(FRONTEND_DIR)/dev-on-cluster.sh" ]; then \
		echo -e "$(RED)[ERROR]$(NC) Expected $(FRONTEND_DIR)/dev-on-cluster.sh"; exit 1; \
	fi
	@if [ -f "$(UI_PIDFILE)" ] && kill -0 "$$(cat "$(UI_PIDFILE)" 2>/dev/null)" 2>/dev/null; then \
		echo -e "$(RED)[ERROR]$(NC) Local UI already running (PID $$(cat "$(UI_PIDFILE)")). Run: make undeploy-ui-local"; \
		exit 1; \
	fi
	@rm -f "$(UI_PIDFILE)" 2>/dev/null; \
		cd "$(FRONTEND_DIR)" && nohup bash ./dev-on-cluster.sh >>"$(UI_LOGFILE)" 2>&1 & echo $$! > "$(UI_PIDFILE)"; \
		echo -e "$(GREEN)[SUCCESS]$(NC) Local UI in background: http://localhost:8501"; \
		echo -e "  PID: $$(cat "$(UI_PIDFILE)")  Log: $(UI_LOGFILE)"; \
		echo -e "  Stop with: $(BLUE)make undeploy-ui-local$(NC)";

undeploy-ui-local: ## Stop background local UI started by deploy-ui-local
	@if [ ! -f "$(UI_PIDFILE)" ]; then \
		echo "No local UI pid file; nothing to stop."; \
		exit 0; \
	fi; \
	PID=$$(cat "$(UI_PIDFILE)"); \
	if ! kill -0 "$$PID" 2>/dev/null; then \
		echo "Removing stale pid $$PID"; \
		rm -f "$(UI_PIDFILE)"; \
		exit 0; \
	fi; \
	kill "$$PID" 2>/dev/null || true; \
	sleep 1; \
	if kill -0 "$$PID" 2>/dev/null; then kill -9 "$$PID" 2>/dev/null || true; fi; \
	rm -f "$(UI_PIDFILE)"; \
	echo "Stopped local UI (was PID $$PID)."

deploy-ui-local-foreground: ## Run Streamlit in foreground (blocks; Ctrl+C to stop)
	@if [ ! -f "$(FRONTEND_DIR)/dev-on-cluster.sh" ]; then \
		echo -e "$(RED)[ERROR]$(NC) Expected $(FRONTEND_DIR)/dev-on-cluster.sh"; exit 1; \
	fi
	@cd "$(FRONTEND_DIR)" && exec bash ./dev-on-cluster.sh

# --- F5 XC Deployment (Ansible) ---
ANSIBLE_DIR := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))../ansible
ANSIBLE_TAGS ?=

.PHONY: f5-deploy
f5-deploy: ## Deploy F5 XC Customer Edge mesh via Ansible
	@command -v ansible-playbook >/dev/null 2>&1 || { \
		echo -e "$(RED)[ERROR]$(NC) ansible-playbook not found."; \
		echo -e "$(BLUE)[INFO]$(NC) Activate your Ansible venv or install Ansible:"; \
		echo -e "        pip install ansible kubernetes"; \
		exit 1; \
	}
	@if [ ! -f "$(ANSIBLE_DIR)/group_vars/all/secrets.yml" ]; then \
		echo -e "$(RED)[ERROR]$(NC) secrets.yml not found at $(ANSIBLE_DIR)/group_vars/all/secrets.yml"; \
		echo -e ""; \
		echo -e "$(YELLOW)Create it from the example:$(NC)"; \
		echo -e "  cp $(ANSIBLE_DIR)/group_vars/all/secrets.yml.example \\"; \
		echo -e "     $(ANSIBLE_DIR)/group_vars/all/secrets.yml"; \
		echo -e ""; \
		echo -e "Then set $(BLUE)f5xc_token$(NC) and $(BLUE)f5xc_cluster_name$(NC) before re-running."; \
		exit 1; \
	fi
	@echo -e "$(BLUE)[INFO]$(NC) Installing Ansible collection dependencies..."
	@ansible-galaxy collection install -r "$(ANSIBLE_DIR)/requirements.yml" --force-with-deps -p "$(ANSIBLE_DIR)/collections" >/dev/null
	@echo -e "$(BLUE)[INFO]$(NC) Running F5 XC CE deployment playbook..."
	@ANSIBLE_STDOUT_CALLBACK=default ANSIBLE_CALLBACK_RESULT_FORMAT=yaml ansible-playbook "$(ANSIBLE_DIR)/site.yml" \
		-e "ansible_collections_path=$(ANSIBLE_DIR)/collections" \
		$(if $(ANSIBLE_TAGS),--tags "$(ANSIBLE_TAGS)",)

.PHONY: f5-clean
f5-clean: ## Remove F5 XC Customer Edge deployment and cluster resources
	@command -v ansible-playbook >/dev/null 2>&1 || { \
		echo -e "$(RED)[ERROR]$(NC) ansible-playbook not found."; \
		echo -e "$(BLUE)[INFO]$(NC) Activate your Ansible venv or install Ansible:"; \
		echo -e "        pip install ansible kubernetes"; \
		exit 1; \
	}
	@echo -e "$(BLUE)[INFO]$(NC) Running F5 XC CE cleanup playbook..."
	@ANSIBLE_STDOUT_CALLBACK=default ANSIBLE_CALLBACK_RESULT_FORMAT=yaml ansible-playbook "$(ANSIBLE_DIR)/cleanup.yml" \
		-e "ansible_collections_path=$(ANSIBLE_DIR)/collections" \
		$(if $(REMOVE_HUGEPAGES),-e "remove_hugepages=true",)
