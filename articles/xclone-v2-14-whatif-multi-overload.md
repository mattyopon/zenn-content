---
title: "XClone v2.14: InfraSim v4.1 マルチパラメータWhat-if & トラフィック過負荷検出 — 5課題修正の実録"
emoji: "🔥"
type: "tech"
topics: ["infrasim", "sre", "capacityplanning", "whatif", "infrastructure"]
published: true
---

## はじめに

前回の[v2.13記事](https://qiita.com/ymaeda_it/items/)では、**InfraSim v4.0**でWhat-if Analysisエンジン（5パラメータのパラメトリックスイープ）とCapacity Planningエンジンを導入し、SLOブレークポイント分析を実装しました。

しかし、v4.0には**2つの大きな制約**がありました。

1. **単一パラメータのみ** — 「MTTRが2倍 **かつ** メンテナンスが2倍」のような複合シナリオを分析できない
2. **トラフィック因子・レプリカ因子が無効** — シミュレーションに影響を与えない「飾り」だった

v4.1ではこれらを解決し、さらに**5つの重大なバグ**を発見・修正しました。

### シリーズ記事

| # | 記事 | テーマ |
|---|------|--------|
| 1 | [**v2.0** -- フルスタック基盤](https://qiita.com/ymaeda_it/items/902aa019456836624081) | Hono+Bun / Next.js 15 / Drizzle / ArgoCD / Linkerd / OTel |
| 2 | [**v2.1** -- 品質・運用強化](https://qiita.com/ymaeda_it/items/e44ee09728795595efaa) | Playwright / OpenSearch ISM / マルチリージョンDB / tRPC / CDC |
| 3 | [**v2.2** -- パフォーマンス](https://qiita.com/ymaeda_it/items/d858969cd6de808b8816) | 分散Rate Limit / 画像最適化 / マルチリージョンWebSocket |
| 4 | [**v2.3** -- DX・コスト最適化](https://qiita.com/ymaeda_it/items/cf78cb33e6e461cdc2b3) | Feature Flag / GraphQL Federation / コストダッシュボード |
| 5 | [**v2.4** -- テスト完備](https://qiita.com/ymaeda_it/items/44b7fca8fc0d07298727) | E2Eテスト拡充 / Terratest インフラテスト |
| 6 | [**v2.5** -- カオステスト](https://qiita.com/ymaeda_it/items/bfe98a49e07cc80dbf32) | InfraSim / 296シナリオ / レジリエンス評価 |
| 7 | [**v2.6** -- レジリエンス強化](https://qiita.com/ymaeda_it/items/817724b2936816f4f28c) | 3ラウンド改善 / WARNING 36→2 / 95%改善 |
| 8 | **v2.7** -- 完全レジリエンス | 6ラウンド完結 / 1,647シナリオ全PASSED / 100%達成 |
| 9 | [**v2.8** -- 動的シミュレーション](https://qiita.com/ymaeda_it/items/) | InfraSim v2.0 / 1,695シナリオ / 動的トラフィック / オートスケーリング |
| 10 | [**v2.9** -- レジリエンス強化II](https://qiita.com/ymaeda_it/items/) | InfraSim v2.1 / CB + Singleflight + Cache Warming / WARNING 2→1 |
| 11 | [**v2.10** -- 完全PASSED](https://qiita.com/ymaeda_it/items/) | 二重遮断CB / 3,351シナリオ全PASSED / カオスエンジニアリング完結 |
| 12 | [**v2.11** -- 運用シミュレーション](https://qiita.com/ymaeda_it/items/) | InfraSim v3.0 / SLOトラッキング / Error Budget / 段階的劣化 |
| 13 | [**v2.12** -- 運用強化](https://qiita.com/ymaeda_it/items/) | InfraSim v3.1/v3.2 / ローリングデプロイ / 全シナリオSLO 99.9%達成 |
| 14 | [**v2.13** -- What-if & Capacity](https://qiita.com/ymaeda_it/items/) | InfraSim v4.0 / パラメトリックスイープ / SLOブレークポイント |
| **15** | **v2.14 -- Multi What-if & Overload Detection（本記事）** | **InfraSim v4.1 / 複合パラメータ / トラフィック過負荷 / 5バグ修正** |

### InfraSimバージョンの進化

```
InfraSim のバージョン進化:

v1.0 (v2.5~v2.7): 静的シミュレーション
  ├ SPOF検出
  ├ カスケード障害分析
  └ 1,647シナリオ（単一時点の障害注入）

v2.0 (v2.8): 動的シミュレーション
  ├ トラフィックパターン（Spike / Wave / DDoS / Flash Crowd）
  ├ オートスケーリング
  ├ フェイルオーバー
  └ 1,695シナリオ（300秒 × 5秒ステップ）

v2.1 (v2.9~v2.10): レジリエンス機構
  ├ Circuit Breaker
  ├ Adaptive Retry
  ├ Cache Warming / Singleflight
  └ 3,351シナリオ全PASSED

v3.0 (v2.11): 運用シミュレーション
  ├ Long-Running Simulation（7〜30日）
  ├ Operational Event Injection（デプロイ/メンテナンス/障害/劣化）
  ├ SLO/Error Budget Tracker
  └ Diurnal-Weekly + Growth Trend トラフィック

v3.1/v3.2 (v2.12): 運用シミュレーション強化
  ├ ローリングデプロイ（1台ずつ順次デプロイ）
  ├ ティア別ステージドメンテナンス（最大3台/グループ）
  ├ デフォルトMTBF/MTTR + 劣化ジッタ
  └ 全5シナリオ SLO 99.9% PASS

v4.0 (v2.13): What-if & Capacity Planning
  ├ What-if Analysis（5パラメータのパラメトリックスイープ）
  ├ Capacity Planning Engine（成長率予測 + Error Budget予測）
  ├ SLOブレークポイント検出
  └ CLI: infrasim whatif / infrasim capacity

v4.1 (v2.14, 本記事): Multi What-if & Overload Detection  ← NEW
  ├ マルチパラメータWhat-if（複合シナリオ分析）
  ├ トラフィック過負荷検出（HealthStatus.OVERLOADED追加）
  ├ MTBF/MTTR因子のゼロ値事前populate修正
  ├ レプリカ因子の逆比例メトリクス調整
  └ 5つの重大バグ修正（下記参照）
```

## 新機能1: マルチパラメータWhat-if

### なぜ複合パラメータが必要か

v4.0のWhat-ifは1パラメータずつしか変えられませんでした。しかし現実のインシデントは「トラフィック急増 **＋** 障害頻度増加」のように**複数の条件が同時に変わる**ものです。

```python
# v4.0: 単一パラメータ（限界あり）
WhatIfScenario(parameter="mttr_factor", values=[0.5, 1.0, 2.0])

# v4.1: 複合パラメータ（NEW）
MultiWhatIfScenario(
    parameters={
        "mttr_factor": 2.0,        # 復旧に2倍の時間
        "maint_duration_factor": 2.0  # メンテナンスも2倍
    },
    description="Worst case: slow recovery + long maintenance"
)
```

### 実装

`MultiWhatIfScenario`と`MultiWhatIfResult`を追加し、全パラメータを同時にグラフ/シナリオに適用します。

```python
class MultiWhatIfScenario(BaseModel):
    base_scenario: OpsScenario
    parameters: dict[str, float]  # 例: {"mttr_factor": 2.0, "traffic_factor": 3.0}
    description: str = ""
    seed: int = 42

class MultiWhatIfResult(BaseModel):
    parameters: dict[str, float]
    avg_availability: float
    min_availability: float
    total_failures: int
    total_downtime_seconds: int
    slo_pass: bool
    summary: str = ""
```

### CLI

```bash
# デフォルト4パターンを実行
infrasim whatif --yaml demo-infra.yaml --multi defaults

# カスタム複合パラメータ
infrasim whatif --yaml demo-infra.yaml \
  --multi "traffic_factor=3.0,mtbf_factor=0.1"
```

### 分析結果

| シナリオ | パラメータ | 平均可用性 | 障害数 | SLO |
|---------|-----------|----------|--------|-----|
| Worst case | MTTR×2 + メンテ×2 | 99.8182% | 0 | **FAIL** |
| Growth stress | Traffic×3 + MTBF×0.1 | 69.8066% | 3 | **FAIL** |
| Cost optimized | Replica×0.5 + MTTR×2 | 97.8516% | 0 | **FAIL** |
| Best case | MTTR×0.5 + メンテ×0.5 | 99.9422% | 0 | PASS |
| Stress combo | Traffic×2 + Replica×0.5 | 67.3360% | 0 | **FAIL** |

**考察**:
- **Growth stress**（3倍トラフィック + 10倍障害率）は平均可用性69.8%まで低下。障害が3件発生し、ピーク時間帯の過負荷と合わせてSLOを大きく逸脱
- **Cost optimized**（レプリカ半減 + MTTR2倍）は97.85%。レプリカ半減で個々のインスタンスの負荷が2倍になり、ピーク時にオーバーロード
- **Best case**のみSLO PASS。復旧高速化 + メンテナンス短縮で余裕を確保

## 新機能2: トラフィック過負荷検出

### HealthStatus.OVERLOADED

v4.0まで、コンポーネントの健全性は `HEALTHY`/`DEGRADED`/`DOWN` の3状態でした。v4.1で `OVERLOADED` を追加し、トラフィック起因の容量超過を検出します。

```python
class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    OVERLOADED = "overloaded"   # NEW: 容量超過だが完全停止ではない
    DOWN = "down"
```

### 絶対閾値によるヘルスチェック

利用率に基づいてヘルス状態を判定します。

```python
# 利用率ベースのヘルス遷移（絶対閾値）
if effective_util > 110.0:
    state.current_health = HealthStatus.DOWN        # 完全停止
elif effective_util > 95.0:
    state.current_health = HealthStatus.OVERLOADED   # 過負荷
elif effective_util > 85.0:
    state.current_health = HealthStatus.DEGRADED     # 劣化
else:
    state.current_health = HealthStatus.HEALTHY      # 正常
```

| 閾値 | 状態 | 意味 | SLIへの影響 |
|------|------|------|------------|
| < 85% | HEALTHY | 正常運用 | 可用性にカウント |
| 85-95% | DEGRADED | 性能劣化 | 可用性にカウント |
| 95-110% | OVERLOADED | 容量超過 | エラーレートに加算 |
| > 110% | DOWN | 完全停止 | 不可用にカウント |

### SLIへの反映

```python
# 可用性: DOWNのみ除外（DEGRADED/OVERLOADEDは「動いている」）
availability = ((total - down) / total * 100.0)

# エラーレート: DOWN + OVERLOADED（過負荷はエラーを返す）
error_rate = ((down + overloaded) / total)
```

## 発見・修正した5つの重大バグ

v4.1の実装・テスト過程で**5つの重大なバグ**を発見し、修正しました。

### バグ1: 過剰な過負荷検出（可用性59%→99.9%）

**症状**: ベースラインシミュレーションで可用性が59%（本来99.9%以上のはず）

**原因**: 型別の過負荷閾値（`_OVERLOAD_THRESHOLDS`）がコンポーネントの通常運用時の利用率より低かった。

```python
# 修正前: 型別閾値（データベースの閾値0.8）
_OVERLOAD_THRESHOLDS = {
    "database": 0.8,  # DEGRADED > 56%, OVERLOADED > 72%, DOWN > 80%
}
# → PostgreSQL(base_util=65%)が常にDEGRADED判定！

# 修正後: 絶対閾値（全型共通）
if effective_util > 110.0:     # DOWN
elif effective_util > 95.0:     # OVERLOADED
elif effective_util > 85.0:     # DEGRADED
```

### バグ2: デモインフラのプロビジョニング不足（可用性54%→99.9%）

**症状**: バグ1を修正しても可用性54%

**原因**: `utilization()` は `max(cpu, memory, disk, connections)` を返す。デモインフラのapp-serverは450/500コネクション（90%）、PostgreSQLは90/100コネクション（90%）だった。

```yaml
# 修正前: プロビジョニング不足
app-1:
  replicas: 1
  capacity: { max_connections: 500 }
  metrics: { network_connections: 450 }  # 90%利用率！
  # → base_util=90%, 2.5xピーク時: 225% → DOWN

# 修正後: 適切なプロビジョニング
app-1:
  replicas: 3
  capacity: { max_connections: 1000 }
  metrics: { network_connections: 200 }  # 20%利用率
  # → base_util=33%, 2.5xピーク時: 82.5% → HEALTHY
```

**教訓**: `utilization()=max(metrics)` なので、1つでもボトルネックメトリクスがあるとbase_utilが跳ね上がる。実際のシステムも同じ — コネクションプール枯渇は最も見落とされるボトルネック。

### バグ3: MTBF因子が完全に無効（0件障害のまま）

**症状**: MTBF因子を0.05（20倍の障害頻度）にしても障害0件

**原因**: コンポーネントの`operational_profile.mtbf_hours`の初期値が0。What-if因子が `0 * 0.05 = 0` を計算し、その後 `_schedule_events()` でゼロ値がデフォルト値（2160h）に置き換えられるため、因子が完全に無視されていた。

```python
# 修正前: ゼロ × 因子 = ゼロ
comp.operational_profile.mtbf_hours *= factor  # 0 * 0.05 = 0
# → _schedule_eventsで0 <= 0判定 → デフォルト2160hにリセット
# → 因子が効かない！

# 修正後: ゼロ値を事前にデフォルト値で埋める
if comp.operational_profile.mtbf_hours <= 0:
    comp.operational_profile.mtbf_hours = (
        _DEFAULT_MTBF_HOURS.get(comp.type.value, 2160.0)
    )
comp.operational_profile.mtbf_hours *= factor
# → 2160 * 0.05 = 108h (4.5日) → 7日間で障害発生
```

### バグ4: レプリカ因子が無効（全値同一結果）

**症状**: replica_factor 0.5〜1.5で全て同じ可用性（99.9008%）

**原因**: What-if でレプリカ数を変更すると、`comp.replicas` が新しい値になる。しかし `_init_ops_states()` で `base_replicas = current_replicas = comp.replicas` と両方同じ値が設定されるため、 `replica_ratio = base_replicas / current_replicas = 1.0` となり利用率が変化しない。

```python
# 修正前: レプリカ数だけ変更（効果なし）
comp.replicas = max(1, round(comp.replicas * factor))
# → base_replicas = current_replicas = 新レプリカ数
# → replica_ratio = 1.0（常に1.0）

# 修正後: メトリクスを逆比例で調整
original = comp.replicas
new_replicas = max(1, round(original * factor))
comp.replicas = new_replicas
if original > 0 and new_replicas != original:
    load_ratio = original / new_replicas  # 3→2 なら 1.5倍
    comp.metrics.cpu_percent = min(100.0, comp.metrics.cpu_percent * load_ratio)
    comp.metrics.memory_percent = min(100.0, comp.metrics.memory_percent * load_ratio)
```

### バグ5: CLI --multi --defaults が動作しない

**症状**: `infrasim whatif --multi --defaults` でパースエラー

**原因**: `--multi` は `str | None` 型で文字列値を必須とするため、`--multi` の直後の `--defaults` が `--multi` の値として解釈される。

```python
# 修正: "defaults" 文字列も受け付ける
if defaults or multi.lower() == "defaults":
    # デフォルト4パターンを実行
    multi_results = engine.run_default_multi_whatifs()
```

## What-if分析結果（全5パラメータ）

### 単一パラメータスイープ

```
mtbf_factor:
   0.05x ->  99.6034% | failures= 6 | SLO=FAIL ← 障害6件！
   0.10x ->  99.7521% | failures= 3 | SLO=FAIL
   0.25x ->  99.9008% | failures= 0 | SLO=PASS
   0.50x ->  99.9008% | failures= 0 | SLO=PASS
   1.00x ->  99.9008% | failures= 0 | SLO=PASS
   >>> BREAKPOINT: 0.05x

traffic_factor:
   1.00x ->  99.9008% | failures= 0 | SLO=PASS
   1.50x ->  97.9342% | failures= 0 | SLO=FAIL ← 1.5倍でもうSLO違反
   2.00x ->  85.6387% | failures= 0 | SLO=FAIL
   3.00x ->  69.9223% | failures= 0 | SLO=FAIL
   5.00x ->  50.1074% | failures= 0 | SLO=FAIL
   >>> BREAKPOINT: 1.5x

replica_factor:
   0.50x ->  97.8516% | failures= 0 | SLO=FAIL ← レプリカ半減で即座に破綻
   0.75x ->  99.9008% | failures= 0 | SLO=PASS
   1.00x ->  99.9008% | failures= 0 | SLO=PASS
   >>> BREAKPOINT: 0.5x

maint_duration_factor:
   0.50x ->  99.9422% | failures= 0 | SLO=PASS
   1.00x ->  99.9008% | failures= 0 | SLO=PASS
   2.00x ->  99.8182% | failures= 0 | SLO=FAIL
   >>> BREAKPOINT: 2.0x
```

### ブレークポイントまとめ

| パラメータ | ブレークポイント | 意味 |
|-----------|-----------------|------|
| **traffic_factor** | **1.5x** | 通常の1.5倍トラフィックでSLO違反 → スケーリングヘッドルームが少ない |
| **replica_factor** | **0.5x** | レプリカ半減でSLO違反 → コスト削減の下限 |
| **maint_duration_factor** | **2.0x** | メンテナンス2倍でSLO違反 → メンテナンス効率化が重要 |
| **mtbf_factor** | **0.05x** | 障害頻度20倍でSLO違反 → 障害耐性は高い |
| **mttr_factor** | なし | 全値PASS → MTTRの影響は小さい（障害自体が少ないため） |

### 分析の洞察

1. **トラフィックが最大のリスク**: ブレークポイントが1.5xと最も低い。ピーク時に利用率85%を超えるとDEGRADED、110%超でDOWN判定される
2. **レプリカ削減は即座に効く**: 0.5x（半減）で利用率が2倍になり、ピーク時にDOWN
3. **障害耐性は高い**: MTBF 0.05x（20倍の障害頻度）でも可用性99.6%。冗長化（replicas=2-3）が効いている
4. **MTTRの影響は限定的**: 障害が少ないため、復旧時間を8倍にしてもSLO圏内

## キャパシティプランニング

### 成長率10%/月の予測

```
nginx (load_balancer): util=30.0% | months_to_cap=10.3 | urgency=healthy
  replicas: now=2 → 3m=2 → 6m=2 → 12m=3

app-1 (app_server):    util=33.0% | months_to_cap= 9.3 | urgency=healthy
  replicas: now=3 → 3m=3 → 6m=3 → 12m=5

postgres (database):   util=34.0% | months_to_cap= 9.0 | urgency=healthy
  replicas: now=2 → 3m=2 → 6m=2 → 12m=4

redis (cache):         util=28.0% | months_to_cap=11.0 | urgency=healthy
  replicas: now=2 → 3m=2 → 6m=2 → 12m=3

rabbitmq (queue):      util=20.0% | months_to_cap=14.6 | urgency=healthy
  replicas: now=2 → 3m=2 → 6m=2 → 12m=2
```

- **ボトルネック**: PostgreSQL（9.0ヶ月）→ app-1（9.3ヶ月）→ nginx（10.3ヶ月）
- 全コンポーネントhealthy。3ヶ月以内のスケーリング不要
- 12ヶ月後: 合計レプリカ 14→22（57%増）

### Error Budget（シミュレーションベース）

```
Burn rate:     1.1899 min/day
Budget total:  43.20 min/month (99.9% SLO)
Consumed (7d): 19.3%
Projected/mo:  82.6%
Status:        WARNING
Days to exhaustion: 29.3 days
```

- 日次バーンレート1.19分は主にピーク時間帯のDEGRADED状態から
- 月間消費82.6%で**WARNING**。Error Budgetは残るがギリギリ
- **対策**: トラフィックピーク時のオートスケーリング設定、またはpostgresの3台目レプリカ追加

## 技術的な実装メモ

### `utilization()` = max(metrics) の重要性

コンポーネントの利用率は `max(cpu, memory, disk, connections)` で計算されます。

```python
def utilization(self) -> float:
    factors = []
    if self.capacity.max_connections > 0:
        factors.append(
            self.metrics.network_connections / self.capacity.max_connections * 100
        )
    if self.metrics.cpu_percent > 0:
        factors.append(self.metrics.cpu_percent)
    ...
    return max(factors) if factors else 0.0
```

これは**リミッティングファクター**の原則に基づいています。CPUが30%でもコネクションプールが90%なら、そのコンポーネントは90%利用中です。バグ2の教訓は、1つのメトリクスが飽和するだけでシステム全体のボトルネックになるということです。

### OVERLOADED状態の設計判断

OVERLOADED状態はDOWNとは異なり、可用性計算では「稼働中」として扱います。しかしエラーレートには加算されます。これはGoogleのSLI設計に倣ったもので、「リクエストは受け付けるがエラーを返す」状態を正確にモデル化しています。

## まとめ

### v4.1で解決した課題

| v4.0の課題 | v4.1の解決 |
|-----------|-----------|
| 単一パラメータのみ | マルチパラメータWhat-if（任意の組み合わせ） |
| トラフィック因子が無効 | 過負荷検出（OVERLOADED状態追加） |
| MTBF因子が無効 | ゼロ値の事前populate修正 |
| レプリカ因子が無効 | メトリクス逆比例調整 |
| デモインフラが非現実的 | 適切なプロビジョニング（30-34%利用率） |

### 全修正のインパクト

```
v4.0（修正前）:
  Baseline: 59% availability ← 過剰なoverload検出
  MTBF sweep: 全値同じ ← ゼロ値バグ
  replica sweep: 全値同じ ← ratio=1.0バグ

v4.1（修正後）:
  Baseline: 99.91% availability ✅
  MTBF sweep: 0.05x=99.60%(6件障害) → 1.0x=99.90%(0件) ✅
  replica sweep: 0.5x=97.85% → 1.0x=99.90% ✅
  traffic sweep: breakpoint 1.5x ✅
  maint sweep: breakpoint 2.0x ✅
  multi-param: 5シナリオ全て差別化 ✅
```

### 次の課題（v4.2ロードマップ）

1. **MTTR感度の改善** — 現在MTTRが効かない（障害自体が少ないため）。障害+MTTR複合スイープが必要
2. **OVERLOADED → 部分可用性** — 現在OVERLOADEDは可用性100%カウントだが、実際は50%程度にすべき
3. **オートスケーリング連動** — トラフィック増加時のオートスケーリングが過負荷検出に追いつくかの検証
4. **コスト最適化分析** — レプリカ数と可用性のパレート最適解を自動探索
