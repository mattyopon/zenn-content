---
title: "ChaosProof v1.2.0 — 特許分析から生まれた5つの新機能：コスト影響・モンテカルロ・5層モデル"
emoji: "🔬"
type: "tech"
topics: ["python", "sre", "chaosengineering", "oss", "simulation"]
published: false
---

## はじめに

ChaosProof の特許性を分析する過程で、競合ツール（Gremlin, Steadybit, AWS FIS）に対する差別化ポイントとして5つの新機能を特定・実装しました。

## 新機能一覧

### 1. Cost Impact Engine（コスト影響エンジン）

障害シナリオごとのビジネス損失を金額で可視化。

```bash
chaosproof cost infra.yaml --top 10
```

| 算出項目 | 計算式 |
|---------|--------|
| ビジネス損失 | revenue_per_minute × downtime_minutes |
| SLA違反ペナルティ | sla_credit_percent × 月間売上 |
| 復旧コスト | engineer_cost × MTTR × 要員数 |
| **年間リスク** | Σ(impact × 年間発生確率) |

### 2. Monte Carlo シミュレーション

MTBF/MTTR に確率分布を適用し、可用性の統計分布を算出。

```bash
chaosproof monte-carlo infra.yaml -n 10000 --json
```

出力: p50/p95/p99 可用性、95%信頼区間、年間ダウンタイム分布

### 3. 5層可用性モデル（Layer 4/5 追加）

| 層 | 名称 | 計算 |
|---|------|------|
| Layer 1 | Software | deploy × downtime + human_error |
| Layer 2 | Hardware | MTBF/(MTBF+MTTR)^replicas |
| Layer 3 | Theoretical | Layer2 × (1 - packet_loss) |
| **Layer 4** | **Operational** | **1 - (incidents × response_time / 8760h)** |
| **Layer 5** | **External SLA** | **Π(provider_sla[i])** |

### 4. Resilience Score v2

5カテゴリの詳細スコア + 改善推奨事項:

| カテゴリ | 0-20点 | 評価基準 |
|---------|--------|---------|
| Redundancy | replicas + failover | Active-Active = 20 |
| CB Coverage | CB設定率 | 100% = 20 |
| Auto-Recovery | autoscaling/failover率 | 100% = 20 |
| Dependency Risk | チェーン深度 + requires SPOF | 浅い = 20 |
| Capacity Headroom | 平均利用率 | <50% = 20 |

### 5. Plugin System 拡張

```python
class EnginePlugin(Protocol):
    def simulate(self, graph, scenarios) -> dict: ...

class ReporterPlugin(Protocol):
    def generate(self, graph, results) -> str: ...

class DiscoveryPlugin(Protocol):
    def discover(self, config) -> InfraGraph: ...
```

## テスト

**1132/1132 PASSED**（v1.1.0 の 1070 から +62）

| 新テスト | 件数 |
|---------|------|
| Cost Engine | 15 |
| Monte Carlo | 15 |
| 5-Layer Model | 13 |
| Resilience Score v2 | 19 |
