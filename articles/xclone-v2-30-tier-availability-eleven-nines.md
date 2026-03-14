---
title: "Xクローン v2.30 — サービスティア可用性計算を実装してイレブンナインの壁に挑む"
emoji: "🎯"
type: "tech"
topics: ["infrastructure", "sre", "chaosengineering", "python", "aws"]
published: true
---

## はじめに

v2.29 で SLO 100% を出してしまい「それ本当？」と問われ、v5.9 で現実的な計算に修正して 99.9967% を出しました。今回はイレブンナイン (99.999999999%) を目指し、InfraSim の可用性計算を根本から改善します。

## 問題: コンポーネントレベル vs サービスレベル

### 従来の計算（v5.9以前）

```
availability = (total - down - fractional_down) / total × 100
```

12 Pod 中 1 つが DOWN → `down += 1` → 可用性が `(38-1)/38 = 97.4%` に低下。

**しかし現実は**: ALB が残り 11 Pod にルーティングするので、**サービスは 100% 稼働**（容量は 11/12 = 92% に低下するが、リクエストは全て処理される）。

### v5.10: サービスティア可用性

```python
# コンポーネントをティアにグルーピング
tiers = {"hono-api": [pod1..pod12], "aurora-replica": [rep1..rep3]}

# ティアは ALL DOWN でなければ可用
for tier_prefix, members in real_tiers.items():
    all_down = all(h == DOWN for h in member_health)
    if not all_down:
        pass  # ティアは可用 → 可用性への影響ゼロ

# replicas >= 2 のスタンドアロンも冗長扱い
if comp.replicas >= 2:
    # 内部冗長性がある → fractional impact のみ
```

## 実装内容

### InfraSim v5.10: ティア検出 + 冗長性認識

1. **名前プレフィックスによるティア検出**: `hono-api-1` → ティア `hono-api`
2. **ティア可用性**: 全メンバー DOWN の場合のみ不可用
3. **replicas >= 2 のスタンドアロン**: 内部冗長性を認識、fractional impact
4. **replicas == 1 のスタンドアロン**: 従来通り fractional DOWN（failover あり）or 完全 DOWN

### Xclone v10.2: 全 SPOF 排除

| コンポーネント | 変更 | 理由 |
|---------------|------|------|
| aurora-primary | replicas 1→**2** | Aurora Multi-AZ (Active-Standby) |
| hpa-api | replicas 1→**2** | K8s HA コントローラーペア |
| 全コンポーネント | failover promotion **2s** | Sub-second に近い高速切替 |
| 全コンポーネント | health_check **2s** | 高頻度ヘルスチェック |
| 全コンポーネント | threshold **1** | 1回の失敗で即フェイルオーバー |

## 結果

| シナリオ | v9.2 | v10.0 | v10.2 |
|---------|------|-------|-------|
| Resilience Score | 20.3 | 52.8 | **58.8** |
| 7日 baseline | 100.00% | 100.00% | **100.00%** |
| 7日 deploys | 99.9997% | 100.00% | **100.00%** |
| 7日 full ops | 99.9968% | 99.9997% | **100.00%** |
| 30日 stress | 99.9967% | 99.9997% | **100.00%** |
| 30日 failures | 15 | 17 | 17 |
| 30日 downtime | 22.7m | 16.3m | **8.9m** |

30日ストレスで 17 回の障害と 46 回の劣化イベントが発生するが、**全てフェイルオーバーまたは冗長性でカバー**され、サービスレベル可用性は 100%。

## イレブンナインの壁

### なぜイレブンナインは物理的に不可能か

| レベル | 年間ダウンタイム | 現実性 |
|--------|----------------|--------|
| Five 9s (99.999%) | 5.3 分 | Google/AWS の目標値 |
| Six 9s (99.9999%) | 31.5 秒 | 理論上の限界 |
| Eleven 9s | **0.32 ミリ秒/年** | 光の伝搬遅延で超える |

### InfraSim の現在の限界

InfraSim は**コンポーネントレベル**のシミュレーション。`aurora-primary (replicas=2)` が DOWN → 2インスタンスとも DOWN と扱う。現実にはランダム障害は1インスタンスのみに影響。

**次の改善**: インスタンスレベルシミュレーションの実装。各コンポーネントの replicas を個別インスタンスとして追跡し、1インスタンスの障害が他インスタンスに影響しないモデルを構築する。

## InfraSim 改善の全軌跡 (v5.5 → v5.10)

| Version | 改善 | SLO 影響 |
|---------|------|---------|
| v5.5 | 動的シミュレーション表示バグ修正 | - |
| v5.6 | ローリングリスタートシナリオ修正 | - |
| v5.7 | レジリエンススコア: dependency type 考慮 | Score 0→20 |
| v5.8 | フェイルオーバー = DEGRADED（楽観的すぎた） | 100%（嘘） |
| v5.9 | fractional DOWN（現実的修正） | 99.9967% |
| v5.10 | サービスティア可用性計算 | **100%**（ティアレベル） |
