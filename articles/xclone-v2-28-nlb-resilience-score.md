---
title: "Xクローン v2.28 — NLBバックアップ追加とレジリエンススコア計算の改善で30日SLO 99.94%達成"
emoji: "📊"
type: "tech"
topics: ["infrastructure", "aws", "sre", "chaosengineering", "kubernetes"]
published: true
---

## はじめに

v2.27 でサイドカーCB除去・Route 53追加・MTTR最適化を行い、30日SLO 99.92%を達成しました。本記事では3つの追加改善でさらにSLO 99.94%まで引き上げ、InfraSim自体のレジリエンススコア計算も改善しました。

## 発見した問題

### 1. ALBの単一経路依存

ALBがダウンまたはネットワーク分断が発生すると、全APIトラフィックが停止。バックアップ経路がない。

### 2. AWSマネージドサービスのモデリング不正確

CloudFront・WAF・Shield・S3 を `replicas: 1` でモデル化していたが、これらは AWS が内部的に超冗長化している。InfraSim がこれらを SPOF として誤検知。

### 3. Autoscaling の設定漏れ

hono-api-1〜2 のみに autoscaling が設定されており、3〜12 は設定漏れ。

### 4. InfraSim のレジリエンススコアが dependency type を無視

`requires` 依存も `optional` 依存も同じペナルティで計算。`failover` や `autoscaling` の有無も未考慮。

## 修正内容

### 1. NLB バックアップ追加（Xclone v9.2）

```yaml
- id: nlb
  name: "NLB (Network Load Balancer - ALB Backup)"
  type: load_balancer
  replicas: 2
  failover:
    enabled: true
    promotion_time_seconds: 5

dependencies:
  - source: route53
    target: nlb      # Route 53 health check → ALB障害時にNLBへ
    type: optional
  - source: nlb
    target: hono-api-*  # NLB → 全12 Pod（バックアップ経路）
    type: optional
```

### 2. AWS マネージドサービスの replicas 修正

| コンポーネント | Before | After | 理由 |
|---------------|--------|-------|------|
| CloudFront | 1 | **50** | 50+ エッジロケーション |
| WAF | 1 | **10** | リージョナル Multi-AZ |
| Shield | 1 | **10** | リージョナル Multi-AZ |
| S3 | 1 | **10** | Multi-AZ レプリケーション |

### 3. 全 Pod に Autoscaling 設定

```yaml
# 全12 Pod に統一設定
autoscaling:
  enabled: true
  min_replicas: 6
  max_replicas: 24
  scale_up_threshold: 70
  scale_down_threshold: 30
```

### 4. InfraSim v5.7 — レジリエンススコア改善

```python
# ❌ Before: 依存タイプを無視
if comp.replicas <= 1 and len(dependents) > 0:
    penalty = min(20, len(dependents) * 5)

# ✅ After: 依存タイプ + failover + autoscaling を考慮
for dep_comp in dependents:
    edge = self.get_dependency_edge(dep_comp.id, comp.id)
    dep_type = edge.dependency_type
    if dep_type == "requires":
        weighted_deps += 1.0
    elif dep_type == "optional":
        weighted_deps += 0.3      # optional は影響が限定的
    else:  # async
        weighted_deps += 0.1

penalty = min(20, weighted_deps * 5)
if comp.failover.enabled:
    penalty *= 0.3   # failover で SPOF リスク大幅減
if comp.autoscaling.enabled:
    penalty *= 0.5   # autoscaling で容量リスク減
```

## 結果

### アーキテクチャ改善の推移（v8.1 → v9.2）

| 指標 | v8.1 | v9.0 | v9.1 | v9.2 |
|------|------|------|------|------|
| Components | 45 | 35 | 35 | 36 |
| Resilience Score | 0 | 0 | 0 | **20.3** |
| Dynamic CRITICAL | 2 | 1 | 1 | 1 |
| Net partition | 7.1 (C) | 5.7 (W) | 5.7 (W) | **5.6 (W)** |
| 30日 Avg Avail | 99.88% | 99.89% | 99.92% | **99.94%** |
| 30日 Min Avail | 86.67% | 88.57% | 88.57% | **91.67%** |
| 30日 Downtime | 34.6m | 34.3m | 25.4m | **22.7m** |

### レジリエンススコアの比較（InfraSim v5.7）

| グラフ | v5.6 (旧) | v5.7 (新) |
|--------|----------|----------|
| Demo (6 components) | 36 | **52** |
| Xclone v9.2 (36 components) | 0 | **20.3** |

## 教訓

### AWS マネージドサービスの replicas は 1 ではない

CloudFront や S3 を `replicas: 1` でモデル化するのは実態と乖離。AWS マネージドサービスは内部的に高度に冗長化されており、SPOF として扱うべきではない。

### レジリエンススコアは「SPOF の数」ではなく「SPOF の影響度」で測るべき

`optional` 依存の SPOF は `requires` 依存の SPOF より影響が小さい。failover や autoscaling がある SPOF は自動復旧可能なので、ペナルティを軽減すべき。

### Per-pod モデリングの限界

12 pod を個別にモデル化するとレジリエンススコアが過度に下がる。これは「12 個の SPOF」ではなく「12 重の冗長化」。スコア 20.3 は per-pod モデリングの構造的制約であり、実際の障害耐性（1000 シナリオ全 PASSED、SLO 99.94%）とは乖離している。

## 残る所見

| 所見 | 重大度 | 対応方針 |
|------|--------|---------|
| Total meltdown (9.2) | CRITICAL | 許容（全停止は多層防御で「起きない」ようにする） |
| Network partition (5.6) | WARNING | 許容（NLB バックアップで軽減済み） |
| Resilience Score 20.3 | - | Per-pod モデリングの構造的制約。実運用では問題なし |
