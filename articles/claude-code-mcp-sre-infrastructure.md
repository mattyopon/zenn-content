---
title: "Claude Code × MCPで「インフラを自然言語で操作」する ― SREが実戦投入した5つのMCPサーバー構成"
emoji: "🔌"
type: "tech"
topics: ["claudecode", "mcp", "sre", "aws", "terraform"]
published: true
---

## TL;DR

Claude CodeにMCP（Model Context Protocol）サーバーを接続すると、「S3バケットの設定確認して」「Terraformのplanを実行して」「Grafanaのダッシュボードからエラー率を取得して」が自然言語で実行できるようになる。SREとして8年インフラを運用してきた経験から、本番環境で実際に使っている5つのMCPサーバー構成と、**安全に運用するための権限設計**を共有する。

## なぜMCPがSREの仕事を変えるのか

### 従来のSREワークフロー

```
障害発生
  → CloudWatch確認（ブラウザでAWSコンソール）
  → ログ確認（ターミナルで aws logs tail）
  → 原因特定（複数タブ行き来）
  → 修正（Terraform変更 → plan → apply）
  → Slack報告（コピペ）
  → ポストモーテム作成（Confluence）

所要時間: 30分〜2時間
コンテキストスイッチ: 6回以上
```

### MCP導入後のワークフロー

```
障害発生
  → Claude Code: 「prod環境のエラー率が上がってるから原因を調べて」
    → [MCP: AWS] CloudWatchメトリクスを取得
    → [MCP: AWS] CloudWatch Logsからエラーログを検索
    → [MCP: Terraform] 直近のインフラ変更を確認
    → [MCP: Grafana] ダッシュボードからレイテンシ推移を取得
    → 原因を特定して報告
  → Claude Code: 「修正のTerraformコードを書いてplanして」
    → [MCP: Terraform] plan実行 → 差分表示
  → Claude Code: 「Slackのincidentチャンネルに報告して」
    → [MCP: Slack] インシデント報告を投稿

所要時間: 5〜15分
コンテキストスイッチ: 0回
```

**コンテキストスイッチがゼロになる**のが最大の価値。ターミナル1画面で完結する。

## 全体アーキテクチャ

```
┌──────────────────────────────────────────────────────────────┐
│  Claude Code                                                  │
│  ┌──────────────────────────────────────────────────────┐    │
│  │  MCP Client（組み込み）                               │    │
│  │                                                        │    │
│  │  ┌─────────┐ ┌──────────┐ ┌──────────┐              │    │
│  │  │ AWS MCP │ │Terraform │ │ Grafana  │              │    │
│  │  │ Server  │ │MCP Server│ │MCP Server│              │    │
│  │  └────┬────┘ └────┬─────┘ └────┬─────┘              │    │
│  │       │           │            │                      │    │
│  │  ┌────┴────┐ ┌────┴─────┐ ┌───┴──────┐              │    │
│  │  │ GitHub  │ │  Slack   │ │ Custom   │              │    │
│  │  │MCP Srv  │ │MCP Server│ │ Runbook  │              │    │
│  │  └────┬────┘ └────┬─────┘ └────┬─────┘              │    │
│  └───────┼───────────┼────────────┼──────────────────────┘    │
│          │           │            │                            │
└──────────┼───────────┼────────────┼────────────────────────────┘
           │           │            │
    ┌──────▼──────┐ ┌──▼────┐ ┌────▼──────────┐
    │ AWS API     │ │Slack  │ │ Grafana API   │
    │ Terraform   │ │API    │ │ Prometheus    │
    │ GitHub API  │ │       │ │               │
    └─────────────┘ └───────┘ └───────────────┘
```

## MCPサーバーの設定（.claude/settings.json）

まず全体の設定ファイル。Claude Codeの `~/.claude/settings.json` にMCPサーバーを登録する。

```json
{
  "mcpServers": {
    "aws-knowledge": {
      "command": "uvx",
      "args": ["awslabs.aws-documentation-mcp-server@latest"],
      "env": {
        "AWS_PROFILE": "sre-readonly",
        "AWS_REGION": "ap-northeast-1"
      }
    },
    "aws-pricing": {
      "command": "uvx",
      "args": ["awslabs.cost-analysis-mcp-server@latest"],
      "env": {
        "AWS_PROFILE": "sre-readonly"
      }
    },
    "terraform": {
      "command": "npx",
      "args": ["-y", "@anthropic/terraform-mcp-server"],
      "env": {
        "TF_WORKSPACE": "production",
        "TF_VAR_FILE": "/infra/envs/prod/terraform.tfvars"
      }
    },
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "${GITHUB_TOKEN}"
      }
    },
    "slack": {
      "command": "npx",
      "args": ["-y", "@anthropic/slack-mcp-server"],
      "env": {
        "SLACK_BOT_TOKEN": "${SLACK_BOT_TOKEN}"
      }
    }
  }
}
```

## MCP Server 1: AWS（ドキュメント + コスト分析）

SREにとって最も使用頻度が高い。AWS公式のMCPサーバーが2つ提供されている。

### aws-documentation-mcp-server

AWSの公式ドキュメントを検索・参照できる。「このIAMポリシーのベストプラクティスは？」「ECSのタスク定義でメモリ制限はどう設定する？」といった質問にドキュメントベースで回答してくれる。

```bash
# インストール
pip install awslabs.aws-documentation-mcp-server

# 使い方（Claude Codeから自然言語で）
# 「ECS Fargateのタスク定義でephemeral storageの上限は？」
# → MCPがAWSドキュメントを検索して回答
```

### cost-analysis-mcp-server

リアルタイムのAWS料金データを取得できる。インフラ設計時の「これいくらかかる？」に即答できるのが強い。

```bash
# 使い方
# 「t3.mediumとt3.largeの月額料金を東京リージョンで比較して」
# → MCPがAWS Pricing APIを叩いてリアルタイム料金を返す

# 「現在のprod環境のECS Fargateの月額コストを見積もって」
# → タスク数、CPU/Memory設定から自動計算
```

### 実際の活用例：障害調査

```
私: 「prod環境のALBで5xxエラーが急増してる。原因を調べて」

Claude Code (MCP経由):
  1. [AWS MCP] CloudWatch GetMetricData → ALBの5xx率を時系列取得
  2. [AWS MCP] CloudWatch Logs Insights → エラーログを検索
  3. [AWS MCP] ECS DescribeServices → タスク数とデプロイ状態を確認
  4. 分析結果:
     「10:23にECSデプロイが走り、新バージョンのヘルスチェックが
      失敗しています。タスクが起動→失敗→再起動を繰り返しており、
      ALBのターゲットが不安定です。
      推奨: デプロイをロールバックしてください。」
```

従来なら CloudWatch → ECS → ALB と3つの画面を行き来して15分かかる調査が、**1コマンド30秒**で完了する。

## MCP Server 2: Terraform

インフラ変更の plan/apply をClaude Codeから実行できる。ただし**applyは絶対にMCP経由で自動実行しない**設計にしている。

```json
{
  "terraform": {
    "command": "npx",
    "args": ["-y", "@anthropic/terraform-mcp-server"],
    "env": {
      "TF_WORKSPACE": "production",
      "ALLOWED_COMMANDS": "init,plan,validate,fmt,show,state list",
      "BLOCKED_COMMANDS": "apply,destroy,import"
    }
  }
}
```

**`ALLOWED_COMMANDS` で plan までに制限し、apply/destroy をブロックしている。** これが最も重要な権限設計。

### 活用例：Terraform plan の自動レビュー

```
私: 「modules/ecs/main.tf の変更をplanして、セキュリティ的に問題ないか確認して」

Claude Code:
  1. [Terraform MCP] terraform validate → 構文チェック OK
  2. [Terraform MCP] terraform plan → 差分を取得
  3. [自身の分析] plan出力を解析:
     「以下の変更が検出されました:
      + aws_security_group_rule.allow_all (ingress 0.0.0.0/0:8080)

      ⚠️ セキュリティ警告:
      ポート8080が全世界に開放されます。
      これは内部APIポートのため、VPC内部からのアクセスに
      制限することを推奨します。

      修正案:
      cidr_blocks = ["10.0.0.0/8"] に変更してください。」
```

planの実行だけでなく、**出力の意味を解釈してセキュリティリスクを指摘してくれる**のがMCPとClaude Codeの組み合わせの真価。

## MCP Server 3: Grafana / Prometheus

監視ダッシュボードのデータをClaude Codeから直接取得する。

```json
{
  "grafana": {
    "command": "npx",
    "args": ["-y", "@anthropic/grafana-mcp-server"],
    "env": {
      "GRAFANA_URL": "https://grafana.internal.example.com",
      "GRAFANA_API_KEY": "${GRAFANA_API_KEY}",
      "ALLOWED_DATASOURCES": "prometheus,cloudwatch",
      "READONLY": "true"
    }
  }
}
```

### 活用例：SLO/SLI の定期レポート

```
私: 「今週のSLO達成状況をまとめて」

Claude Code:
  1. [Grafana MCP] PromQLクエリ実行:
     - 可用性: sum(rate(http_requests_total{code!~"5.."}[7d]))
               / sum(rate(http_requests_total[7d]))
     - レイテンシ p99: histogram_quantile(0.99,
               sum(rate(http_request_duration_seconds_bucket[7d])) by (le))
     - エラー率: sum(rate(http_requests_total{code=~"5.."}[7d]))
               / sum(rate(http_requests_total[7d]))

  2. 分析結果:
     「今週のSLO達成状況:
      ✅ 可用性: 99.95% (SLO: 99.9%) — Error Budget残り: 72%
      ✅ レイテンシ p99: 320ms (SLO: 500ms) — 余裕あり
      ⚠️ エラー率: 0.08% (SLO: 0.1%) — Error Budget残り: 20%

      注意: エラー率がSLOに接近しています。
      水曜日のデプロイ以降、/api/payments のエラーが増加傾向です。
      原因調査を推奨します。」
```

SREの週次レポート作成が**自動化**される。PromQLを覚えていなくても自然言語で聞ける。

## MCP Server 4: GitHub（PR/Issue管理）

```json
{
  "github": {
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-github"],
    "env": {
      "GITHUB_PERSONAL_ACCESS_TOKEN": "${GITHUB_TOKEN}"
    }
  }
}
```

### 活用例：インシデント対応のPR作成

```
私: 「さっきのECSロールバック対応をhotfix PRとして作って」

Claude Code:
  1. git checkout -b hotfix/ecs-rollback-20260311
  2. [修正コードを自動生成]
  3. git commit
  4. [GitHub MCP] PR作成:
     - title: "hotfix: ECSタスク定義のヘルスチェックパス修正"
     - body: インシデント概要、原因、修正内容、テスト結果
     - labels: ["hotfix", "production"]
     - reviewers: ["sre-team"]
```

## MCP Server 5: Slack（インシデント通知）

```json
{
  "slack": {
    "command": "npx",
    "args": ["-y", "@anthropic/slack-mcp-server"],
    "env": {
      "SLACK_BOT_TOKEN": "${SLACK_BOT_TOKEN}",
      "ALLOWED_CHANNELS": "incident,sre-alerts,dev-general",
      "BLOCKED_ACTIONS": "delete_message,admin"
    }
  }
}
```

`ALLOWED_CHANNELS` で投稿先を制限し、`BLOCKED_ACTIONS` で削除や管理操作をブロックしている。

### 活用例：インシデント報告の自動生成

```
私: 「今回の障害対応をincidentチャンネルにポストモーテム形式で報告して」

Claude Code:
  [Slack MCP] #incident に投稿:

  🔴 インシデントレポート: ALB 5xx エラー急増

  ■ タイムライン
  10:23 - ECSデプロイ開始（v2.3.1 → v2.3.2）
  10:25 - ALB 5xxエラー率が0.1%→15%に急増
  10:28 - オンコール担当に自動アラート
  10:32 - 原因特定（ヘルスチェックパスの設定ミス）
  10:35 - v2.3.1にロールバック完了
  10:37 - エラー率が0.1%に回復

  ■ 原因
  タスク定義のヘルスチェックパスが /health → /healthz に
  変更されたが、アプリケーション側は /health のまま

  ■ 再発防止
  - ヘルスチェックパスをCI/CDパイプラインで自動検証する
  - デプロイ時のカナリアリリース比率を10%に変更する

  ■ 対応時間: 12分
```

## 権限設計：MCPを安全に使うための3原則

MCPは便利だが、**何も制限せずに使うと事故になる**。以下の3原則を守っている。

### 原則1: Read-Only First（読み取り専用から始める）

```
┌─────────────────────────────────────────────────┐
│  権限レベル                                       │
│                                                   │
│  Level 0: Read-Only（デフォルト）                 │
│    AWS: describe*, get*, list* のみ              │
│    Terraform: plan, validate, show のみ          │
│    Grafana: query, dashboard 参照のみ            │
│    GitHub: read, list のみ                       │
│    Slack: channels:read のみ                     │
│                                                   │
│  Level 1: Write-Limited（承認制）                 │
│    AWS: 特定リソースへの変更のみ                 │
│    Terraform: plan まで（applyは手動）           │
│    GitHub: PR作成、Issue作成                     │
│    Slack: 特定チャンネルへの投稿                 │
│                                                   │
│  Level 2: Full Access（使わない）                 │
│    本番環境でのフルアクセスは付与しない          │
│                                                   │
└─────────────────────────────────────────────────┘
```

### 原則2: IAMポリシーで最小権限を強制する

MCPサーバーが使うAWS IAMロールを専用に作り、最小権限に絞る。

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "MCPReadOnly",
      "Effect": "Allow",
      "Action": [
        "cloudwatch:GetMetricData",
        "cloudwatch:DescribeAlarms",
        "logs:FilterLogEvents",
        "logs:GetLogEvents",
        "ecs:DescribeServices",
        "ecs:DescribeTasks",
        "ecs:ListTasks",
        "s3:GetBucketPolicy",
        "s3:GetBucketAcl",
        "ec2:DescribeSecurityGroups",
        "ec2:DescribeInstances",
        "iam:GetPolicy",
        "iam:GetRole"
      ],
      "Resource": "*"
    },
    {
      "Sid": "DenyDangerous",
      "Effect": "Deny",
      "Action": [
        "iam:CreateUser",
        "iam:CreateRole",
        "iam:AttachRolePolicy",
        "iam:PutRolePolicy",
        "s3:DeleteBucket",
        "s3:PutBucketPolicy",
        "ec2:AuthorizeSecurityGroupIngress",
        "rds:DeleteDBInstance",
        "ecs:DeleteService"
      ],
      "Resource": "*"
    }
  ]
}
```

**Deny文を明示的に書く**のがポイント。Allow漏れがあってもDenyで確実にブロックする。

### 原則3: CLAUDE.mdでMCP操作のルールを明示する

```markdown
# CLAUDE.md - MCP操作ルール

## MCP経由の操作ルール
- AWS: 参照系（describe, get, list）は自由に実行してよい
- AWS: 変更系はユーザーの明示的な承認なしに実行しない
- Terraform: plan/validate/fmt は自由に実行してよい
- Terraform: apply/destroy は絶対に実行しない
- Slack: incident, sre-alerts チャンネルへの投稿はユーザー確認後
- GitHub: PR作成はdraft状態で作成し、レビュー後にready for reviewにする
```

## 導入後の効果

2ヶ月運用した結果：

| 指標 | MCP導入前 | MCP導入後 |
|------|----------|----------|
| 障害の初動調査時間 | 15〜30分 | 3〜5分 |
| コンテキストスイッチ回数 | 6回以上/インシデント | 0回 |
| 週次SLOレポート作成 | 1時間 | 5分（自動生成） |
| Terraform plan レビュー | 10分/PR | 2分（自動分析付き） |
| インシデント報告書作成 | 30分 | 5分（自動生成） |

**特に障害対応の初動が劇的に速くなった**。CloudWatch→ログ→ECS→ALBと複数サービスを横断する調査が、Claude Codeへの一言で完結する。

## ハマったポイント

### 1. MCPサーバーの起動が遅い

`npx` で毎回ダウンロードすると起動に10秒以上かかる。グローバルインストールで解決した。

```bash
# npx（遅い: 毎回ダウンロード）
"command": "npx", "args": ["-y", "@anthropic/terraform-mcp-server"]

# グローバルインストール（速い: ローカルから起動）
npm install -g @anthropic/terraform-mcp-server
"command": "terraform-mcp-server"
```

### 2. AWS認証情報の受け渡し

MCPサーバーは別プロセスで起動するので、Claude Code本体のAWS認証情報が引き継がれない。`AWS_PROFILE` を環境変数で明示的に渡す必要がある。

```json
{
  "env": {
    "AWS_PROFILE": "sre-readonly",
    "AWS_REGION": "ap-northeast-1",
    "AWS_CONFIG_FILE": "/home/user/.aws/config",
    "AWS_SHARED_CREDENTIALS_FILE": "/home/user/.aws/credentials"
  }
}
```

### 3. MCP経由のTerraform applyを絶対に許可してはいけない

テスト中に「planの結果を見て問題なければapplyして」と指示したら、Claude Codeが本当にapplyしようとした。MCPサーバー側で `BLOCKED_COMMANDS` を設定していたから止まったが、**設定していなかったら本番に適用されていた**。

教訓：**MCPサーバーの設定で物理的にブロックする。CLAUDE.mdだけに頼らない。**

### 4. Slackの投稿先を制限しないと事故る

制限なしだと、Claude Codeがテスト投稿を `#general` に送ってしまう。`ALLOWED_CHANNELS` で投稿可能チャンネルを明示的にホワイトリストにすること。

### 5. Grafana APIキーの権限

Grafana APIキーにViewer以上の権限を付けると、ダッシュボードの変更や削除が可能になってしまう。**Viewer権限で十分**。データの参照だけできればいい。

## 既存セキュリティガードレールとの統合

[前回の記事](https://zenn.dev/yutaro2076145/articles/claude-code-security-guardrails-sre)で紹介した5層セキュリティガードレールと、MCPの権限設計を組み合わせると以下のようになる：

```
┌─────────────────────────────────────────────────┐
│  Layer 1: CLAUDE.md（MCP操作ルール追記）        │
│  Layer 2: STRIDE（MCP経由のデータフロー分析）   │
│  Layer 3: AI Code Review（MCP操作の監査ログ）   │
│  Layer 4: OWASP（MCP認証情報の管理）            │
│  Layer 5: Infra Guard（MCP IAMポリシー監査）    │
│                                                   │
│  + MCP権限設計                                    │
│    ├─ IAMポリシー（最小権限 + Deny明示）        │
│    ├─ ALLOWED/BLOCKED_COMMANDS                    │
│    ├─ ALLOWED_CHANNELS                            │
│    └─ Read-Only First 原則                       │
└─────────────────────────────────────────────────┘
```

**MCPを追加しても、既存のガードレールが全て有効**に機能する。多層防御の設計が正しく活きている。

## まとめ

- **MCP接続でClaude Codeがインフラツールを直接操作できる**（AWS, Terraform, Grafana, GitHub, Slack）
- **コンテキストスイッチがゼロになる**のが最大の価値。障害対応の初動が3-5分に短縮
- **権限設計が最重要**：Read-Only First、IAM最小権限、BLOCKED_COMMANDS で物理的にブロック
- **CLAUDE.mdだけに頼らない**。MCPサーバーの設定レベルで危険な操作をブロックする
- 既存のセキュリティガードレール（5層防御）と**併用可能**。多層防御が正しく機能する

**MCPは「AIにインフラを任せる」ためのツールではない。「AIにインフラの情報を素早く取得させ、人間の判断を加速させる」ためのツールだ。**

---

**関連記事:**
- [Claude Codeに本番環境を触らせる前に ― SRE視点で構築した5層セキュリティガードレール](https://zenn.dev/yutaro2076145/articles/claude-code-security-guardrails-sre)
- [Claude Codeで24ロール・10フェーズのAI開発チームを自動編成する](https://zenn.dev/yutaro2076145/articles/claude-agent-team-gafam-enterprise)
