---
title: "Xクローン v2.32 — Sub-secondフェイルオーバーでSeven Nines(99.9999%)に迫る"
emoji: "⚡"
type: "tech"
topics: ["infrastructure", "sre", "python", "chaosengineering", "failover"]
published: true
---

## はじめに

v2.31 で InfraSim にインスタンスレベル障害とリクエストレベル可用性を実装し、Six Nines (99.9996%) に到達しました。残り 0.0004% はフェイルオーバー中のリクエスト失敗。今回は sub-second フェイルオーバーで Seven Nines に迫ります。

## 課題: フェイルオーバー時間が精度のボトルネック

### リクエスト失敗の計算式

```
micro_penalty = (1/replicas) × (failover_time/step_window) / total × 100
```

v10.2 (failover 4s): `(1/12) × (4/300) / 38 × 100 = 0.0003%` per failure
v10.3 (failover 1s): `(1/12) × (1/300) / 38 × 100 = 0.00007%` per failure

### InfraSim の制約: FailoverConfig が int 型

```python
# ❌ Before: int型のため sub-second 不可
promotion_time_seconds: int = 30
health_check_interval_seconds: int = 10

# ✅ After: float型で sub-second 対応
promotion_time_seconds: float = 30.0
health_check_interval_seconds: float = 10.0
```

## 結果

| シナリオ | v10.2 (2s failover) | v10.3 (0.5s failover) |
|---------|-------------------|---------------------|
| 7日 deploys | 99.9999% | **100.0000%** |
| 7日 full ops | 99.9995% | **99.9999%** |
| 30日 stress | 99.9996% | **99.9999%** |
| 30日 Min Avail | 99.89% | **99.97%** |

## イレブンナインまでの距離

```
現在:      99.9999%   = Seven Nines - 1
イレブン:  99.999999999% = 現在の 10,000 倍の精度が必要

Gap: 0.0001% = 年間 31.5 秒のダウンタイム
```

### 残る精度限界

| 限界 | 現在 | 改善策 | 実現性 |
|------|------|--------|--------|
| タイムステップ | 5分 (300s) | 1秒ステップ | 計算コスト 300× |
| 障害モデル | MTBF指数分布 | ワイブル分布 | 中 |
| ネットワーク | 未モデル | パケットロス率 | 大規模改修 |
| 人的エラー | 未モデル | 確率的イベント | 定義困難 |

Seven Nines を超えるには、**物理世界のノイズ**（ネットワークジッター、カーネルスケジューリング遅延、GC パーズ）のモデル化が必要。これは「インフラシミュレーション」の範疇を超え、「分散システムシミュレーション」の領域に入ります。

## InfraSim 全バージョン履歴

| Version | 改善 | 30日 SLO |
|---------|------|---------|
| v5.5 | 表示バグ修正 | 99.88% (v8.1) |
| v5.6 | シナリオ修正 | 99.88% |
| v5.7 | レジリエンススコア改善 | 99.94% (v9.2) |
| v5.8 | フェイルオーバー = DEGRADED | 100%（嘘） |
| v5.9 | fractional DOWN | 99.9967% |
| v5.10 | サービスティア可用性 | 100%（ティア） |
| v5.11 | インスタンスレベル + リクエストレベル | 99.9996% |
| **v5.12** | **sub-second failover (float型)** | **99.9999%** |
