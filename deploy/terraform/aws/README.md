# DocAgent on AWS ECS Fargate (Terraform)

**Status: this configuration has been `terraform validate`d but NOT applied.**
It has never been planned or applied against a real AWS account, so expect to
fix small things on first apply.

## Design

```
Internet -> ALB :80 --/        -> ui  (nginx, :80)  --http://api:8000--> api (:8000)
                    --/api/*   -> api (:8000)  (direct, no prefix rewrite)
worker (arq) --> Redis (ElastiCache)      api + worker --> EFS (/data, /models)
```

- **Primary path**: ALB default action forwards to `ui`. The ui's nginx proxies
  `/api/` to `http://api:8000`, resolved through ECS Service Connect
  (Cloud Map namespace `docagent.local`, client alias `api:8000`). Your ui
  nginx config must proxy to `http://api:8000/`.
- **Secondary path**: an ALB rule sends `/api/*` straight to the api target
  group (health check `/healthz`). ALB cannot rewrite paths, so the api sees
  the `/api` prefix; use this only if the api serves under that prefix, and
  treat the UI proxy as the supported route.
- **EFS**: one encrypted file system with two access points (`/data` and
  `/models`, posix user 1000:1000), mounted by both api and worker. One file
  system keeps cost and mount targets minimal.
- **Redis**: single-node ElastiCache replication group (`cache.t4g.micro`) in
  private subnets; only the tasks SG can reach 6379.
- **Network**: VPC module, 2 public + 2 private subnets, one NAT gateway.
  Tasks run in private subnets.
- **Secret**: `ANTHROPIC_API_KEY` is stored in Secrets Manager only when
  `anthropic_api_key` is non-empty, and injected via the task `secrets` block.
- HTTPS is a follow-up: add an ACM certificate, an HTTPS :443 listener, and
  redirect :80 to it.

## Deploy

```sh
cd deploy/terraform/aws
terraform init
# create the repos first so you have somewhere to push
terraform apply -target=aws_ecr_repository.api -target=aws_ecr_repository.ui

ECR_API=$(terraform output -raw ecr_api_url)
ECR_UI=$(terraform output -raw ecr_ui_url)
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin "${ECR_API%%/*}"
docker build --platform linux/amd64 -t "$ECR_API:v1" <path-to-api-Dockerfile-context> && docker push "$ECR_API:v1"
docker build --platform linux/amd64 -t "$ECR_UI:v1"  <path-to-ui-context>             && docker push "$ECR_UI:v1"

terraform apply -var image_tag=v1 [-var provider_mode=anthropic -var anthropic_api_key=...]
terraform output alb_dns_name
```

Tasks use the default x86_64 Fargate platform, so build images for linux/amd64.
The first api/worker start downloads models into `/models` on EFS and can be slow.

## Rough monthly cost (us-east-1, always on)

| Item | Approx. |
|---|---|
| Fargate: 2 x (1 vCPU / 4 GB) + 1 x (0.25 vCPU / 0.5 GB) | $75-85 |
| NAT gateway (single) | $33 |
| ALB | $18 |
| ElastiCache cache.t4g.micro | $12 |
| EFS (small) | pennies |
| **Total** | **~$140-150** |

## Tear down

```sh
terraform destroy -var image_tag=v1
```

ECR repos are created with `force_delete = true` so images do not block
destroy. The Secrets Manager secret is deleted immediately (no recovery window).
EFS contents (uploaded documents, model cache) are destroyed too.
