---
title: "Xクローン v2.27 — サイドカー12個を除去してネットワーク分断をCRITICALからWARNINGに改善"
emoji: "🏗️"
type: "tech"
topics: ["infrastructure", "chaosengineering", "kubernetes", "sre", "aws"]
published: false
---

## はじめに

InfraSim v5.6 で全コードバグをゼロにした後、**Xclone インフラアーキテクチャ自体**に改善の余地があるか検証しました。結果、3つの構造的問題を発見し、v9.0 で修正しました。

## 発見した問題

### 1. サイドカー CB の過剰モデリング（最大の問題）

12個の Envoy サイドカー CB を**個別コンポーネント**（replicas=1）としてモデル化していたため：

- InfraSim が 12個の SPOF として認識
- ネットワーク分断時に障害連鎖が増幅（sidecar → downstream の追加ホップ）
- コンポーネント数が 45 に膨張（本来 33 で十分）

```yaml
# ❌ Before: サイドカーを個別コンポーネントとしてモデル化
components:
  - id: cb-sidecar-1     # replicas: 1 → SPOF扱い
  - id: cb-sidecar-2     # replicas: 1 → SPOF扱い
  # ...x12

dependencies:
  - source: hono-api-1   # Pod → Sidecar (requires)
    target: cb-sidecar-1
  - source: cb-sidecar-1  # Sidecar → PgBouncer (with CB)
    target: pgbouncer
```

**サイドカーは Pod と同一ライフサイクル**。独立したインフラコンポーネントではなく、依存エッジの CB 設定として表現すべきです。

### 2. DNS レジリエンス未対応

Route 53 がモデルに含まれておらず、DNS 障害 = 全停止の SPOF が存在。

### 3. Kafka Dead Letter Queue なし

CDC パイプライン（Debezium → Kafka → OpenSearch）で処理失敗したメッセージの退避先がなく、データ消失リスクあり。

## 修正内容（v8.1 → v9.0）

### 1. サイドカー CB を依存エッジに折り込み

```yaml
# ✅ After: CB設定を依存エッジに直接記述
dependencies:
  - source: hono-api-1    # Pod → PgBouncer (CB + retry をエッジに)
    target: pgbouncer
    type: optional
    weight: 0.7
    circuit_breaker:
      enabled: true
      failure_threshold: 3
      recovery_timeout_seconds: 15
    retry_strategy:
      enabled: true
      max_retries: 2
      initial_delay_ms: 50
      max_delay_ms: 2000
      multiplier: 2.0
      jitter: true
```

Python スクリプトで 12 sidecar コンポーネント + 全関連依存を自動変換。CB 設定は全て保持。

### 2. Route 53 追加

```yaml
- id: route53
  name: "Route 53 (DNS Health Check + Failover)"
  type: dns
  replicas: 4  # AWS managed, multi-AZ
  capacity:
    max_connections: 10000000
    max_rps: 50000000

dependencies:
  - source: route53
    target: cloudfront
    type: requires
```

### 3. Kafka DLQ 追加

```yaml
- id: kafka-dlq
  name: "Kafka Dead Letter Queue"
  type: queue
  replicas: 3

dependencies:
  - source: kafka
    target: kafka-dlq
    type: optional
  - source: opensearch
    target: kafka-dlq
    type: optional
```

## 結果比較

### 構造

| 指標 | v8.1 | v9.0 | 変化 |
|------|------|------|------|
| コンポーネント | 45 | 35 | **-22%** |
| 依存関係 | 165 | 157 | -5% |
| 不要なホップ | 12 (Pod→Sidecar) | 0 | **除去** |

### 動的シミュレーション（1,695 → 1,129 シナリオ）

| シナリオ | v8.1 | v9.0 | 変化 |
|---------|------|------|------|
| Total meltdown | 9.2 (CRITICAL) | 8.9 (CRITICAL) | -0.3 |
| Network partition LB↔App | **7.1 (CRITICAL)** | **5.7 (WARNING)** | **改善** |
| Rolling restart | 4.0 (WARNING) | - | 解消 |
| CRITICAL 合計 | 2 | 1 | **-50%** |

### 運用シミュレーション

| シナリオ | v8.1 Avg | v9.0 Avg | v8.1 Failures | v9.0 Failures |
|---------|---------|---------|---------------|---------------|
| 7日 deploys | 99.98% | **99.99%** | 0 | 0 |
| 7日 full ops | 99.90% | **99.93%** | 3 | **0** |
| 14日 growth | 99.89% | **99.92%** | 4 | **2** |
| 30日 stress | 99.88% | **99.89%** | 17 | **15** |

## 教訓

### サイドカーはインフラコンポーネントではない

サービスメッシュのサイドカー（Envoy、Linkerd-proxy 等）は Pod と同一ライフサイクルで動作するため、**独立したインフラコンポーネントとしてモデル化すべきではない**。代わりに：

- **CB 設定**: 依存エッジの `circuit_breaker` フィールドに記述
- **リトライ**: 依存エッジの `retry_strategy` フィールドに記述
- **メトリクス**: Pod のメトリクスに含める

これにより：
- モデルがシンプルになる（45→35 コンポーネント）
- 偽の SPOF が除去される
- 障害連鎖の深さが浅くなる（1ホップ削減）

### DNS は見えない SPOF

Route 53 のような「当たり前すぎて忘れる」コンポーネントこそモデルに含めるべき。DNS 障害は全サービスに波及する。

## 残課題

| 課題 | 現状 | 目標 |
|------|------|------|
| 30日ストレス SLO | 99.89% | 99.9%（あと 0.01%） |
| Total meltdown | 8.9 (CRITICAL) | 対策困難（全停止は本質的に CRITICAL） |

次回は 30日ストレステストの SLO 99.9% 達成に取り組みます。
