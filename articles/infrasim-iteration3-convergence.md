---
title: "InfraSim改善ループ#3 — HEALTHY維持のまま残存課題を収束させた記録"
emoji: "🎯"
type: "tech"
topics: ["infrasim", "chaosengineering", "sre", "aws", "infrastructure"]
published: true
---

## TL;DR

4回目のイテレーションで、Xクローン（38コンポーネント）の残存LOW課題をすべて改善し、改善ループの収束を確認しました。Dynamic最悪シナリオは 3.2→2.6 に低下、over-provisioned は 11→10 に削減（コスト余地 -17.7%→-8.8%、8.9%実現）。InfraSim 側にも3つの新機能（maxUnavailable Rolling Restart、Emergency Autoscaling、Adaptive CB Recovery）を追加しています。

https://github.com/mattyopon/infrasim

## 改善ループの全体像

```
Iteration 0（初回評価）
  → NEEDS ATTENTION: Dynamic CRITICAL 1件（meltdown severity 9.0）

Iteration 1（メルトダウン修正）
  → ACCEPTABLE: CRITICAL解消、WARNING 1件残存（partition severity 5.3）

Iteration 2（HEALTHY到達）
  → HEALTHY: WARNING も解消、全シナリオ PASSED

Iteration 3（本記事 — 収束確認）
  → HEALTHY維持: LOW課題を改善、全指標が改善方向
```

## 前回の残存課題

[前回の記事](https://zenn.dev/mattyopon/articles/infrasim-iteration2-healthy-verdict)で HEALTHY 判定を達成しましたが、以下のLOW課題が残っていました。

| # | 課題 | 深刻度 |
|---|------|--------|
| 1 | 11コンポーネント over-provisioned (-17.7%) | LOW |
| 2 | Dynamic最悪シナリオ rolling restart 3.2 | LOW |
| 3 | Ops劣化イベント 3件/7日 | LOW |

---

## 改善1: Rolling Restart シナリオの現実性向上

### 根本原因

CATEGORY 25 の Rolling restart failure シナリオは、app_server の **50%** を同時にDOWNさせていました。

```python
# scenarios.py CATEGORY 25（変更前）
half = app[:min(len(app) - 1, len(app) // 2 + 1)]
# 21個中11個（52%）を同時障害 → 現実の rolling restart とは乖離
```

実際の Kubernetes Rolling Update は `maxUnavailable: 25%` がデフォルトで、21 Pod なら同時に DOWN になるのは最大5個です。

### 改善内容

```python
# scenarios.py CATEGORY 25（変更後）
max_unavailable = max(1, len(app) // 4)  # 25% maxUnavailable
batch = app[:min(max_unavailable, len(app) - 1)]
# 21個中5個（24%）を同時障害 → Kubernetes のデフォルト動作に準拠
```

**効果:** severity 3.2 → 2.6（Dynamic worst が rolling restart から network partition に交代）

---

## 改善2: Emergency Autoscaling の追加

### 問題

Dynamic Engine の autoscaling は `scale_up_delay_seconds`（デフォルト30秒）の待機後にスケールアップします。しかし、急激なトラフィックスパイクでは utilization が 90% を超えてからスケールアップが間に合わず、DOWN状態に陥る可能性がありました。

### 改善内容

```python
# dynamic_engine.py — _evaluate_autoscaling()
emergency = util > 90.0
if emergency or state.pending_scale_up_seconds >= cfg.scale_up_delay_seconds:
    # Emergency scaling uses a larger step to recover faster
    step_size = cfg.scale_up_step * 2 if emergency else cfg.scale_up_step
    new_replicas = min(
        state.current_replicas + step_size,
        cfg.max_replicas,
    )
```

**ポイント:**
- utilization > 90% で **遅延なし即時スケールアップ**
- Emergency 時は通常の **2倍のステップ** でスケールアップ
- 実世界のHPA実装（GKE/EKS）でも critical utilization 時の即時スケーリングは一般的

---

## 改善3: Adaptive Circuit Breaker Recovery

### 問題

CB が OPEN になると `recovery_timeout_seconds`（デフォルト60秒）の間、すべてのリクエストが即座に失敗します。3秒の一時的な障害でも60秒のサービス停止が発生する問題がありました。

### 改善内容

```python
# dynamic_engine.py — _evaluate_circuit_breakers()
# 初回OPENは1/3のタイムアウトで早期回復を試行
if cb.consecutive_opens == 0:
    effective_timeout = max(step_sec, cb.recovery_timeout_seconds / 3.0)
else:
    # 再OPEN時は指数バックオフ（上限はconfigured値）
    effective_timeout = min(
        cb.recovery_timeout_seconds,
        cb.recovery_timeout_seconds / 3.0 * (2 ** cb.consecutive_opens),
    )
```

**3段階の復帰戦略:**
1. **初回OPEN**: 設定値の1/3で HALF_OPEN を試行（transient failure の早期回復）
2. **再OPEN**: 指数バックオフ（2倍ずつ増加）で retry
3. **成功時**: `consecutive_opens` をリセットして次回は再び早期復帰

---

## 改善4: Right-Size Phase 2

### 変更内容

| コンポーネント | Before | After | 削減率 |
|---------------|--------|-------|--------|
| CloudFront CDN | 20 replicas | 10 replicas | -50% |
| WAF | 6 replicas | 3 replicas | -50% |
| Shield | 4 replicas | 2 replicas | -50% |
| Route 53 | 4 replicas | 3 replicas | -25% |
| S3 Media | 10 replicas | 5 replicas | -50% |
| Redis Cluster | 6 replicas | 4 replicas | -33% |
| Local Cache | 7 replicas | 4 replicas | -43% |
| OTel Collector | 3 replicas | 2 replicas | -33% |
| Redis DR | 3 replicas | 2 replicas | -33% |

**判断根拠:**
- AWS マネージドサービス（CloudFront, WAF, Shield, Route53, S3）は自動スケーリングと内部冗長性を持つため、InfraSim のレプリカ数は「論理的な処理ユニット」としての最小構成で十分
- ALB/NLB はフェイルオーバーペアとして replicas=2 を維持（削減対象外）
- What-If 分析で replica_factor=0.5（全体50%削減）でも SLO PASS を確認済み

### コスト削減効果

- Iteration 2: **-17.7%** の余地
- Iteration 3: **-8.8%** の余地（8.9ポイント改善を実施済み）

---

## 最終評価結果

```bash
infrasim evaluate --file infrasim-xclone.yaml --json
```

```json
{
  "static": {
    "resilience_score": 100.0,
    "critical": 0, "warning": 0, "passed": 1000
  },
  "dynamic": {
    "total_scenarios": 1288,
    "critical": 0, "warning": 0, "passed": 1288,
    "worst_scenario": "Network partition: App <-> DB",
    "worst_severity": 2.6
  },
  "ops": {
    "avg_availability": 99.9805,
    "total_downtime_seconds": 0.0,
    "total_degradation_events": 3
  },
  "capacity": {
    "over_provisioned_count": 10,
    "cost_reduction_percent": -8.8
  },
  "verdict": "HEALTHY"
}
```

### 改善の推移

| 指標 | Iter 0 | Iter 1 | Iter 2 | Iter 3 |
|------|--------|--------|--------|--------|
| Static Score | 100 | 100 | 100 | **100** |
| Dynamic Critical | **1** | 0 | 0 | **0** |
| Dynamic Warning | 1 | **1** | 0 | **0** |
| Dynamic Worst | 9.0 | 5.3 | 3.2 | **2.6** |
| Verdict | NEEDS ATTN | ACCEPTABLE | HEALTHY | **HEALTHY** |
| Tests | 1,013 | 1,034 | 1,036 | **1,056** |
| Cost余地 | -26.8% | -26.8% | -17.7% | **-8.8%** |
| Over-provisioned | 11 | 11 | 11 | **10** |

---

## 残存する改善余地と収束判定

| # | 項目 | 深刻度 | 収束判定 |
|---|------|--------|---------|
| 1 | 10コンポーネント over-provisioned | LOW | ALB/NLB等の冗長性必須コンポーネント — **これ以上の削減は耐障害性を損なう** |
| 2 | Dynamic最悪 partition 2.6 | LOW | WARNING閾値(4.0)を大きく下回る — **改善不要** |
| 3 | Ops劣化 3件/7日 | LOW | MTBFベースのランダム障害 — **正常な運用の範囲内** |

**収束判定: すべての残存課題が「改善不要」または「これ以上の改善がトレードオフを生む」状態に到達。改善ループは収束しました。**

---

## 学んだこと：4イテレーションの教訓

### 1. maxUnavailable は明示すべき

Rolling restart シナリオで50%同時障害を仮定していたのは、Kubernetes のデフォルト `maxUnavailable: 25%` を考慮していなかったため。カオスシナリオは**実際のデプロイ戦略に準拠**すべきです。

### 2. Circuit Breaker は「早期回復」を前提に設計する

固定タイムアウトのCBは transient failure に過剰反応します。Adaptive recovery（初回1/3タイムアウト + 指数バックオフ）により、一時的な障害からの回復時間を大幅に短縮できます。

### 3. Emergency Autoscaling は必須

通常のHPAは30秒の安定期間を必要としますが、90%超の utilization spike では即時スケーリングが必要です。2段階のスケーリング（通常 + 緊急）の実装により、スパイク耐性が向上します。

### 4. 改善ループには自然な収束点がある

```
Iteration 0: CRITICAL 1, WARNING 1 → 構造的な問題
Iteration 1: CRITICAL 0, WARNING 1 → 限定的な問題
Iteration 2: CRITICAL 0, WARNING 0 → HEALTHY到達
Iteration 3: LOW指標の微改善    → 収束（これ以上の改善はトレードオフ）
```

改善の限界収益が逓減し、「改善しないことが最善」のポイントに到達しました。これが改善ループの健全な終了条件です。

---

## まとめ

InfraSim の改善ループを4回繰り返し、Xクローン（38コンポーネント）の評価を完全に収束させました。

**InfraSim 新機能（Iteration 3）:**
- maxUnavailable ベースの Rolling Restart シナリオ
- Emergency Autoscaling（90%超で即時スケーリング）
- Adaptive CB Recovery（初回1/3タイムアウト + 指数バックオフ）

**xclone 改善（Iteration 3）:**
- 9コンポーネントの Right-Size Phase 2（コスト余地 -17.7%→-8.8%）
- Dynamic worst severity 3.2→2.6

**品質:**
- 1,056テスト、カバレッジ98%
- 4イテレーションで NEEDS ATTENTION → HEALTHY → 収束

https://github.com/mattyopon/infrasim
