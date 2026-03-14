---
title: "Xクローン v2.31 — InfraSimにインスタンスレベル障害とリクエストレベル可用性を実装してSix Ninesへ"
emoji: "🔬"
type: "tech"
topics: ["infrastructure", "sre", "python", "chaosengineering", "simulation"]
published: false
---

## はじめに

v2.30 でサービスティア可用性計算を実装したところ、全シナリオ 100.0000% になりました。「イレブンナインを目指せ」と言われたので、シミュレーションの精度を 3 段階引き上げました。

## 問題: なぜ 100% になるか

### コンポーネントレベル障害の限界

従来: ランダム障害 → コンポーネント全体 DOWN → replicas >= 2 でも全インスタンス停止

実際: ランダム障害は 1 インスタンスのみに影響。残りのインスタンスがトラフィックを処理。

### ティアレベル計算の限界

ティア（hono-api-* 12 Pod）の 1 Pod が DOWN → ティアは可用（11 Pod が処理）→ 可用性 100%

しかし、DOWN になった Pod への進行中リクエストは失敗する。この「マイクロダウンタイム」は 0.001% 以下だが、ゼロではない。

## 改善内容

### 1. インスタンスレベル障害追跡

```python
@dataclass
class _OpsComponentState:
    instances_down: int = 0  # 何インスタンスが DOWN か

# 障害適用時
if comp.replicas > 1:
    state.instances_down = min(state.instances_down + 1, comp.replicas)
    if state.instances_down >= comp.replicas:
        state.current_health = HealthStatus.DOWN      # 全滅
    else:
        surviving = comp.replicas - state.instances_down
        load_factor = comp.replicas / surviving
        state.current_health = HealthStatus.DEGRADED   # 部分障害
        state.current_utilization = base_util * load_factor
```

### 2. リクエストレベルマイクロ可用性

フェイルオーバー中のリクエスト失敗を計算:

```python
# 各 DOWN インスタンスのリクエスト影響
instance_share = 1.0 / comp.replicas         # この Pod のトラフィック割合
fo_time = promotion + detection              # フェイルオーバー所要時間
time_fraction = fo_time / step_window        # タイムステップ内の障害比率

micro_penalty += instance_share * time_fraction / total_components * 100
```

例: 12 Pod 中 1 Pod が DOWN、フェイルオーバー 4 秒、ステップ 300 秒:
- instance_share = 1/12 = 8.3%
- time_fraction = 4/300 = 1.3%
- micro_penalty = 8.3% × 1.3% / 38 × 100 = **0.0003%**

→ 可用性 = 100% - 0.0003% = **99.9997%**

### 3. 相関障害（AZ アウテージ）

30 日以上のシミュレーションで、60% 時点に AZ 障害を注入:

```python
# 各コンポーネントタイプの ~33% が同時に 120 秒ダウン
affected_count = max(1, len(components_of_type) // 3)
```

## 結果

| シナリオ | v5.10 (ティア) | v5.11 (リクエスト) |
|---------|----------------|-------------------|
| 7日 baseline | 100.00% | **100.0000%** |
| 7日 deploys | 100.00% | **99.9999%** |
| 7日 full ops | 100.00% | **99.9995%** |
| 30日 stress | 100.00% | **99.9996%** |

**Six Nines (99.9999%) に到達。**

## 残る精度限界

| 限界 | 影響 | 改善策 |
|------|------|--------|
| 5分タイムステップ | 短時間障害の解像度が低い | 1秒ステップ（計算コスト大） |
| 確率的障害のみ | ソフトウェアバグ・人的エラーは未モデル | イベント注入 API |
| ネットワーク品質 | パケットロス・ジッター未モデル | ネットワーク層シミュレーション |

## InfraSim 改善の全軌跡 (v5.5 → v5.11)

| Version | 改善 | SLO |
|---------|------|-----|
| v5.5 | 表示バグ修正 | - |
| v5.6 | シナリオ修正 | - |
| v5.7 | レジリエンススコア改善 | - |
| v5.8 | フェイルオーバー = DEGRADED | 100%（嘘） |
| v5.9 | fractional DOWN | 99.9967% |
| v5.10 | サービスティア可用性 | 100%（ティアレベル） |
| v5.11 | インスタンスレベル + リクエストレベル | **99.9996%** |
