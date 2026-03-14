---
title: "InfraSim改善ループ#1 — メルトダウン誤検知の解消と--compare機能でXクローンがACCEPTABLEに昇格"
emoji: "🔄"
type: "tech"
topics: ["infrasim", "chaosengineering", "sre", "python", "infrastructure"]
published: true
---

## TL;DR

前回の記事で残っていた **Dynamic CRITICAL（Total infrastructure meltdown, severity 9.0）** を解消しました。原因は「全38コンポーネントを同時にDOWNにする」という非現実的なシナリオ設計でした。根本原因ベースのカスケードに再設計し、新機能 `evaluate --compare` でv10→v12の改善を一発で可視化できるようにしました。

https://github.com/mattyopon/infrasim

**結果:** Xクローンの判定が **NEEDS ATTENTION → ACCEPTABLE** に改善。

## 前回の記事で残った課題

[前回の記事](https://zenn.dev/mattyopon/articles/infrasim-evaluate-xclone-crossengine)で `evaluate` コマンドを実装し、5エンジン一括評価を可能にしました。しかし以下の課題が残っていました。

| # | 課題 | 深刻度 |
|---|------|--------|
| 1 | 動的メルトダウン severity 9.0 が Score 100 でも残存 | CRITICAL |
| 2 | LB↔App ネットワーク分断 WARNING | HIGH |
| 3 | 11コンポーネント over-provisioned（-26.8%） | MEDIUM |
| 4 | モデル間比較機能がない | MEDIUM |

今回は **課題1（メルトダウン誤検知）** と **課題4（比較機能）** を解消します。

---

## 課題1の根本原因分析

### なぜ Score 100 なのに CRITICAL が出るのか？

`scenarios.py` のCATEGORY 22を調べると、原因は明白でした。

```python
# BEFORE: 全コンポーネントを同時にDOWNにする
scenarios.append(Scenario(
    id="total-meltdown",
    name="Total infrastructure meltdown",
    faults=[Fault(target_component_id=c, fault_type=FaultType.COMPONENT_DOWN)
            for c in component_ids],  # ← 38コンポーネント全部
))
```

**問題:** 38コンポーネントを**同時に**DOWNにするシナリオは、AWSリージョン全体が消滅するレベルの災害でのみ発生します。現実的にはあり得ません。

**severity 計算の内訳:**
```
spread_score = 38/38 = 1.0（全コンポーネント影響）
impact_score = 1.0（全部DOWN）
raw_score = 1.0 × 1.0 × 10.0 = 10.0
likelihood = 0.9（デフォルト）
final_severity = 10.0 × 0.9 = 9.0  ← CRITICAL
```

一方、Resilience Score は **単一コンポーネント障害** に対する耐性を評価するため、多重冗長化されたv12は正しく100点になります。**静的スコアと動的シナリオは異なる観点を評価しており、矛盾ではなかった** — しかしシナリオ設計が非現実的だったことが本質的な問題でした。

---

## 改善1: メルトダウンシナリオのリアリズム向上

### 変更内容

**scenarios.py** — CATEGORY 22を2つに分割:

```python
# AFTER (22a): 全コンポーネント同時故障 — 極低尤度で残す
scenarios.append(Scenario(
    id="total-meltdown",
    name="Total infrastructure meltdown",
    description="...extremely unlikely — simultaneous all-down.",
    faults=[Fault(...) for c in component_ids],
    # 尤度は engine.py で 0.05 に制限される
))

# AFTER (22b): 根本原因ベースのカスケード — 現実的
# 依存度の高い上位2-3コンポーネントのみを故障させ、
# カスケードエンジンが実際の伝搬範囲を計算
critical_components = _rank_by_criticality(component_ids, components)
scenarios.append(Scenario(
    id="cascading-meltdown",
    name="Cascading infrastructure failure",
    faults=[Fault(...) for c in critical_components[:3]],
))
```

**engine.py** — 極端シナリオの尤度を制限:

```python
# シナリオが全コンポーネントの90%以上を直接故障させる場合、
# 尤度を0.05に制限（severity 9.0 → 0.45 に低下）
direct_fault_ratio = len(scenario.faults) / total_components
if direct_fault_ratio >= 0.9:
    chain.likelihood = min(chain.likelihood, 0.05)
```

**dynamic_engine.py** — 動的エンジンにも同様の尤度制限を適用:

```python
# 動的シナリオでも直接フォルト比率に基づく尤度を計算
scenario_likelihood = 0.05 if direct_fault_ratio >= 0.9 else 1.0

# _severity_for_step に尤度を渡す
step_severity = self._severity_for_step(
    comp_states, step_effects, scenario_likelihood
)
```

### 設計判断: なぜ削除ではなく尤度調整なのか？

「全コンポーネント同時障害」シナリオを**削除する**選択肢もありましたが、以下の理由で**尤度を下げて残す**方針にしました。

1. **完全性** — シナリオとして存在すること自体に意味がある（最悪ケースの定量化）
2. **透明性** — 「テストしていない」より「テストしたが極低確率」の方が誠実
3. **柔軟性** — ユーザーが尤度係数をオーバーライドすれば、リージョン障害を想定した評価も可能

---

## 改善2: evaluate --compare 機能

2つのモデルを一発で比較できる機能を追加しました。

### 使い方

```bash
# v12 と v10 を比較
infrasim evaluate \
  --file infrasim-xclone.yaml \
  --compare infrasim-xclone-v10.yaml

# JSON で差分を出力（CI/CD向け）
infrasim evaluate \
  --file infrasim-xclone.yaml \
  --compare infrasim-xclone-v10.yaml \
  --json
```

### コンソール出力

```
╔═══════════════════════════════════════════════════════════╗
║  COMPARISON SUMMARY                                      ║
╠═══════════════════════════════════════════════════════════╣
║  Metric              │ Model A (v12)  │ Model B (v10)  │ Delta    ║
╠══════════════════════╪════════════════╪════════════════╪══════════╣
║  Resilience Score    │ 100.0          │ 58.8           │ +41.2 ✅ ║
║  Static Critical     │ 0              │ 0              │ —        ║
║  Dynamic Critical    │ 0              │ 0              │ —        ║
║  Dynamic Warning     │ 1              │ 1              │ —        ║
║  Worst Severity      │ 5.3            │ 5.3            │ —        ║
║  Ops Availability    │ 99.980%        │ 99.999%        │ -0.02%   ║
║  Ops Downtime        │ 0.0s           │ 133.0s         │ -133s ✅ ║
║  Over-provisioned    │ 11             │ 13             │ -2 ✅    ║
║  Cost Reduction      │ -26.8%         │ -24.9%         │ -1.9%    ║
║  Verdict             │ ACCEPTABLE     │ ACCEPTABLE     │ —        ║
╚══════════════════════╧════════════════╧════════════════╧══════════╝
```

### JSON出力（CI/CD連携）

```json
{
  "model_a": { "model": "infrasim-xclone.yaml", ... },
  "model_b": { "model": "infrasim-xclone-v10.yaml", ... },
  "comparison": {
    "resilience_score_delta": -41.2,
    "dynamic_critical_delta": 0,
    "ops_downtime_delta": 133.0,
    "over_provisioned_delta": 2,
    "verdict_changed": false
  }
}
```

**ユースケース:**
- **アーキテクチャ改善の定量評価** — 変更前後のモデルを比較して改善を数値で証明
- **PRレビュー** — インフラ変更のPRにevaluate結果を添付
- **SLO契約更新** — SLO引き上げ前にevaluateで裏付けを取得

---

## 改善後の Xクローン評価結果

### Before（前回記事時点）

```json
{
  "static":  { "resilience_score": 100.0, "critical": 0 },
  "dynamic": { "critical": 1, "worst_severity": 9.0 },
  "verdict": "NEEDS ATTENTION"
}
```

### After（今回の改善後）

```json
{
  "static":  { "resilience_score": 100.0, "critical": 0 },
  "dynamic": { "critical": 0, "worst_severity": 5.3 },
  "verdict": "ACCEPTABLE"
}
```

| 指標 | Before | After | 変化 |
|------|--------|-------|------|
| Static Score | 100/100 | 100/100 | — |
| Dynamic Critical | **1** | **0** | **解消** |
| Dynamic Worst | 9.0 (meltdown) | 5.3 (net partition) | **-3.7** |
| Verdict | NEEDS ATTENTION | **ACCEPTABLE** | **昇格** |

---

## 残存課題 — 次のイテレーションで対処

| # | 課題 | 深刻度 | 対処方針 |
|---|------|--------|---------|
| 1 | Network partition WARNING (severity 5.3) | WARNING | LB↔App冗長パス追加でxcloneモデル改善 |
| 2 | 11コンポーネント over-provisioned (-26.8%) | MEDIUM | xcloneモデルのRight-Size適用 |
| 3 | HEALTHY判定未達（WARNING 1件残存） | MEDIUM | 課題1解決で自動的に達成 |

**目標:** 次のイテレーションで Verdict を **HEALTHY** に昇格させる。

---

## テスト・カバレッジ

今回の改善で21テストを追加し、全1,034テストがPASS。

| 対象 | テスト数 | カバレッジ |
|------|---------|-----------|
| evaluate.py（--compare含む） | 12 | 65% → **97%** |
| scenarios.py（cascading-meltdown） | 3 | 100% |
| engine.py（尤度制限） | 3 | 100% |
| dynamic_engine.py（尤度伝搬） | 3 | 99% |
| **全体** | **1,034** | **98%** |

---

## まとめ

改善ループ#1で学んだこと:

1. **「全部壊す」シナリオは現実的ではない** — カオスエンジニアリングでは「何が根本原因で、どこまで伝搬するか」をテストすべき
2. **尤度（likelihood）は重要なパラメータ** — 発生確率を考慮しないseverityは誤ったアラートを生む
3. **比較機能はインフラ改善の必需品** — Before/Afterを定量比較できなければ、改善の効果を証明できない

次のイテレーションでは、残存するNetwork partition WARNINGを解消し、**HEALTHY判定**を目指します。

https://github.com/mattyopon/infrasim
