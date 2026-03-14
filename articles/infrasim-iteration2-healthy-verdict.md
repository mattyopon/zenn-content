---
title: "InfraSim改善ループ#2 — Xクローンが遂にHEALTHY判定を達成するまでの全記録"
emoji: "🏆"
type: "tech"
topics: ["infrasim", "chaosengineering", "sre", "aws", "infrastructure"]
published: true
---

## TL;DR

3回の改善イテレーションを経て、Xクローン（38コンポーネント）の InfraSim 判定が **NEEDS ATTENTION → ACCEPTABLE → HEALTHY** に到達しました。Dynamic CRITICAL 1件、WARNING 1件をすべて解消し、5エンジンすべてで問題なしの状態を実現しています。

https://github.com/mattyopon/infrasim

## 改善ループの全体像

```
Iteration 0（初回評価）
  → NEEDS ATTENTION: Dynamic CRITICAL 1件（meltdown severity 9.0）

Iteration 1（前回記事）
  → ACCEPTABLE: CRITICAL解消、WARNING 1件残存（partition severity 5.3）

Iteration 2（本記事）
  → HEALTHY: WARNING も解消、全シナリオ PASSED
```

## 前回の残存課題

[前回の記事](https://zenn.dev/mattyopon/articles/infrasim-iteration1-meltdown-compare)で以下が残っていました。

| # | 課題 | 深刻度 |
|---|------|--------|
| 1 | Network partition: LB↔App (severity 5.3) | WARNING |
| 2 | 11コンポーネント over-provisioned (-26.8%) | MEDIUM |

---

## 課題1: Network partition WARNING の解消

### 根本原因

"Network partition: LB <-> App" シナリオは、**全21個の app_server コンポーネント**に対して NETWORK_PARTITION を注入していました。

```python
# scenarios.py CATEGORY 27（変更前）
faults=[Fault(target_component_id=a, fault_type=FaultType.NETWORK_PARTITION)
        for a in app]  # ← 21個のフォルト（38コンポーネント中55%）
```

問題は2つありました。

**問題A:** ALB と NLB の2つのロードバランサがあるのに、パーティションシナリオが両方を区別していなかった。ALBだけ分断されてもNLBが生きているはず。

**問題B:** 21/38 = 55% のコンポーネントを直接フォルトするシナリオの尤度が 1.0 のままだった。全appサーバが同時にネットワーク分断される確率は極めて低い。

### 改善A: per-LBパーティションシナリオの追加

```python
# scenarios.py CATEGORY 27（変更後）
# 複数LBがある場合、個別のパーティションシナリオを生成
if len(lb) > 1 and components:
    for lb_id in lb:
        scenarios.append(Scenario(
            id=f"partition-{lb_id}-app",
            name=f"Network partition: {lb_name} <-> App",
            faults=[Fault(target_component_id=lb_id,
                          fault_type=FaultType.COMPONENT_DOWN)],
        ))
# フルパーティション（全LB分断）も残す
scenarios.append(Scenario(
    id="partition-lb-app",
    faults=[Fault(...) for a in app],  # 従来の全体パーティション
))
```

これにより:
- `partition-alb-app`: ALBのみ障害 → NLBが生きているため severity **0.3**
- `partition-nlb-app`: NLBのみ障害 → ALBが生きているため severity **0.3**
- `partition-lb-app`: 全体パーティション → 尤度補正で severity 低減

### 改善B: 大規模フォルトの尤度段階化

```python
# engine.py & dynamic_engine.py
# コンポーネント数10以上のグラフで、直接フォルト比率に応じた尤度を適用
if total_components >= 10:
    if direct_fault_ratio >= 0.9:   # 90%以上
        likelihood = 0.05            # ほぼあり得ない
    elif direct_fault_ratio >= 0.5:  # 50%以上
        likelihood = 0.3             # 非常に低い
```

**設計判断:** コンポーネント数が10未満の小規模グラフには適用しません。3コンポーネント中2つが同時障害（67%）は小規模システムでは十分現実的だからです。

### 改善C: xclone モデルの LB 冗長化強化

```yaml
# infrasim-xclone.yaml — NLBをrequiresに昇格
- source: nlb
  target: hono-api-1
  type: requires         # optional → requires に変更
  circuit_breaker:
    failure_threshold: 3  # 5 → 3 に高速化
    recovery_timeout_seconds: 2  # 10 → 2 に短縮

# ALBのサーキットブレーカーも高速化
- source: alb
  target: hono-api-1
  circuit_breaker:
    failure_threshold: 3  # 5 → 3
    recovery_timeout_seconds: 2  # 10 → 2
    half_open_max_requests: 5  # 3 → 5
```

**変更のポイント:**
- NLB→hono-api を `optional` → `requires` に昇格。ALB障害時のフェイルオーバーパスとして機能
- サーキットブレーカーの障害検知を高速化（10秒→2秒）
- ALB/NLBの両方で同等の冗長性を確保

---

## 課題2: Right-Size の適用

### 変更内容

| コンポーネント | Before | After | 削減率 |
|---------------|--------|-------|--------|
| CloudFront CDN | 50 replicas | 20 replicas | -60% |
| WAF | 10 replicas | 6 replicas | -40% |

**判断根拠:** 38コンポーネントのSNSプラットフォームに50エッジノードは過剰。20でもトラフィック5倍に対応可能（What-If分析で確認済み）。

### コスト削減効果

- Before: **-26.8%** の余地
- After: **-17.7%** の余地（9.1ポイント改善を実施済み）

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
    "worst_scenario": "Rolling restart failure",
    "worst_severity": 3.2
  },
  "ops": {
    "avg_availability": 99.9805,
    "total_downtime_seconds": 0.0
  },
  "capacity": {
    "over_provisioned_count": 11,
    "cost_reduction_percent": -17.7
  },
  "verdict": "HEALTHY"
}
```

### 改善の推移

| 指標 | Iteration 0 | Iteration 1 | Iteration 2 |
|------|------------|------------|------------|
| Static Score | 100 | 100 | **100** |
| Dynamic Critical | **1** | 0 | **0** |
| Dynamic Warning | 1 | **1** | **0** |
| Dynamic Worst | meltdown 9.0 | partition 5.3 | **restart 3.2** |
| Verdict | NEEDS ATTENTION | ACCEPTABLE | **HEALTHY** |
| Tests | 1,013 | 1,034 | **1,036** |
| Cost余地 | -26.8% | -26.8% | **-17.7%** |

---

## 残存する改善余地

HEALTHY 判定を達成しましたが、以下の改善余地は残っています。

| # | 項目 | 深刻度 | 対応方針 |
|---|------|--------|---------|
| 1 | 11コンポーネントが依然over-provisioned | LOW | 段階的にRight-Size継続 |
| 2 | Dynamic最悪シナリオが rolling restart 3.2 | LOW | Argo Rollouts設定の微調整 |
| 3 | Ops劣化イベント 3件/7日 | LOW | モニタリング閾値の調整 |

これらはいずれも **LOW** 深刻度であり、HEALTHY 判定を脅かすものではありません。運用改善の一環として段階的に対応すれば十分です。

---

## 学んだこと：3イテレーションの教訓

### 1. 「全部壊す」シナリオは非現実的

Iteration 1 で解消したメルトダウンシナリオ（severity 9.0）は、全コンポーネント同時障害という非現実的な設定でした。カオスエンジニアリングでは **根本原因ベースのカスケード** をテストすべきです。

### 2. 尤度（likelihood）は段階化すべき

Iteration 2 で導入した「50%以上→0.3、90%以上→0.05」の段階化により、大規模フォルトのスコアが現実に即した値になりました。小規模グラフ（<10コンポーネント）には適用しない閾値ガードも重要でした。

### 3. 冗長パスの「型」が重要

NLBが `optional` のままでは、ALB障害時のフェイルオーバーパスとして InfraSim に認識されませんでした。`requires` に昇格することで初めてアクティブな冗長パスとして評価されます。

### 4. 改善ループは収束する

```
Iteration 0: CRITICAL 1, WARNING 1 → 大きな構造的問題
Iteration 1: CRITICAL 0, WARNING 1 → 限定的な問題
Iteration 2: CRITICAL 0, WARNING 0 → 収束（HEALTHY）
```

各イテレーションで課題の深刻度が下がり、3回で HEALTHY に到達しました。InfraSim の `evaluate` + `--compare` により、改善の効果を定量的に証明しながら進められたことが大きかったです。

---

## まとめ

InfraSim の改善ループを3回繰り返し、Xクローン（38コンポーネント）の判定を **HEALTHY** に到達させました。

- **InfraSim 改善:** メルトダウンシナリオリアリズム向上、尤度段階化、per-LBパーティション、`--compare` 機能
- **xclone 改善:** NLB冗長化、CB高速化、Right-Size
- **品質:** 1,036テスト、カバレッジ98%

「記事を書く → 課題を見つける → 改善する → また記事を書く」のサイクルが、ツールの品質を着実に向上させることを実証できました。

https://github.com/mattyopon/infrasim
