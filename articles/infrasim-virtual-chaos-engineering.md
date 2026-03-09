---
title: "実インフラに触れずに障害シミュレーション！仮想カオスエンジニアリングツール InfraSim を作った"
emoji: "🔥"
type: "tech"
topics: ["chaosengineering", "python", "infrastructure", "sre", "devops"]
published: true
---

## TL;DR

**InfraSim** は、実インフラに一切触れずにカオスエンジニアリングを実行できるPython製OSSツールです。インフラの依存関係グラフをモデル化し、150以上のカオスシナリオを自動生成して障害の連鎖的影響を可視化します。

https://github.com/mattyopon/infrasim

## なぜ作ったのか

### カオスエンジニアリングの課題

Netflix の Chaos Monkey に代表されるカオスエンジニアリングツールは、実際のインフラに障害を注入してシステムの耐障害性を検証します。しかし、これには大きな壁があります。

- **本番に障害を注入する恐怖** - Blast Radius を完全にコントロールできない
- **ステージング環境との差異** - ステージングで問題なくても本番で発生する障害がある
- **準備コストが高い** - 実行環境のセットアップ、安全装置の構築が必要
- **事前に「何が起きるか」が分からない** - 実行してみないと影響範囲が不明

### 「実行前に知りたい」というニーズ

クラウドインフラエンジニアとして8年間働く中で感じたのは、**障害シナリオを「実行前」に分析できるツールがない**ということでした。

Gremlin や Litmus は優れたツールですが、実際に障害を注入します。securiCAD はセキュリティ攻撃パスをモデル化しますが、インフラ障害の連鎖は対象外です。

**「仮想的に」カオスエンジニアリングを実行し、事前にリスクを定量化する** - このコンセプトで InfraSim を作りました。

## InfraSim の仕組み

### アーキテクチャ

```
Discovery Layer       Model Layer          Simulator Layer
┌──────────────┐   ┌──────────────┐    ┌──────────────────┐
│ Local Scan    │   │ InfraGraph   │    │ 30カテゴリ       │
│ Prometheus    │──>│ Components   │──> │ カオスシナリオ    │
│ Terraform     │   │ Dependencies │    │ カスケードエンジン│
│ YAML          │   │ NetworkX     │    │ リスクスコア      │
└──────────────┘   └──────────────┘    └──────────────────┘
```

4ステップで動作します：

1. **Discovery** - インフラの構成情報を取得（Terraform / Prometheus / ローカルスキャン / YAML定義）
2. **Model** - 依存関係グラフとしてモデル化（NetworkXの有向グラフ）
3. **Simulate** - 150+のカオスシナリオを自動生成・実行
4. **Report** - リスクスコア付きのレポート出力（CLI / HTML / Web Dashboard）

### 依存関係グラフ

InfraSim の核心は**依存関係グラフ**です。コンポーネント間の関係を3種類に分類します：

| 依存タイプ | 障害伝播 | 例 |
|-----------|---------|-----|
| `requires` | 依存先DOWN → 自身もDOWN | App → DB |
| `optional` | 依存先DOWN → DEGRADEDに劣化 | App → Cache |
| `async` | 依存先DOWN → 遅延DEGRADED | App → Queue |

これにより、**「DBが落ちたら何が連鎖的に壊れるか」**を正確に予測できます。

## 使い方

### 最も簡単な方法（デモ）

```bash
pip install -e .
infrasim demo
```

6コンポーネントのWebアプリケーションスタック（nginx → App Server x2 → PostgreSQL / Redis / RabbitMQ）で150シナリオを実行します。

### YAML でインフラを定義

```yaml
components:
  - id: nginx
    type: load_balancer
    port: 443
    replicas: 2
    metrics: { cpu_percent: 25, memory_percent: 30 }
    capacity: { max_connections: 10000 }

  - id: api
    type: app_server
    port: 8080
    metrics: { cpu_percent: 65, memory_percent: 70 }
    capacity: { max_connections: 500, connection_pool_size: 100 }

  - id: postgres
    type: database
    port: 5432
    metrics: { cpu_percent: 45, memory_percent: 80, disk_percent: 72 }
    capacity: { max_connections: 100 }

dependencies:
  - source: nginx
    target: api
    type: requires
  - source: api
    target: postgres
    type: requires
```

```bash
infrasim load infra.yaml
infrasim simulate --html report.html
```

### Terraform から自動インポート

```bash
# stateファイルから
infrasim tf-import --state terraform.tfstate

# terraform plan の影響分析
terraform plan -out=plan.out
infrasim tf-plan plan.out --html plan-report.html
```

AWS / GCP / Azure の50以上のリソースタイプを自動認識し、依存関係も推定します。

## カオスシナリオ 30カテゴリ

InfraSim は以下の30カテゴリから自動でシナリオを生成します：

### 単一障害

- コンポーネント停止、CPU飽和、メモリ枯渇（OOM）、ディスクフル
- 接続プール枯渇、ネットワーク分断、レイテンシスパイク

### 複合障害

- **ペア障害**: 全 C(n,2) 組の同時停止
- **トリプル障害**: 全 C(n,3) 組の同時停止
- コンポーネント停止 + トラフィックスパイク

### インフラ種別特化

- **DB**: ログ爆発、レプリケーション遅延、接続嵐、ロック競合
- **Cache**: キャッシュスタンピード、エビクション嵐、スプリットブレイン
- **Queue**: バックプレッシャー、ポイズンメッセージ
- **LB**: ヘルスチェック失敗、TLS証明書期限切れ、設定リロード失敗
- **App**: メモリリーク、スレッド枯渇、GCポーズ、不良デプロイ

### 大規模障害

- ゾーン障害、カスケードタイムアウト連鎖、全インフラ崩壊
- ブラックフライデーシミュレーション（10x トラフィック + キャッシュ圧力）

## リスクスコアリング

スコアは **0.0〜10.0** の範囲で3つの要素から算出されます：

```
severity = impact × spread × likelihood

impact   = DOWN数×1.0 + OVERLOADED数×0.5 + DEGRADED数×0.25
spread   = 影響コンポーネント数 / 全コンポーネント数
likelihood = 現在のメトリクスに基づく発生確率 (0.2〜1.0)
```

### Likelihood（発生確率）の算出

単なる「起きたらどうなるか」ではなく、**「今の状態からどれくらい起きやすいか」**も評価します。

| シナリオ | ディスク使用90%超 | ディスク使用50%未満 |
|---------|-----------------|------------------|
| ディスクフル | likelihood=1.0（切迫） | likelihood=0.2（低い） |

これにより、ディスク使用率20%のサーバーの「ディスクフル」シナリオは自動的にリスクスコアが低くなります。

## セキュリティニュースフィード連携

InfraSim のユニークな機能として、**セキュリティニュースからカオスシナリオを自動生成**する仕組みがあります。

```bash
infrasim feed-update
```

8つのセキュリティニュースフィード（CISA、NIST NVD、The Hacker News、BleepingComputer、AWS Security、GCP Status、Krebs on Security、Ars Technica）からRSS/Atomを取得し、18種類のインシデントパターン（DDoS、ランサムウェア、メモリリーク、TLS証明書期限切れ等）にマッチングしてカオスシナリオに変換します。

次回の `infrasim simulate` 実行時に自動でマージされます。

## 既存ツールとの比較

| 特徴 | InfraSim | Gremlin | Chaos Monkey | Litmus |
|------|---------|---------|------|------|
| 実インフラへの影響 | **なし（完全仮想）** | あり | あり | あり |
| セットアップ | pip install | エージェント | AWS統合 | K8s必須 |
| 事前リスク分析 | **可能** | 不可 | 不可 | 不可 |
| ニュースフィード連携 | **あり** | なし | なし | なし |
| Terraform連携 | **あり** | なし | なし | なし |
| コスト | 無料（OSS） | 有料SaaS | 無料 | 無料 |

## 今後の展望

- AWS CloudWatch / Datadog からのメトリクス自動取得
- Kubernetes マニフェストからの自動インポート
- CI/CD パイプライン統合（terraform plan 時の自動リスク分析）
- 障害シナリオのカスタム定義 API
- 時系列シミュレーション（障害の時間的進行を可視化）

## まとめ

InfraSim は **「カオスエンジニアリングを安全に、事前に」** 実行するためのツールです。

- 実インフラに一切触れない
- 150以上のシナリオを自動生成
- リスクを定量的に評価
- セキュリティニュースから最新脅威を自動反映

ぜひ試してフィードバックをいただけると嬉しいです。

https://github.com/mattyopon/infrasim
