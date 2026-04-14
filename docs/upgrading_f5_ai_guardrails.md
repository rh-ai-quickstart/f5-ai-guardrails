# Upgrading F5 AI Guardrails on OpenShift

This guide covers upgrading the **F5 AI Security Operator** from v0.4.3 (alpha channel) to v0.7.0 (stable channel) on a Red Hat OpenShift cluster. It preserves existing data and minimizes downtime.

---

## Table of contents

- [Before you begin](#before-you-begin)
- [What changed in v0.7.0](#what-changed-in-v070)
- [Step 1: Back up the SecurityOperator CR](#step-1-back-up-the-securityoperator-cr)
- [Step 2: Remove the SecurityOperator CR](#step-2-remove-the-securityoperator-cr)
- [Step 3: Uninstall the v0.4.3 operator](#step-3-uninstall-the-v043-operator)
- [Step 4: Install v0.7.0 from the stable channel](#step-4-install-v070-from-the-stable-channel)
- [Step 5: Apply the updated SecurityOperator CR](#step-5-apply-the-updated-securityoperator-cr)
- [Step 6: Grant SCC to inference service accounts](#step-6-grant-scc-to-inference-service-accounts)
- [Step 7: Verify the upgrade](#step-7-verify-the-upgrade)
- [Step 8: Clean up old namespaces](#step-8-clean-up-old-namespaces)
- [Post-upgrade tasks](#post-upgrade-tasks)
- [Troubleshooting](#troubleshooting)
- [Rollback](#rollback)

---

## Before you begin

### Prerequisites

- OpenShift CLI (`oc`) authenticated with cluster-admin privileges
- F5 AI Security Operator v0.4.3 installed and running on the alpha channel
- All product pods healthy (`cai-moderator`, `cai-scanner`, `cai-redteam`, `prefect`)

### Pre-flight checks

```bash
# Verify current operator version
oc get csv -n f5-ai-sec | grep f5-ai-security
# Expected: f5-ai-security-operator.v0.4.3   Succeeded

# Verify all product pods are running
oc get pods -n cai-moderator
oc get pods -n cai-scanner
oc get pods -n cai-redteam
oc get pods -n prefect

# Verify v0.7.0 is available in the stable channel
oc get packagemanifest f5-ai-security-operator -n openshift-marketplace \
  -o jsonpath='{range .status.channels[*]}Channel: {.name}, CSV: {.currentCSV}{"\n"}{end}'
# Expected: Channel: stable, CSV: f5-ai-security-operator.v0.7.0

# Record current image versions for reference
for ns in f5-ai-sec cai-moderator cai-scanner cai-redteam prefect; do
  echo "=== $ns ==="
  oc get pods -n $ns -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{range .spec.containers[*]}{.image}{"\n"}{end}{end}' 2>/dev/null
done
```

### Estimated downtime

- **Product pods** (moderator, scanner, prefect): Continue running throughout the upgrade. Downtime occurs only when the new operator reconciles and rolls out updated deployments (~2-5 minutes).
- **Operator**: Not reconciling during the swap (~5 minutes). Existing pods are unaffected.

---

## What changed in v0.7.0

| Area | v0.4.3 (alpha) | v0.7.0 (stable) |
|------|-----------------|------------------|
| Channel | `alpha` | `stable` |
| Scanner + Red Team | Separate products: `scanner` and `redTeam` in CR spec, deployed to `cai-scanner` and `cai-redteam` namespaces | Consolidated into single `inference` product, deployed to `f5-ai-sec-inference` namespace |
| Moderator image | `cai_moderator:v9.133.x` | `cai_moderator:v9.189.x` |
| Moderator chart | v1.5.0 | v1.7.0 |
| JobManager chart | v1.0.0 | v1.2.0 |
| Inference chart | N/A | v1.0.0 (new) |
| CR spec fields | `scanner`, `redTeam` | `inference` (replaces both) |

### CR spec comparison

**v0.4.3:**
```yaml
spec:
  scanner:
    enabled: true
  redTeam:
    enabled: true
```

**v0.7.0:**
```yaml
spec:
  inference:
    enabled: true
```

---

## Step 1: Back up the SecurityOperator CR

Export the current CR so you can reference it or roll back if needed:

```bash
oc get securityoperator security-operator-demo -n cai-moderator -o yaml > /tmp/security-operator-cr-backup.yaml
```

Verify the backup:

```bash
grep -c "kind: SecurityOperator" /tmp/security-operator-cr-backup.yaml
# Expected: 1
```

---

## Step 2: Remove the SecurityOperator CR

> **Critical:** Remove the finalizer _before_ deleting the CR. This prevents the operator from cascading a Helm uninstall that would tear down all product pods and delete data.

```bash
# Remove the finalizer (prevents cascading teardown)
oc patch securityoperator security-operator-demo -n cai-moderator \
  --type=json -p='[{"op":"remove","path":"/metadata/finalizers"}]'

# Delete the CR
oc delete securityoperator security-operator-demo -n cai-moderator
```

Verify product pods are still running (they should be unaffected):

```bash
oc get pods -n cai-moderator
oc get pods -n prefect
```

---

## Step 3: Uninstall the v0.4.3 operator

Delete the OLM resources in order. The OperatorGroup is retained for reuse:

```bash
# Delete the subscription
oc delete subscription f5-ai-security-operator -n f5-ai-sec

# Delete the CSV (this also removes the controller-manager deployment and OLM-generated RBAC)
oc delete csv f5-ai-security-operator.v0.4.3 -n f5-ai-sec
```

Verify the old operator is fully gone:

```bash
oc get csv -n f5-ai-sec | grep f5-ai-security
# Expected: no output

oc get pods -n f5-ai-sec
# Expected: No resources found
```

> **Note:** The 3 custom ClusterRoles created for known issues (`f5-ai-security-operator-scc`, `-rbac-escalate`, `-workloads`) are retained. The new operator may still need them.

---

## Step 4: Install v0.7.0 from the stable channel

Create a new Subscription pointing to the stable channel:

```bash
cat <<'EOF' | oc apply -f -
apiVersion: operators.coreos.com/v1alpha1
kind: Subscription
metadata:
  name: f5-ai-security-operator
  namespace: f5-ai-sec
spec:
  channel: stable
  installPlanApproval: Automatic
  name: f5-ai-security-operator
  source: certified-operators
  sourceNamespace: openshift-marketplace
  startingCSV: f5-ai-security-operator.v0.7.0
EOF
```

Wait for the operator to become ready (~30-60 seconds):

```bash
# Watch CSV status
oc get csv -n f5-ai-sec -w
# Wait for: f5-ai-security-operator.v0.7.0   Succeeded

# Verify controller-manager is running
oc get pods -n f5-ai-sec
# Expected: controller-manager-<hash>   1/1   Running
```

If the controller-manager hits **OOMKilled**, increase memory limits:

```bash
oc patch deployment controller-manager -n f5-ai-sec --type=json \
  -p='[{"op":"replace","path":"/spec/template/spec/containers/0/resources/limits/memory","value":"512Mi"},
       {"op":"replace","path":"/spec/template/spec/containers/0/resources/requests/memory","value":"256Mi"}]'
```

---

## Step 5: Apply the updated SecurityOperator CR

The v0.7.0 CRD replaces `scanner` and `redTeam` with a single `inference` field. Apply the updated CR:

```bash
cat <<'EOF' | oc apply -f -
apiVersion: ai.security.f5.com/v1alpha1
kind: SecurityOperator
metadata:
  name: security-operator-demo
  namespace: cai-moderator
spec:
  inference:
    enabled: true
  jobManager:
    enabled: true
  moderator:
    enabled: true
    values:
      env:
        CAI_MODERATOR_BASE_URL: "https://<your-hostname>"
      secrets:
        CAI_MODERATOR_DB_ADMIN_PASSWORD: "<your-db-password>"
        CAI_MODERATOR_DEFAULT_LICENSE: "<your-license-key>"
  postgresql:
    enabled: true
    values:
      postgresql:
        auth:
          password: "<your-db-password>"
  registryAuth:
    enabled: true
    existingSecret: regcred
    registry: harbor.calypsoai.app
    secretName: regcred
EOF
```

> **Important:** Replace `<your-hostname>`, `<your-db-password>`, and `<your-license-key>` with the values from your v0.4.3 CR backup at `/tmp/security-operator-cr-backup.yaml`.

Monitor the reconciliation:

```bash
oc logs -n f5-ai-sec deployment/controller-manager -f --tail=50
```

Expected log output:

```
controllers.ProductReconciler.moderator    No Helm upgrade/install needed (version and spec match)
controllers.ProductReconciler.postgresql   No Helm upgrade/install needed (version and spec match)
controllers.ProductReconciler.jobManager   No Helm upgrade/install needed (version and spec match)
controllers.ProductReconciler.inference    Upgrading Helm release    {"releaseName": "f5-ai-sec-inference"}
```

The operator reuses existing Helm releases for moderator, postgresql, and jobManager. It creates a new `f5-ai-sec-inference` namespace and deploys the inference chart.

---

## Step 6: Grant SCC to inference service accounts

The new `f5-ai-sec-inference` namespace requires `anyuid` SCC, just like the old scanner and redteam namespaces did. Without this, inference pods fail with `Permission denied`.

```bash
oc adm policy add-scc-to-user anyuid -z f5-ai-sec-inference -n f5-ai-sec-inference
oc adm policy add-scc-to-user anyuid -z f5-ai-sec-inference-models -n f5-ai-sec-inference
```

Restart the crashing pods:

```bash
oc delete pods -n f5-ai-sec-inference --all
```

Wait ~30 seconds and verify:

```bash
oc get pods -n f5-ai-sec-inference
# Expected: all pods Running and Ready
```

---

## Step 7: Verify the upgrade

### 7.1 Operator status

```bash
oc get csv -n f5-ai-sec
# Expected: f5-ai-security-operator.v0.7.0   F5 AI Security Operator   0.7.0   Succeeded

oc get pods -n f5-ai-sec
# Expected: controller-manager   1/1   Running
```

### 7.2 Product pods

```bash
oc get pods -n cai-moderator
# Expected: cai-moderator + postgres   Running

oc get pods -n prefect
# Expected: prefect-server + prefect-worker   Running

oc get pods -n f5-ai-sec-inference
# Expected: inference pods   Running
```

### 7.3 Operator reconciliation

```bash
oc logs -n f5-ai-sec deployment/controller-manager --tail=20 | grep -i "error\|fail"
# Expected: no output (no errors)
```

### 7.4 Routes

```bash
oc get route -n cai-moderator
# Expected: cai-moderator-ui and cai-moderator-auth routes intact
```

### 7.5 UI access

Open `https://<your-hostname>` in a browser. If you see "Invalid License", see [Troubleshooting](#invalid-license-after-upgrade).

### 7.6 Image versions

```bash
for ns in f5-ai-sec cai-moderator f5-ai-sec-inference prefect; do
  echo "=== $ns ==="
  oc get pods -n $ns -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{range .spec.containers[*]}{.image}{"\n"}{end}{end}' 2>/dev/null
done
```

---

## Step 8: Clean up old namespaces

After confirming the upgrade is successful, remove the old scanner and redteam namespaces that are no longer managed by v0.7.0:

```bash
# Check for any remaining pods
oc get pods -n cai-scanner
oc get pods -n cai-redteam

# Delete orphaned pods (if any)
oc delete pods -n cai-scanner --all
oc delete pods -n cai-redteam --all

# Delete Helm release secrets
oc delete secrets -n cai-scanner -l owner=helm
oc delete secrets -n cai-redteam -l owner=helm

# Delete the namespaces (optional — only if no other workloads use them)
oc delete namespace cai-scanner
oc delete namespace cai-redteam
```

---

## Post-upgrade tasks

### API tokens

API tokens from the v0.4.3 installation are **invalidated** after the moderator restarts with a new encryption key. Create new tokens in the UI under **API Tokens**.

### Update external integrations

If you have scripts or applications using the OpenAI-compatible endpoint, update them with the new API token:

```bash
curl -sk -X POST https://<your-hostname>/openai/llamastack/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <NEW_API_TOKEN>" \
  -d '{
    "model": "llama-3-2-1b-instruct-quantized/RedHatAI/Llama-3.2-1B-Instruct-quantized.w8a8",
    "messages": [{"role": "user", "content": "say hi"}],
    "max_tokens": 20
  }'
```

### Update CLAUDE.md

If your repository has a `CLAUDE.md` referencing operator version or namespace layout, update it to reflect:
- Operator version: `v0.7.0`
- Channel: `stable`
- New namespace: `f5-ai-sec-inference` (replaces `cai-scanner` and `cai-redteam`)

---

## Troubleshooting

### Invalid License after upgrade

**Symptom:** UI shows "Invalid License — No valid license found."

**Cause:** The moderator encryption key changed during reinstall. The `setting`, `secret`, and `secret_config` tables hold data encrypted with the old key.

**Fix:**

```bash
oc exec -n cai-moderator cai-moderator-postgres-cai-postgresql-0 -- \
  psql -U postgres -d moderator -c "DELETE FROM setting; DELETE FROM secret_config; DELETE FROM secret;"
oc rollout restart deployment/cai-moderator -n cai-moderator
```

> **Note:** After this, re-add providers in the UI, assign them to your project, and create new API tokens.

### Inference pods: Permission denied

**Symptom:** Pods in `f5-ai-sec-inference` crash with `exec container process: Permission denied`.

**Cause:** Missing `anyuid` SCC on the inference service accounts.

**Fix:** See [Step 6](#step-6-grant-scc-to-inference-service-accounts).

### controller-manager OOMKilled

**Symptom:** controller-manager pod OOMKilled shortly after starting.

**Fix:**

```bash
oc patch deployment controller-manager -n f5-ai-sec --type=json \
  -p='[{"op":"replace","path":"/spec/template/spec/containers/0/resources/limits/memory","value":"512Mi"},
       {"op":"replace","path":"/spec/template/spec/containers/0/resources/requests/memory","value":"256Mi"}]'
```

### Operator RBAC errors

**Symptom:** controller-manager logs show `forbidden` errors for SCC, RBAC escalate, or workload resources.

**Fix:** Re-apply the custom ClusterRoles documented in [troubleshooting.md](troubleshooting.md) (Fixes 4 and the RBAC escalate / workloads ClusterRoles from the main CLAUDE.md).

### Helm release conflicts

**Symptom:** controller-manager logs show `has no deployed releases` for a product.

**Fix:** Delete stale Helm release secrets and trigger a reconcile:

```bash
# Example for inference
oc delete secrets -n f5-ai-sec-inference -l owner=helm,name=f5-ai-sec-inference
oc annotate securityoperator security-operator-demo -n cai-moderator reconcile=$(date +%s) --overwrite
```

---

## Rollback

If the upgrade fails and you need to revert to v0.4.3:

1. Remove the v0.7.0 CR (with finalizer removal):
   ```bash
   oc patch securityoperator security-operator-demo -n cai-moderator \
     --type=json -p='[{"op":"remove","path":"/metadata/finalizers"}]'
   oc delete securityoperator security-operator-demo -n cai-moderator
   ```

2. Delete the v0.7.0 operator:
   ```bash
   oc delete subscription f5-ai-security-operator -n f5-ai-sec
   oc delete csv f5-ai-security-operator.v0.7.0 -n f5-ai-sec
   ```

3. Reinstall v0.4.3 on the alpha channel:
   ```bash
   cat <<'EOF' | oc apply -f -
   apiVersion: operators.coreos.com/v1alpha1
   kind: Subscription
   metadata:
     name: f5-ai-security-operator
     namespace: f5-ai-sec
   spec:
     channel: alpha
     installPlanApproval: Automatic
     name: f5-ai-security-operator
     source: certified-operators
     sourceNamespace: openshift-marketplace
     startingCSV: f5-ai-security-operator.v0.4.3
   EOF
   ```

4. Re-apply the backed-up CR:
   ```bash
   oc apply -f /tmp/security-operator-cr-backup.yaml
   ```

> **Note:** If the `f5-ai-sec-inference` namespace was created during the upgrade, it will remain after rollback. Delete it manually if not needed.
