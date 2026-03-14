---
title: "ChaosProof改善ループ#4 — Over-provisioned ゼロ到達＋HA/クォーラム対応Capacity Engine"
emoji: "🏁"
type: "tech"
topics: ["chaosproof", "chaosengineering", "sre", "aws", "infrastructure"]
published: true
---

## TL;DR

5回目のイテレーションで、Xクローン（38コンポーネント）の **over-provisioned が 10→0 に完全解消**。ChaosProof（旧InfraSim）に HA最小レプリカガード、クラスタクォーラムガード、シナリオ上限2,000への引き上げの3つの新機能を追加し、Capacity Engine の偽陽性を排除しました。

https://github.com/mattyopon/infrasim

> 注: InfraSim は商標上の理由により **ChaosProof** にリネーム予定です。

## 改善ループの全体像

```
Iteration 0: NEEDS ATTENTION — meltdown severity 9.0
Iteration 1: ACCEPTABLE — WARNING 1件（partition 5.3）
Iteration 2: HEALTHY到達 — 全シナリオ PASSED
Iteration 3: 収束確認 — LOW課題の微改善
Iteration 4（本記事）: 完全収束 — over-provisioned 0、全指標最適化
```

## 前回の残存課題

| # | 課題 | 深刻度 |
|---|------|--------|
| 1 | 10コンポーネント over-provisioned (-8.8%) | LOW |
| 2 | 247シナリオが未テスト（1,000上限で切り捨て） | LOW |
| 3 | ALB/NLBに「1レプリカ推奨」の偽陽性 | **ツール問題** |

---

## 改善1: HA最小レプリカガード

### 問題

Capacity Engine は utilization ベースで `recommended_replicas` を算出しますが、**HA（高可用性）要件を考慮していません**でした。

```
RIGHT-SIZE: alb (load_balancer) → 2 → 1 replicas  ← 偽陽性！
RIGHT-SIZE: nlb (load_balancer) → 2 → 1 replicas  ← 偽陽性！
RIGHT-SIZE: shield (load_balancer) → 2 → 1 replicas  ← 偽陽性！
```

ALB/NLB/Shield を1レプリカにすると SPOF になり、耐障害性が崩壊します。

### 改善内容

```python
# capacity_engine.py — _build_forecasts()
ha_min = 1
is_ha = (
    comp.failover.enabled
    or comp.type.value in ("load_balancer", "dns")
)
if is_ha:
    ha_min = 2  # HA コンポーネントは最低2レプリカ

rec_3m = max(ha_min, self._replicas_needed(...))
```

**対象:** failover が有効なコンポーネント、load_balancer 型、dns 型

---

## 改善2: クラスタクォーラムガード

### 問題

Redis Cluster（3レプリカ）と local-cache（3レプリカ）に「2レプリカ推奨」が出力されていました。

```
RIGHT-SIZE: redis-cluster (cache) → 3 → 2 replicas  ← 偽陽性！
RIGHT-SIZE: local-cache (cache) → 3 → 2 replicas  ← 偽陽性！
```

Redis Cluster は3ノード以上でクォーラムを形成し、Kafka は3ブローカー以上でパーティション冗長性を確保します。2ノードへの削減はスプリットブレインのリスクがあります。

### 改善内容

```python
# capacity_engine.py — _build_forecasts()
# 3レプリカ以上のcache/queueはクォーラム維持のため最低3
if comp.type.value in ("cache", "queue") and comp.replicas >= 3:
    ha_min = max(ha_min, 3)
```

**結果:** cache/queue 型の偽陽性が解消

---

## 改善3: シナリオ上限 1,000 → 2,000

### 問題

xclone は1,247シナリオを生成しますが、`MAX_SCENARIOS = 1000` で247シナリオが未テストでした。

```
WARNING: Scenario count 1247 exceeds limit, truncating to 1000
```

### 改善内容

```python
# engine.py
MAX_SCENARIOS = 2000  # 1000 → 2000
```

**結果:** 1,247シナリオすべてがテスト対象に（切り捨てゼロ）

---

## 改善4: xclone 最終 Right-Size

HAガード・クォーラムガードにより「本当に削減可能」なコンポーネントが明確になったため、安全なもののみ削減:

| コンポーネント | Before | After | 根拠 |
|---------------|--------|-------|------|
| Route 53 | 3 | 2 | DNS型 → HAガードで最低2、これが最適 |
| CloudFront | 5 | 2 | LB型 → HAガードで最低2、2で十分 |
| WAF | 3 | 2 | LB型 → HAガードで最低2 |
| WebSocket | 5 | 4 | app_server型、推奨は4 |

**削減しなかったもの:**
- ALB/NLB: 既に2（HAガード最低値）
- Shield: 既に2（HAガード最低値）
- Redis Cluster/Local Cache: 既に3（クォーラム最低値）

---

## 最終評価結果

```json
{
  "static": {
    "resilience_score": 100.0,
    "total_scenarios": 1247,
    "critical": 0, "warning": 0, "passed": 1247
  },
  "dynamic": {
    "total_scenarios": 1288,
    "critical": 0, "warning": 0, "passed": 1288,
    "worst_scenario": "Network partition: App <-> DB",
    "worst_severity": 2.6
  },
  "ops": {
    "avg_availability": 99.9805,
    "total_downtime_seconds": 0.0
  },
  "capacity": {
    "over_provisioned_count": 0,
    "cost_reduction_percent": 6.9
  },
  "verdict": "HEALTHY"
}
```

### 全イテレーション推移

| 指標 | Iter 0 | Iter 1 | Iter 2 | Iter 3 | Iter 4 |
|------|--------|--------|--------|--------|--------|
| Verdict | NEEDS ATTN | ACCEPTABLE | HEALTHY | HEALTHY | **HEALTHY** |
| Dynamic Critical | 1 | 0 | 0 | 0 | **0** |
| Dynamic Warning | 1 | 1 | 0 | 0 | **0** |
| Dynamic Worst | 9.0 | 5.3 | 3.2 | 2.6 | **2.6** |
| Static テスト | 1,000 | 1,000 | 1,000 | 1,000 | **1,247** |
| Over-provisioned | 11 | 11 | 11 | 10 | **0** |
| Cost | -26.8% | -26.8% | -17.7% | -8.8% | **+6.9%** |
| Tests | 1,013 | 1,034 | 1,036 | 1,056 | **1,070** |

---

## 収束判定

| # | 項目 | 状態 |
|---|------|------|
| Dynamic Critical | 0 | 完了 |
| Dynamic Warning | 0 | 完了 |
| Over-provisioned | **0** | **完了（今回解消）** |
| Static 切り捨て | **0** | **完了（今回解消）** |
| Ops劣化 3件/7日 | 正常範囲 | 改善不要 |
| Cost | +6.9%（成長バッファ） | 最適 |

**全定量指標がゼロまたは最適値に到達。改善ループは完全に収束しました。**

---

## 学んだこと

### 1. Capacity Engine は「レプリカ数学」だけでは不十分

utilization × growth_rate でレプリカ数を計算するのは正しいですが、**HA 制約**（最低2台）と**クォーラム制約**（最低3台）を無視すると偽陽性を生みます。「コスト最適」と「耐障害性最適」は異なる目的関数です。

### 2. 偽陽性はツールの信頼性を損なう

「ALBを1台にしろ」という推奨は、ユーザーがツールを信用しなくなる原因になります。HA/クォーラムガードは単なる機能追加ではなく、**ツールの信頼性に直結する品質改善**です。

### 3. シナリオ切り捨ては「テストしていない」と同義

1,247シナリオ中247が未テストだったのは、テストカバレッジが80%の CI パイプラインと同じです。上限引き上げにより**100%シナリオカバレッジ**を実現しました。

### 4. Over-provisioned ゼロは「完成」ではなく「出発点」

over-provisioned が 0 になったのは「現在の利用率に対して最適」という意味であり、トラフィック成長に備えた +6.9% のバッファは健全です。Cost が 0% ではなく +6.9% であることが、過剰削減していない証拠です。

---

## まとめ

ChaosProof（旧InfraSim）の改善ループを5回繰り返し、すべての定量指標を最適値に到達させました。

**ChaosProof 新機能（Iteration 4）:**
- HA最小レプリカガード（failover/LB/DNS → 最低2）
- クラスタクォーラムガード（cache/queue → 最低3）
- シナリオ上限 1,000 → 2,000（切り捨てゼロ）

**xclone 最終Right-Size（Iteration 4）:**
- Route53/CloudFront/WAF/WebSocket を最適値に削減
- Over-provisioned 10 → 0

**品質:**
- 1,070テスト、2,535シナリオ（static 1,247 + dynamic 1,288）すべてPASSED
- 5イテレーションで NEEDS ATTENTION → HEALTHY → 完全収束

https://github.com/mattyopon/infrasim
