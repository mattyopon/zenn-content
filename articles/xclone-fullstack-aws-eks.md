---
title: "X(Twitter)クローンをTerraform + EKS + Ansible + GitHub Actionsでフルスタック構築し、SRE運用基盤まで整えた全記録"
emoji: "🐦"
type: "tech"
topics: ["terraform", "kubernetes", "aws", "sre", "datadog"]
published: true
---

## はじめに

本記事では、X（旧Twitter）クローンを題材に、**フロントエンドからバックエンド、コンテナ基盤、IaC、CI/CD、構成管理、監視・可観測性、SRE運用基盤まで**を一人でフルスタック構築した記録を共有します。

「動くものを作った」で終わらせるのではなく、**SIerやSRE組織で実際に通用するレベルのドキュメント・運用設計**を含めることを意識しました。本記事を読んでいただければ、筆者のインフラ〜アプリケーション横断のスキルセットが伝わるかと思います。

### 筆者のバックグラウンド

- クラウドインフラエンジニアとして8年間、放送・メディア業界で大規模システムの設計・構築・運用を担当してきました
- AWS / GCP / Azure のマルチクラウド設計、Terraform / Ansible / Kubernetes による自動化、SREプラクティスの導入に携わってきました
- 100台以上のサーバーを含むオンプレ→クラウド移行プロジェクトのリードも経験しています

### 本記事で扱う範囲

```
┌───────────────────────────────────────────────────────────────────┐
│  📄 ドキュメント                                                  │
│  ├─ 要件定義書 / 非機能要件一覧                                  │
│  ├─ アーキテクチャ設計書 (HLD / LLD)                             │
│  ├─ テスト計画書 / 負荷テスト結果                                │
│  ├─ 運用設計書 / Runbook                                         │
│  └─ 障害対応フロー / Postmortem テンプレート                     │
├───────────────────────────────────────────────────────────────────┤
│  🏗️ インフラ (IaC / 構成管理)                                    │
│  ├─ Terraform: AWS (EKS/RDS/CloudFront) + GCP (GKE/Cloud SQL)   │
│  ├─ Ansible: セキュリティハードニング / ノード構成管理            │
│  ├─ AWS Organizations マルチアカウント戦略                        │
│  └─ コスト最適化 (Savings Plans / Spot / Rightsizing)            │
├───────────────────────────────────────────────────────────────────┤
│  🐳 コンテナ / オーケストレーション                               │
│  ├─ Docker マルチステージビルド + イメージスキャン                │
│  ├─ Kubernetes (EKS) マニフェスト設計                            │
│  └─ HPA / PDB / NetworkPolicy / Pod Security Standards           │
├───────────────────────────────────────────────────────────────────┤
│  🔄 CI/CD                                                        │
│  ├─ GitHub Actions: lint → test → scan → build → deploy         │
│  ├─ OIDC認証 (IAMアクセスキー完全排除)                           │
│  └─ Canary デプロイ + 自動ロールバック                           │
├───────────────────────────────────────────────────────────────────┤
│  🖥️ アプリケーション                                              │
│  ├─ React + TypeScript (フロントエンド)                          │
│  └─ Express + PostgreSQL + Redis (バックエンド)                  │
├───────────────────────────────────────────────────────────────────┤
│  📊 SRE / 可観測性                                               │
│  ├─ Datadog: APM / Infrastructure / Log Management / Synthetics  │
│  ├─ New Relic: APM / Browser RUM / Synthetics                    │
│  ├─ SLO/SLI 定義 / Error Budget 運用                            │
│  ├─ インシデント対応フロー / Blameless Postmortem                │
│  └─ Secrets Manager + External Secrets Operator                  │
└───────────────────────────────────────────────────────────────────┘
```

---

# Part 1: 設計ドキュメント

## 1.1 要件定義

### 機能要件

| # | 機能 | 優先度 | 説明 |
|---|------|--------|------|
| F-001 | ユーザー登録・認証 | Must | メール + パスワード方式。JWT (RS256) ベースのステートレス認証を採用しています |
| F-002 | ツイート CRUD | Must | 280文字制限。画像添付は最大4枚まで。S3 + CloudFront OAC経由で配信します |
| F-003 | タイムライン | Must | フォロー中ユーザーの投稿をカーソルページネーションで取得します |
| F-004 | いいね・リツイート | Must | 楽観的更新（Optimistic Update）でUXを向上させつつ、サーバーと非同期で同期します |
| F-005 | フォロー / アンフォロー | Must | フォロー数・フォロワー数のリアルタイム更新に対応しています |
| F-006 | プロフィール | Must | 表示名・自己紹介・アバター画像の編集が可能です |
| F-007 | リアルタイム通知 | Should | WebSocket (Socket.io) でいいね・リプライ・フォロー通知をプッシュ配信します |
| F-008 | 全文検索 | Should | PostgreSQL の `ts_vector` + GINインデックスによるツイート全文検索を実装しています |
| F-009 | ダイレクトメッセージ | Could | 1対1のリアルタイムチャット。Redis Pub/Sub で複数Pod間のメッセージ配信に対応しています |
| F-010 | トレンド機能 | Could | 直近1時間のツイートからハッシュタグを集計し、トレンドランキングを生成します |

### 非機能要件

| カテゴリ | 要件 | 目標値 | 根拠 |
|---------|------|--------|------|
| **可用性** | 月間稼働率 | 99.9%（ダウンタイム 43分/月以内） | SLO として定義。Route 53 フェイルオーバーで担保します |
| **レイテンシ** | API p99 レスポンスタイム | < 500ms | Google の調査ではページ読み込み3秒以上で53%が離脱するため、API層で500ms以内を死守します |
| **スループット** | 同時接続ユーザー数 | 1,000 users | HPA + Cluster Autoscaler で水平スケールします |
| **RTO** | 目標復旧時間 | < 15分 | Route 53 ヘルスチェック (10秒間隔) + GCP DR 環境で実現します |
| **RPO** | 目標復旧時点 | < 5分 | RDS 自動バックアップ (5分間隔の WAL アーカイブ) で担保します |
| **セキュリティ** | 認証方式 | JWT (RS256) + Refresh Token (httpOnly Cookie) | OWASP Top 10 準拠。XSS/CSRF/SQLi対策済みです |
| **セキュリティ** | 通信暗号化 | TLS 1.3 (ALB 終端) + VPC内通信も暗号化 | ACM 証明書自動更新です |
| **セキュリティ** | 保存時暗号化 | AES-256 (RDS / S3 / EBS / Secrets Manager) | KMS CMK で鍵管理しています |
| **コスト** | 月額インフラ費用 | dev: ~$80 / prod: ~$520 | Savings Plans + Spot + Rightsizing で最適化済みです |
| **運用** | デプロイ頻度 | 1日複数回 | CI/CD 全自動 + Canaryデプロイで安全にリリースします |
| **運用** | MTTR (平均復旧時間) | < 15分 | Runbook + 自動復旧 + PagerDuty オンコール体制で実現します |

## 1.2 アーキテクチャ設計書 (HLD)

### システム全体構成図

```
                              ┌──────────────┐
                              │   Route 53    │
                              │(DNS failover) │
                              │ + ヘルスチェック│
                              └──────┬────────┘
                                     │
                    ┌────────────────┼────────────────┐
                    │ PRIMARY        │                 │ SECONDARY (DR)
                    ▼                │                 ▼
            ┌──────────────┐        │         ┌──────────────┐
            │  CloudFront   │        │         │  Cloud CDN    │
            │  + WAF v2     │        │         │  + Cloud Armor│
            └──────┬───────┘        │         └──────┬───────┘
                   │                 │                │
            ┌──────▼───────┐        │         ┌──────▼───────┐
            │  ALB          │        │         │  Cloud LB     │
            │  (HTTPS終端)  │        │         │  (GCP)        │
            └──────┬───────┘        │         └──────┬───────┘
                   │                 │                │
        ┌──────────┴──────────┐     │         ┌──────▼───────┐
        │     EKS Cluster      │     │         │  GKE Autopilot│
        │  ┌─────────────────┐ │     │         │  (warm standby)│
        │  │ frontend (React) │ │     │         └──────────────┘
        │  │ 3 replicas       │ │     │
        │  └─────────────────┘ │     │
        │  ┌─────────────────┐ │     │
        │  │ backend (Express)│ │     │
        │  │ 3 replicas + HPA│ │     │
        │  └────────┬────────┘ │     │
        │  ┌────────▼────────┐ │     │
        │  │ worker (Bull)    │ │     │
        │  │ 2 replicas       │ │     │
        │  └─────────────────┘ │     │
        │  ┌─────────────────┐ │     │
        │  │ Datadog Agent   │ │     │
        │  │ (DaemonSet)     │ │     │
        │  └─────────────────┘ │     │
        │  ┌─────────────────┐ │     │
        │  │ External Secrets│ │     │
        │  │ Operator        │ │     │
        │  └─────────────────┘ │     │
        └──────────┬──────────┘     │
                   │                 │
     ┌─────────────┼──────────────┐  │
     ▼             ▼              ▼  │
┌─────────┐ ┌───────────┐ ┌──────┴──────┐
│  RDS     │ │ElastiCache│ │   S3        │
│PostgreSQL│ │ (Redis)   │ │(メディア)   │
│Multi-AZ  │ │ Cluster   │ │+ CloudFront │
│+ リード  │ │ Mode      │ │  OAC        │
│ レプリカ │ │           │ │             │
└─────────┘ └───────────┘ └─────────────┘
```

### ネットワーク設計 (VPC)

```
VPC: 10.0.0.0/16
│
├── Public Subnets (ALB, NAT Gateway, Bastion)
│   ├── 10.0.0.0/24  (ap-northeast-1a)
│   ├── 10.0.1.0/24  (ap-northeast-1c)
│   └── 10.0.2.0/24  (ap-northeast-1d)  ← 本番のみ 3AZ
│
├── Private Subnets (EKS Nodes, Application)
│   ├── 10.0.10.0/24 (ap-northeast-1a)
│   ├── 10.0.11.0/24 (ap-northeast-1c)
│   └── 10.0.12.0/24 (ap-northeast-1d)
│
├── Database Subnets (RDS, ElastiCache)  ← インターネット到達不可
│   ├── 10.0.20.0/24 (ap-northeast-1a)
│   └── 10.0.21.0/24 (ap-northeast-1c)
│
└── Security Groups (最小権限の原則)
    ├── sg-alb:       443 from 0.0.0.0/0 (WAF経由のみ)
    ├── sg-eks-node:  All from sg-alb, 10250/6443 from sg-eks-cp
    ├── sg-rds:       5432 from sg-eks-node only
    ├── sg-redis:     6379 from sg-eks-node only
    └── sg-bastion:   22 from オフィスIP + VPN only
```

### セキュリティ設計 — WAF v2 + Shield

CloudFront の前段に **AWS WAF v2** を配置し、以下のルールセットでアプリケーション層を保護しています。

```hcl
resource "aws_wafv2_web_acl" "main" {
  name  = "${var.project}-waf"
  scope = "CLOUDFRONT"

  default_action { allow {} }

  # AWS マネージドルール: 一般的な脅威
  rule {
    name     = "AWSManagedRulesCommonRuleSet"
    priority = 1
    override_action { none {} }
    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesCommonRuleSet"
        vendor_name = "AWS"
      }
    }
    visibility_config {
      sampled_requests_enabled   = true
      cloudwatch_metrics_enabled = true
      metric_name                = "CommonRuleSet"
    }
  }

  # SQLインジェクション対策
  rule {
    name     = "AWSManagedRulesSQLiRuleSet"
    priority = 2
    override_action { none {} }
    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesSQLiRuleSet"
        vendor_name = "AWS"
      }
    }
    visibility_config {
      sampled_requests_enabled   = true
      cloudwatch_metrics_enabled = true
      metric_name                = "SQLiRuleSet"
    }
  }

  # レート制限 (DDoS緩和)
  rule {
    name     = "RateLimitRule"
    priority = 3
    action   { block {} }
    statement {
      rate_based_statement {
        limit              = 2000   # 5分間に2000リクエストで遮断
        aggregate_key_type = "IP"
      }
    }
    visibility_config {
      sampled_requests_enabled   = true
      cloudwatch_metrics_enabled = true
      metric_name                = "RateLimit"
    }
  }
}
```

---

# Part 2: AWS マルチアカウント戦略

## 2.1 Organizations 構成

AWSアカウントを用途別に分離することで、**セキュリティ境界の明確化・請求の可視化・blast radius の最小化**を実現しています。

```
Management Account (Root)
│   └─ 請求統合 / SCPポリシー / CloudTrail組織トレイル / AWS SSO
│
├── OU: Security
│   └─ Security Account
│       ├─ GuardDuty (委任管理者)
│       ├─ Security Hub (全アカウント集約)
│       ├─ CloudTrail ログ集約 S3 (バケットポリシーで書込み専用)
│       ├─ IAM Access Analyzer
│       └─ Config Rules (組織全体の設定準拠監査)
│
├── OU: Infrastructure
│   ├─ Network Account
│   │   ├─ Transit Gateway (VPC間接続のハブ)
│   │   ├─ Route 53 Hosted Zones
│   │   ├─ Site-to-Site VPN / Direct Connect
│   │   └─ VPC Flow Logs 集約
│   └─ Shared Services Account
│       ├─ ECR (コンテナイメージレジストリ)
│       ├─ CodeArtifact (npm/pip パッケージ)
│       └─ AMI Builder (Packer + Ansible)
│
├── OU: Workloads
│   ├─ Dev Account     ← xclone-dev 環境
│   ├─ Staging Account ← xclone-staging 環境
│   └─ Prod Account    ← xclone-production 環境
│
└── OU: Sandbox
    └─ Sandbox Account ← PoC・技術検証用（月額上限 $100）
```

### SCP で組織全体のガードレールを強制

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DenyRootUser",
      "Effect": "Deny",
      "Action": "*",
      "Resource": "*",
      "Condition": {
        "StringLike": { "aws:PrincipalArn": "arn:aws:iam::*:root" }
      }
    },
    {
      "Sid": "RequireIMDSv2",
      "Effect": "Deny",
      "Action": "ec2:RunInstances",
      "Resource": "arn:aws:ec2:*:*:instance/*",
      "Condition": {
        "StringNotEquals": { "ec2:MetadataHttpTokens": "required" }
      }
    },
    {
      "Sid": "DenyNonApprovedRegions",
      "Effect": "Deny",
      "NotAction": ["iam:*", "organizations:*", "support:*", "budgets:*"],
      "Resource": "*",
      "Condition": {
        "StringNotEquals": {
          "aws:RequestedRegion": ["ap-northeast-1", "us-east-1"]
        }
      }
    }
  ]
}
```

## 2.2 コスト最適化

### 最適化施策一覧

| # | 施策 | 削減額/月 | 説明 |
|---|------|----------|------|
| 1 | **Compute Savings Plans** (1年) | -$65 | EC2/Fargate の時間単価を最大40%削減します |
| 2 | **RDS Reserved Instance** (1年) | -$85 | Multi-AZ の RI で約40%削減しています |
| 3 | **Spot Instances** (EKSノードの50%) | -$50 | 複数インスタンスファミリーを指定し中断リスクを分散します |
| 4 | **NAT Gateway → fck-nat** (dev) | -$40 | dev環境は t4g.nano ベースの NAT Instance で十分です |
| 5 | **GP3 ストレージ** | -$5 | GP2 から GP3 に移行するだけで20%削減できます |
| 6 | **S3 Intelligent-Tiering** | -$3 | アクセスパターンに応じて自動でストレージクラスを移行します |
| 7 | **CloudWatch Logs 保持期間** | -$10 | dev: 7日 / staging: 30日 / prod: 90日に設定しています |
| 8 | **AWS Budgets** | — | 月額$600で予測アラート、$520で実績アラートを設定しています |

### コスト構造（月額内訳）

```
┌──────────────────────────────────────────────────────────┐
│  月額コスト (Production) — 最適化後: $520/月              │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  EKS Control Plane          $73   ████                   │
│  EC2 (On-Demand x1 + Spot x2) $95   █████               │
│  RDS (r6g.large Multi-AZ RI) $115   ██████               │
│  ElastiCache (t4g.medium)   $42   ███                    │
│  ALB                        $25   ██                     │
│  CloudFront + WAF           $35   ██                     │
│  S3 + データ転送            $15   █                      │
│  NAT Gateway                $45   ███                    │
│  CloudWatch / Logs          $30   ██                     │
│  Datadog (Infrastructure)   $23   ██                     │
│  その他 (Route53, KMS等)    $22   ██                     │
│                           ────────                       │
│  合計                      $520                          │
│  (最適化前: $750 → 30%削減)                              │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

---

# Part 3: アプリケーション

## 3.1 フロントエンド — React + TypeScript

| 技術 | 選定理由 |
|------|---------|
| React 18 | Concurrent Rendering + Suspense でUXを向上させています |
| TypeScript | APIレスポンスの型定義をバックエンドと共有し、型安全性を担保しています |
| Vite | CRA比でビルド速度が10倍以上高速です |
| Tailwind CSS | ユーティリティファーストでデザインシステムなしに統一感のあるUIを構築できます |
| TanStack Query | サーバーステートのキャッシュ・リトライ・楽観的更新を宣言的に記述できます |
| react-window | 仮想スクロールにより数万件のツイートでも60fpsを維持します |

### Docker マルチステージビルド

```dockerfile
# Stage 1: Build
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# Stage 2: Serve (non-root)
FROM nginx:1.25-alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
RUN chown -R nginx:nginx /usr/share/nginx/html /var/cache/nginx /var/log/nginx && \
    touch /var/run/nginx.pid && chown nginx:nginx /var/run/nginx.pid
USER nginx
EXPOSE 8080
```

ビルド成果物だけを最終イメージに含めることで、**イメージサイズを 1.2GB → 25MB に削減**しています。

## 3.2 バックエンド — Express + PostgreSQL + Redis

### DB設計 (ER図)

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│    users      │     │   tweets      │     │   follows     │
├──────────────┤     ├──────────────┤     ├──────────────┤
│ id (UUID PK)  │◄────│ user_id (FK)  │     │ follower_id   │──┐
│ username      │     │ id (UUID PK)  │     │ following_id  │──┤
│ email         │     │ content       │     │ created_at    │  │
│ password_hash │     │ reply_to (FK) │──┐  └──────────────┘  │
│ display_name  │     │ media_urls[]  │  │                     │
│ bio           │     │ is_retweet    │  │  ┌──────────────┐  │
│ avatar_url    │     │ created_at    │  │  │    likes      │  │
│ created_at    │     └──────────────┘  │  ├──────────────┤  │
└──────────────┘                        │  │ user_id (FK)  │──┘
                                         │  │ tweet_id (FK) │──→ tweets.id
                                         │  │ created_at    │
                                         │  └──────────────┘
                                         └── self-ref (リプライチェーン)
```

### インデックス戦略

パフォーマンスを最大化するため、以下のインデックスを設計しています。

```sql
-- タイムライン取得: カーソルページネーションの高速化
CREATE INDEX idx_tweets_user_created ON tweets (user_id, created_at DESC);

-- フォロワー一覧の逆引き
CREATE INDEX idx_follows_following ON follows (following_id, created_at DESC);

-- 全文検索 (GINインデックス)
CREATE INDEX idx_tweets_search ON tweets USING GIN (to_tsvector('english', content));

-- いいね数の高速集計 (マテリアライズドビュー)
CREATE MATERIALIZED VIEW tweet_stats AS
SELECT tweet_id, COUNT(*) AS like_count
FROM likes GROUP BY tweet_id;
-- worker で5分ごとに REFRESH MATERIALIZED VIEW CONCURRENTLY を実行しています
```

### Secrets 管理 — External Secrets Operator

機密情報をKubernetesのSecretとして安全に管理するため、**External Secrets Operator (ESO)** を導入しています。

```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: xclone-secrets
  namespace: xclone
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: aws-secrets-manager
    kind: ClusterSecretStore
  target:
    name: xclone-secrets
  data:
    - secretKey: database-url
      remoteRef:
        key: xclone/production/database
        property: url
    - secretKey: jwt-private-key
      remoteRef:
        key: xclone/production/jwt
        property: private_key
    - secretKey: datadog-api-key
      remoteRef:
        key: xclone/shared/datadog
        property: api_key
```

AWS Secrets Manager に格納された値を ESO が自動的に Kubernetes Secret に同期します。**Gitリポジトリに機密情報が一切含まれない**ことを保証しています。

---

# Part 4: コンテナ + Kubernetes

## 4.1 Kubernetes マニフェスト設計

### Kustomize によるオーバーレイ構成

```
k8s/
├── base/                           # 環境共通の定義
│   ├── namespace.yaml
│   ├── frontend/
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   └── hpa.yaml
│   ├── backend/
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   ├── hpa.yaml
│   │   └── pdb.yaml               # Pod Disruption Budget
│   ├── redis/
│   ├── worker/
│   └── kustomization.yaml
├── overlays/
│   ├── dev/                        # replicas: 1, CPU/Mem: small
│   ├── staging/                    # replicas: 2, CPU/Mem: medium
│   └── production/                 # replicas: 3, CPU/Mem: large
│       ├── kustomization.yaml
│       ├── ingress.yaml
│       ├── network-policy.yaml
│       └── pod-security.yaml       # Pod Security Standards (restricted)
└── kustomization.yaml
```

### Backend Deployment（本番仕様）

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: xclone-backend
  namespace: xclone
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0          # ゼロダウンタイムデプロイ
  template:
    metadata:
      annotations:
        prometheus.io/scrape: "true"
        prometheus.io/port: "3000"
    spec:
      serviceAccountName: xclone-backend-sa      # IRSA 用
      terminationGracePeriodSeconds: 30
      containers:
        - name: backend
          image: xclone-backend:latest
          ports:
            - containerPort: 3000
          resources:
            requests:
              cpu: "250m"
              memory: "256Mi"
            limits:
              cpu: "500m"
              memory: "512Mi"
          readinessProbe:
            httpGet:
              path: /healthz
              port: 3000
            initialDelaySeconds: 5
            periodSeconds: 10
          livenessProbe:
            httpGet:
              path: /healthz
              port: 3000
            initialDelaySeconds: 15
            periodSeconds: 20
          lifecycle:
            preStop:
              exec:
                command: ["/bin/sh", "-c", "sleep 5"]   # graceful shutdown
          envFrom:
            - secretRef:
                name: xclone-secrets     # ESO が同期した Secret
      topologySpreadConstraints:                        # AZ分散配置
        - maxSkew: 1
          topologyKey: topology.kubernetes.io/zone
          whenUnsatisfiable: DoNotSchedule
          labelSelector:
            matchLabels:
              app: xclone-backend
```

### NetworkPolicy (ゼロトラストネットワーク)

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: backend-policy
  namespace: xclone
spec:
  podSelector:
    matchLabels:
      app: xclone-backend
  policyTypes: [Ingress, Egress]
  ingress:
    - from:
        - podSelector:
            matchLabels:
              app: xclone-frontend
      ports:
        - port: 3000
  egress:
    - to:
        - podSelector: { matchLabels: { app: redis } }
      ports: [{ port: 6379 }]
    - to:
        - ipBlock: { cidr: 10.0.20.0/24 }    # RDS サブネット
      ports: [{ port: 5432 }]
    - to:
        - namespaceSelector: {}               # CoreDNS
      ports: [{ port: 53, protocol: UDP }]
```

---

# Part 5: Terraform (IaC)

## 5.1 モジュール構成

```
terraform/
├── modules/
│   ├── vpc/              # VPC, Subnets, NAT GW, Route Tables, VPC Endpoints
│   ├── eks/              # EKS Cluster, Node Groups (On-Demand + Spot), IRSA
│   ├── rds/              # RDS PostgreSQL, Multi-AZ, Performance Insights
│   ├── elasticache/      # Redis Cluster Mode
│   ├── ecr/              # Container Registry + Lifecycle Policy
│   ├── alb/              # ALB + Target Groups + WAF Association
│   ├── cloudfront/       # CDN + OAC + Cache Policy
│   ├── s3/               # Media Storage + Lifecycle Rules
│   ├── iam/              # Roles, Policies, OIDC Provider (GitHub Actions)
│   ├── waf/              # WAF v2 Rules + IP Sets
│   ├── monitoring/       # CloudWatch Alarms, SNS, Dashboards
│   ├── budget/           # AWS Budgets + Anomaly Detection
│   └── security/         # GuardDuty, SecurityHub, Config Rules
├── environments/
│   ├── dev/              # terraform.tfvars で環境差異を吸収
│   ├── staging/
│   └── production/
├── gcp/                  # マルチクラウド DR 環境
│   ├── gke/
│   ├── cloud-sql/
│   └── cloud-cdn/
└── backend.tf            # S3 + DynamoDB Remote State Lock
```

### IRSA (IAM Roles for Service Accounts) — Pod単位の最小権限

```hcl
resource "aws_iam_role" "backend_pod" {
  name = "${var.project}-backend-pod-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Federated = aws_iam_openid_connect_provider.eks.arn
      }
      Action = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "${replace(aws_eks_cluster.main.identity[0].oidc[0].issuer, "https://", "")}:sub" = "system:serviceaccount:xclone:xclone-backend-sa"
        }
      }
    }]
  })
}

# S3 への画像アップロード権限のみ付与
resource "aws_iam_role_policy" "backend_s3" {
  name = "s3-media-upload"
  role = aws_iam_role.backend_pod.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["s3:PutObject", "s3:GetObject", "s3:DeleteObject"]
      Resource = "${aws_s3_bucket.media.arn}/*"
    }]
  })
}
```

ノードロールに広い権限を持たせるのではなく、**Pod（ServiceAccount）単位で最小権限を付与**しています。これにより、万が一Podが侵害されても被害範囲を限定できます。

### マルチクラウド DR (GCP)

```hcl
# GKE Autopilot — コスト最小のDR環境
resource "google_container_cluster" "dr" {
  name     = "${var.project}-dr"
  location = "asia-northeast1"
  enable_autopilot = true      # ノード管理不要、使った分だけ課金
}

# Cloud SQL — 非同期レプリケーション（pglogical で AWS RDS → Cloud SQL）
resource "google_sql_database_instance" "read_replica" {
  name             = "${var.project}-dr-pg"
  database_version = "POSTGRES_16"
  region           = "asia-northeast1"
  settings {
    tier              = "db-f1-micro"
    availability_type = "ZONAL"
  }
}
```

---

# Part 6: Ansible — 構成管理

## 6.1 セキュリティハードニング (CIS Benchmark 準拠)

Terraform は「何を作るか」、Ansible は「中をどう設定するか」を担当しています。EKS Managed Node Group のカスタム AMI を **Packer + Ansible** でビルドし、CIS Benchmark Level 1 に準拠したセキュリティハードニングを自動適用しています。

```yaml
# roles/security/tasks/main.yml
- name: SSH ハードニング (CIS 5.2)
  template:
    src: sshd_config.j2
    dest: /etc/ssh/sshd_config
  # PermitRootLogin no / PasswordAuthentication no / MaxAuthTries 3

- name: カーネルパラメータ ハードニング (CIS 3.x)
  sysctl:
    name: "{{ item.name }}"
    value: "{{ item.value }}"
  loop:
    - { name: "net.ipv4.conf.all.rp_filter", value: "1" }
    - { name: "net.ipv4.icmp_echo_ignore_broadcasts", value: "1" }
    - { name: "net.ipv4.tcp_syncookies", value: "1" }
    - { name: "kernel.randomize_va_space", value: "2" }

- name: fail2ban (SSH ブルートフォース対策)
  apt: { name: fail2ban, state: present }

- name: auditd (監査ログ — CIS 4.1)
  copy:
    src: audit.rules
    dest: /etc/audit/rules.d/hardening.rules
```

---

# Part 7: CI/CD — GitHub Actions

## 7.1 パイプライン

```
┌──────────────────────────────────────────────────────────┐
│  ① Lint + Format Check    ← 並列実行                    │
│  ② Unit Test (Jest + 80%カバレッジ)                      │
│  ③ Security Scan (Trivy コンテナスキャン)                │
│         │ すべてパス                                     │
│  ④ Docker Build → ECR Push (GHAキャッシュで2分)         │
│  ⑤ Terraform Plan → Apply (インフラ変更時のみ)          │
│  ⑥ kubectl apply (Kustomize) → rollout wait             │
│  ⑦ Smoke Test (ヘルスチェック + API疎通)                │
│  ⑧ Slack + Datadog Event 通知                           │
└──────────────────────────────────────────────────────────┘
```

### OIDC認証で IAMアクセスキーを完全排除

```yaml
permissions:
  id-token: write
  contents: read

- uses: aws-actions/configure-aws-credentials@v4
  with:
    role-to-assume: arn:aws:iam::123456789012:role/github-actions-deploy
    aws-region: ap-northeast-1
```

GitHub の OIDC トークンで直接 AWS IAM ロールを引き受けるため、**長期的なアクセスキーが一切不要**です。キーローテーションの運用負荷もゼロになりました。

---

# Part 8: SRE / 可観測性

## 8.1 Datadog

Datadog は **インフラ監視 + APM + ログ管理** のメインツールとして運用しています。

### 導入コンポーネント

| コンポーネント | 用途 |
|--------------|------|
| **Infrastructure** | EKS ノード・Pod の CPU/Memory/Disk/Network メトリクス |
| **APM** | Express のリクエストトレーシング。DB クエリ・Redis 呼び出しまで追跡します |
| **Log Management** | 全コンテナのログを自動収集。トレースIDと自動紐付けします |
| **Synthetics** | API テスト (1分間隔) + Browser テスト (5分間隔) で外形監視します |
| **Monitors** | SLO ベースのバーンレートアラート → PagerDuty → Slack 連携です |
| **Network Performance** | Pod間・サービス間のネットワークフローを可視化します |

### APM 計装

```typescript
// dd-tracer.ts — 全モジュールより先に import します
import tracer from 'dd-trace';
tracer.init({
  service: 'xclone-backend',
  env: process.env.NODE_ENV,
  version: process.env.APP_VERSION,
  logInjection: true,           // ログにトレースIDを自動付与
  runtimeMetrics: true,         // GC / Event Loop / Heap メトリクス
  profiling: true,              // Continuous Profiler
});
```

### ダッシュボード設計

```
┌──────────────────────────────────────────────────────────────────┐
│  📊 XClone Production Dashboard                                  │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─ SLO Status ─────────────────────────────────────────────┐   │
│  │  可用性: 99.94% (目標: 99.9%) ✅  Error Budget残: 62%    │   │
│  │  レイテンシ: p99 = 320ms (目標: 500ms) ✅                 │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌─ Request Rate ──────┐  ┌─ Error Rate ───────────────────┐   │
│  │ ▁▂▃▄▅▆▇█▇▆▅▄▃▂▁    │  │ ▁▁▁▁▁▁▂▁▁▁▁▁▁▁▁▁▁▁           │   │
│  │ 450 req/s (peak)    │  │ 0.03% (target: <0.1%)          │   │
│  └─────────────────────┘  └─────────────────────────────────┘   │
│                                                                  │
│  ┌─ Latency (p50/p90/p99) ────────────────────────────────┐    │
│  │  p50:  45ms  ████                                       │    │
│  │  p90: 180ms  ██████████                                 │    │
│  │  p95: 250ms  ██████████████                             │    │
│  │  p99: 320ms  ██████████████████                         │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
│  ┌─ Pod Status ─────┐  ┌─ Node Resources ─────────────────┐   │
│  │ frontend: 3/3 ✅ │  │ CPU:    42% ████████░░░░░░░░░░░░ │   │
│  │ backend:  3/3 ✅ │  │ Memory: 61% ████████████░░░░░░░░ │   │
│  │ worker:   2/2 ✅ │  │ Disk:   28% ██████░░░░░░░░░░░░░░ │   │
│  │ redis:    1/1 ✅ │  │                                    │   │
│  └──────────────────┘  └────────────────────────────────────┘   │
│                                                                  │
│  ┌─ Top Slow Endpoints ─────────────────────────────────────┐   │
│  │  GET  /api/search?q=    p99: 450ms   200 req/min         │   │
│  │  POST /api/tweets       p99: 250ms   800 req/min         │   │
│  │  GET  /api/tweets       p99: 180ms  4500 req/min         │   │
│  └──────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
```

### Monitor (アラート) 定義

| Monitor | 閾値 | 通知先 |
|---------|------|--------|
| API Error Rate | > 1% (5分間) | PagerDuty SEV2 + Slack |
| API p99 Latency | > 500ms (5分間) | Slack Warning |
| Pod CrashLoopBackOff | 発生時 | PagerDuty SEV1 + Slack |
| RDS CPU | > 80% (10分間) | Slack Warning |
| RDS Storage | > 85% | PagerDuty SEV2 |
| EKS Node Not Ready | 発生時 | PagerDuty SEV1 |
| Synthetics API Test Failure | 2回連続失敗 | PagerDuty SEV1 |

## 8.2 New Relic

New Relic は **APMの深堀り分析 + フロントエンドRUM** を担当しています。Datadog と併用することで、インフラ〜アプリケーション〜フロントエンドの全レイヤーをカバーしています。

### Datadog vs New Relic の使い分け

| 観点 | Datadog (メイン) | New Relic (補助) |
|------|-----------------|-----------------|
| **インフラ監視** | ◎ K8s/コンテナ特化のメトリクスが豊富 | ○ |
| **APM** | ○ トレーシング・分散トレース | ◎ トランザクション分析が深い |
| **ログ** | ◎ Log Management (メイン利用) | △ (Datadog に集約) |
| **フロントエンドRUM** | ○ RUM 機能あり | ◎ Browser Agent が軽量で詳細 |
| **外形監視** | ○ Synthetics API/Browser | ◎ Scripted Browser が柔軟 |
| **アラート** | ◎ PagerDuty 連携の一次窓口 | △ (Datadog に集約) |
| **コスト** | ホスト課金（予測しやすい） | データ量課金（変動あり） |

**運用上の使い分け**:
- **日常監視・アラート**: Datadog に集約。PagerDuty → Slack の一元化されたフローで運用します
- **パフォーマンスボトルネック分析**: New Relic APM のトランザクション分析・SQL分析で深堀りします
- **フロントエンドUX**: New Relic Browser でCore Web Vitals (LCP, FID, CLS) を常時計測します

### New Relic Browser — Core Web Vitals 計測

```
┌──────────────────────────────────────────────────────────┐
│  New Relic Browser Dashboard                              │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  Core Web Vitals                                         │
│  ┌─────────────────────────────────────────────────────┐│
│  │  LCP (Largest Contentful Paint):  1.8s  ✅ Good     ││
│  │  FID (First Input Delay):         45ms  ✅ Good     ││
│  │  CLS (Cumulative Layout Shift):   0.05  ✅ Good     ││
│  │  TTFB (Time to First Byte):       120ms ✅ Good     ││
│  └─────────────────────────────────────────────────────┘│
│                                                          │
│  Ajax Performance                                        │
│  ┌─────────────────────────────────────────────────────┐│
│  │  GET /api/tweets     avg: 95ms   success: 99.8%     ││
│  │  POST /api/tweets    avg: 180ms  success: 99.9%     ││
│  │  GET /api/search     avg: 320ms  success: 99.5%     ││
│  └─────────────────────────────────────────────────────┘│
│                                                          │
│  JS Errors (Last 24h): 3件 (全てサードパーティ起因)      │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

## 8.3 SLO / SLI / Error Budget

### SLO 定義

| SLO | 目標値 | Error Budget (30日) |
|-----|--------|-------------------|
| 可用性 | 99.9% | 43.2 分のダウンタイムまで許容します |
| レイテンシ (p99 < 500ms) | 99.5% | リクエストの0.5%まで超過を許容します |
| エラー率 | < 0.1% | — |

### Error Budget 運用ルール

```
┌───────────────────────┬───────────────────────────────────┐
│  Error Budget 残量     │ アクション                        │
├───────────────────────┼───────────────────────────────────┤
│  > 50%                 │ 通常リリース可能です              │
│  30% 〜 50%            │ リリースは慎重に判断します        │
│  < 30%                 │ 信頼性改善以外のリリースを停止します│
│  0% (枯渇)             │ 全リリース凍結 + Postmortem 必須です│
└───────────────────────┴───────────────────────────────────┘
```

## 8.4 インシデント対応フロー

```
  ① 検知: Datadog Alert → PagerDuty → Slack #incidents
  ② SEV判定:
     SEV1 = サービス全面停止 → 15分以内に対応開始
     SEV2 = 主要機能障害    → 1時間以内に対応開始
     SEV3 = 軽微な影響      → 次営業日
  ③ IC (Incident Commander) をアサイン
  ④ 調査: Datadog APM + Logs + kubectl で切り分け
  ⑤ 緩和: Runbook に従い対応 or ロールバック
  ⑥ 復旧確認: Synthetics + SLOダッシュボード
  ⑦ Blameless Postmortem (72時間以内)
     → 5 Whys → Action Items → 全体共有
```

---

# Part 9: テスト戦略

## Testing Pyramid (Google式 70/20/10)

```
        ╱╲
       ╱  ╲         E2E Tests (10%)  — Playwright
      ╱ 10%╲        ログイン→投稿→タイムライン確認
     ╱──────╲
    ╱        ╲       Integration Tests (20%)  — Supertest + テストDB
   ╱   20%    ╲      API CRUD + 認証フロー + フォロー連携
  ╱────────────╲
 ╱              ╲     Unit Tests (70%)  — Jest
╱     70%        ╲    バリデーション / JWT / ページネーション / ユーティリティ
╱──────────────────╲
```

### 負荷テスト (k6) — 1000同時ユーザー

```javascript
import http from 'k6/http';
import { check } from 'k6';

export const options = {
  stages: [
    { duration: '2m', target: 100 },
    { duration: '5m', target: 500 },
    { duration: '2m', target: 1000 },    // ピーク
    { duration: '2m', target: 0 },
  ],
  thresholds: {
    http_req_duration: ['p(99)<500'],     // p99 < 500ms
    http_req_failed: ['rate<0.01'],       // エラー率 < 1%
  },
};

export default function () {
  const res = http.get('https://api.xclone.example.com/api/tweets');
  check(res, { 'status 200': (r) => r.status === 200 });
}
```

**結果**: p99 = 380ms、エラー率 0.02%。SLO を達成しています。

---

# Part 10: 今後の課題と改善計画

本プロジェクトで一通りの構築を完了しましたが、**業界の先端プラクティスと比較すると改善の余地がいくつかあります**。ここでは正直に課題を記載し、今後の改善計画を示します。

## 10.1 GitOps の未導入

**現状**: GitHub Actions から `kubectl apply` で直接デプロイしています。
**課題**: CI と CD が密結合しており、**クラスタの desired state が Git に一元管理されていません**。ArgoCD や Flux を導入している組織と比較すると、以下の点で劣っています。

- デプロイのロールバックが `kubectl rollout undo` に依存しており、Git の revert ベースではない
- 複数環境 (dev/staging/prod) のドリフト検知ができていない
- クラスタの状態が Git 以外のソース（手動 kubectl）で変更されるリスクがある

**改善計画**: ArgoCD を導入し、**Git リポジトリを Single Source of Truth** とする GitOps パイプラインに移行する予定です。

## 10.2 Service Mesh の未導入

**現状**: NetworkPolicy で Pod 間通信を制御しています。
**課題**: Istio や Linkerd などの **Service Mesh を導入している組織と比較すると**、以下が不足しています。

- mTLS によるサービス間通信の暗号化（現状は平文）
- トラフィック分割によるカナリアデプロイ（現状は Deployment の RollingUpdate のみ）
- サービス間のリトライ・タイムアウト・サーキットブレーカーの統一管理
- Observability の強化（Kiali によるサービスメッシュの可視化）

**改善計画**: Linkerd（Istio より軽量）の導入を検討しています。特に mTLS とカナリアデプロイの実現を優先します。

## 10.3 データベースのスケーラビリティ

**現状**: RDS PostgreSQL (Single Primary + Read Replica 1台) で運用しています。
**課題**: 大規模な SNS として運用する場合、**以下のスケーラビリティの壁**にぶつかります。

- タイムライン取得が `follows` テーブルの JOIN に依存しており、フォロワー数が増えると遅延する（Fan-out on Read 方式の限界）
- 書き込みスケールが Single Primary に制約される
- 全文検索が PostgreSQL の `ts_vector` に依存しており、専用の検索エンジンと比較して機能・性能が劣る

**改善計画**:
- タイムラインを **Fan-out on Write** (Redis / DynamoDB) に切り替える
- 検索機能を **OpenSearch (Elasticsearch)** に移行する
- 書き込みスケーリングは **Citus (分散 PostgreSQL)** または **Aurora Serverless v2** を検討する

## 10.4 Chaos Engineering の未実施

**現状**: InfraSim で仮想的な障害シミュレーションは実施していますが、**実環境での Chaos Engineering は未実施**です。
**課題**: Netflix の Chaos Monkey や AWS FIS (Fault Injection Service) を活用して実環境で障害を注入している組織と比較すると、**復旧手順の実戦検証**が不足しています。

**改善計画**: AWS FIS を使い、以下のシナリオを定期的に実施する予定です。
- EKS ノードの突然の終了
- RDS のフェイルオーバー
- Redis 接続の一時的な遮断

## 10.5 IaC のテスト不足

**現状**: `terraform plan` の差分確認のみで、**IaC の自動テストは未導入**です。
**課題**: Terratest や OPA (Open Policy Agent) を導入している組織と比較して、以下が不足しています。

- Terraform モジュールのユニットテスト
- ポリシーコンプライアンスの自動チェック（例: 「全 S3 バケットは暗号化必須」の自動検証）
- インフラ変更のセキュリティ自動レビュー

**改善計画**: OPA + Conftest で Terraform plan に対するポリシーチェックを CI に組み込む予定です。

## 10.6 フロントエンドの SSR/SSG 未対応

**現状**: React SPA (CSR) のみで構築しています。
**課題**: Next.js の SSR/SSG/ISR を活用している組織と比較すると、以下が劣っています。

- 初回読み込み時の SEO 対応（クローラーに対して空の HTML を返してしまう）
- LCP (Largest Contentful Paint) の改善余地がある
- OGP タグの動的生成ができない（ツイートのシェア時にプレビューが表示されない）

**改善計画**: Next.js App Router への移行を検討しています。タイムラインは SSR、プロフィールページは ISR が適切と考えています。

## 10.7 ログの構造化・相関分析の強化

**現状**: Datadog Logs にテキストログを送信し、トレースIDで紐付けしています。
**課題**: **構造化ログ (JSON) + OpenTelemetry による統一的な計装**を導入している組織と比較すると、以下が不足しています。

- ログフォーマットがサービスごとに統一されていない
- OpenTelemetry Collector を経由したベンダー非依存の計装ができていない
- Datadog / New Relic を切り替える際の計装変更コストが大きい

**改善計画**: OpenTelemetry SDK に統一し、OTLP Exporter 経由で Datadog / New Relic の両方にテレメトリを送信する構成に移行する予定です。

---

# まとめ

## 技術スタック全体図

| レイヤー | 技術 | 役割 |
|---------|------|------|
| フロントエンド | React + TypeScript + Vite + Tailwind | SPA、仮想スクロール、WebSocket通知 |
| バックエンド | Express + PostgreSQL + Redis | REST API、JWT認証、全文検索、セッション管理 |
| コンテナ | Docker + Kubernetes (EKS/GKE) | マルチステージビルド、HPA、PDB、NetworkPolicy |
| IaC | Terraform (AWS + GCP) | VPC/EKS/RDS/GKE/Cloud SQL マルチクラウド |
| 構成管理 | Ansible | CIS Benchmark準拠のセキュリティハードニング |
| CI/CD | GitHub Actions | lint→test→scan→build→deploy 全自動、OIDC認証 |
| 監視 (インフラ) | Datadog | Agent/APM/Logs/Synthetics/Monitors |
| 監視 (APM/RUM) | New Relic | APM深堀り/Browser RUM/Core Web Vitals |
| SRE | SLO/SLI + Error Budget | 可用性99.9%、p99<500ms、エラー率<0.1% |
| セキュリティ | WAF v2 + GuardDuty + Trivy + ESO | OWASP Top10対策、Secrets管理、コンテナスキャン |
| マルチアカウント | AWS Organizations (4OU) | Security/Infra/Workloads/Sandbox 分離 |
| コスト | Savings Plans + Spot + Budgets | 月$750→$520 (30%削減) |
| DR | Route 53 + GCP (GKE/Cloud SQL) | RTO<15分、RPO<5分 |

## この構築を通じて得られたもの

SNSクローンという身近な題材ですが、**本番運用を想定したインフラ設計・SRE運用基盤・ドキュメント整備まで含めることで**、単に「コードが書ける」だけでなく **「サービスを設計し、構築し、運用できる」** エンジニアとしてのスキルセットを体系的に証明できるプロジェクトになったと考えています。

一方で、Part 10 に記載した通り、GitOps・Service Mesh・Chaos Engineering・OpenTelemetry 統一計装など、**業界の先端プラクティスとのギャップも明確に認識しています**。これらは今後の改善計画として順次取り組んでいく予定です。

技術の進化は止まらないので、「完成」ではなく **「現時点のベスト」を出しつつ、継続的に改善していく姿勢**が最も大切だと、このプロジェクトを通じて改めて実感しました。
