# Kubernetes (kind) verification

`deploy/k8s/base` is a kustomize base (namespace, ConfigMap, PVCs, Redis, api Deployment + Service, worker
Deployment, HPA). `deploy/k8s/overlays/ci` sets `DOCAGENT_PROVIDER=fake` and smaller resource requests so the
rollout fits a CI runner. `scripts/kind-up.sh` builds the image, loads it into a kind cluster, applies the overlay,
waits for every rollout, port-forwards the api Service and runs `scripts/wait_and_smoke.py` (upload → worker
indexes → query with a citation). CI runs this on every push.

Recorded run on 2026-10-04 (Apple M4, Docker Desktop, kind v0.33.0):

```
$ bash scripts/kind-up.sh
service/api created
service/redis created
deployment.apps/api created
deployment.apps/redis created
deployment.apps/worker created
horizontalpodautoscaler.autoscaling/api created
deployment "redis" successfully rolled out
deployment "api" successfully rolled out
deployment "worker" successfully rolled out
SMOKE OK

$ kubectl -n docagent get all
NAME                         READY   STATUS    RESTARTS   AGE
pod/api-888dd8ff4-dwwhc      1/1     Running   0          30s
pod/redis-85c8f67d-9hbl6     1/1     Running   0          30s
pod/worker-59c95b97c-9z4mt   1/1     Running   0          30s
NAME            TYPE        CLUSTER-IP      EXTERNAL-IP   PORT(S)    AGE
service/api     ClusterIP   10.96.143.252   <none>        8000/TCP   30s
service/redis   ClusterIP   10.96.90.111    <none>        6379/TCP   30s
NAME                     READY   UP-TO-DATE   AVAILABLE   AGE
deployment.apps/api      1/1     1            1           30s
deployment.apps/redis    1/1     1            1           30s
deployment.apps/worker   1/1     1            1           30s
NAME                                      REFERENCE        TARGETS              MINPODS   MAXPODS   REPLICAS   AGE
horizontalpodautoscaler.autoscaling/api   Deployment/api   cpu: <unknown>/70%   1         3         1          30s
```

Notes:

- The HPA shows `cpu: <unknown>` on kind because no metrics-server is installed; on a managed cluster install one
  (or use the cloud provider's) for the autoscaler to act.
- The api and worker share the `docagent-data` and `docagent-models` PVCs (ReadWriteOnce). That works on a
  single-node cluster such as kind; a multi-node cluster needs ReadWriteMany storage (EFS on AWS, which the
  Terraform in `deploy/terraform/aws` provisions).
- The worker must stay at one replica: ingestion appends to a single on-disk index.
- Tear down with `bash scripts/kind-down.sh`.
