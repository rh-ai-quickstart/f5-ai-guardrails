# Troubleshooting F5 AI Guardrails

Common failure patterns and fixes encountered during installation and operation.

---

| # | Symptom | Root Cause | Fix |
|---|---------|------------|-----|
| 1 | PostgreSQL stuck at 0/1 | Missing `anyuid` SCC | [Step 3.1](installing_f5_ai_guardrails.md#31-apply-required-scc-policies) |
| 2 | Prefect logs show `403 Forbidden` | Missing cluster-scope RBAC | [Step 5](installing_f5_ai_guardrails.md#step-5-prefect-worker-rbac) |
| 3 | UI loads blank or black page | Missing `/auth` route | [Step 4](installing_f5_ai_guardrails.md#step-4-route-configuration) |
| 4 | Operator stuck in `Installing` / controller-manager CrashLoopBackOff | Missing SCC permissions for operator SA | [Fix 4](#fix-4-operator-scc-permissions) |
| 5 | controller-manager OOMKilled | Default 128Mi memory limit insufficient | [Fix 5](#fix-5-controller-manager-oomkilled) |
| 6 | "Invalid License" after reinstall | Encryption key mismatch in settings table | [Fix 6](#fix-6-invalid-license-after-reinstall) |
| 7 | "Internal error" / Keycloak 400 after node outage | PostgreSQL connection pool exhaustion | [Fix 7](#fix-7-keycloak-400--connection-pool-exhaustion) |

---

### Fix 4: Operator SCC permissions

```bash
cat <<'EOF' | oc apply -f -
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: f5-ai-security-operator-scc
rules:
- apiGroups: ["security.openshift.io"]
  resources: ["securitycontextconstraints"]
  verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: f5-ai-security-operator-scc
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: f5-ai-security-operator-scc
subjects:
- kind: ServiceAccount
  name: controller-manager
  namespace: f5-ai-sec
EOF
oc rollout restart deployment/controller-manager -n f5-ai-sec
```

### Fix 5: controller-manager OOMKilled

```bash
oc patch deployment controller-manager -n f5-ai-sec --type=json \
  -p='[{"op":"replace","path":"/spec/template/spec/containers/0/resources/limits/memory","value":"512Mi"},
       {"op":"replace","path":"/spec/template/spec/containers/0/resources/requests/memory","value":"256Mi"}]'
```

### Fix 6: "Invalid License" after reinstall

```bash
oc exec -n cai-moderator cai-moderator-postgres-cai-postgresql-0 -- \
  psql -U postgres -d moderator -c "DELETE FROM setting;"
oc rollout restart deployment/cai-moderator -n cai-moderator
```

### Fix 7: Keycloak 400 / connection pool exhaustion

```bash
# Immediate fix
oc exec -n cai-moderator cai-moderator-postgres-cai-postgresql-0 -- \
  psql -U postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE state = 'idle' AND pid <> pg_backend_pid();"
oc rollout restart deployment/cai-moderator -n cai-moderator

# Permanent fix (raise max_connections)
oc exec -n cai-moderator cai-moderator-postgres-cai-postgresql-0 -- \
  psql -U postgres -c "ALTER SYSTEM SET max_connections = 200;"
oc rollout restart statefulset/cai-moderator-postgres-cai-postgresql -n cai-moderator
```
