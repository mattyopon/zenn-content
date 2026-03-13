---
title: "XClone v2.13: InfraSim v4.0 What-if Analysis & Capacity Planning — SLOブレークポイント分析"
emoji: "📊"
type: "tech"
topics: ["infrasim", "sre", "capacityplanning", "slo", "infrastructure"]
published: false
---

## はじめに

前回の[v2.12記事](https://qiita.com/ymaeda_it/items/)では、**InfraSim v3.1/v3.2**でローリングデプロイ・ティア別メンテナンス・自動復旧を導入し、**全5シナリオでSLO 99.9%を達成**しました。

しかし、達成後すぐに新たな問いが生まれました。

- **「MTTRが2倍になったらSLOは維持できる？」**
- **「トラフィックが5倍に急増したら？」**
- **「DBは何ヶ月後にキャパシティ上限に達する？」**

v3.2までのInfraSimは「今の状態」をシミュレートするツールでした。しかし実際のSREに必要なのは、**「条件が変わったらどうなるか」を事前に知る力**です。

v4.0では2つの新エンジンを追加しました。

1. **What-if Analysis（WhatIfEngine）** — 5つのパラメータを掃引し、SLOが破綻するブレークポイントを特定
2. **Capacity Planning（CapacityPlanningEngine）** — 成長率に基づくキャパシティ予測とError Budget消費予測

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
| **14** | **v2.13 -- What-if & Capacity Planning（本記事）** | **InfraSim v4.0 / パラメトリックスイープ / SLOブレークポイント / 成長予測** |

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

v4.0 (v2.13, 本記事): What-if & Capacity Planning  ← NEW
  ├ What-if Analysis（5パラメータのパラメトリックスイープ）
  ├ SLOブレークポイント検出
  ├ Capacity Planning（成長率ベースのキャパシティ予測）
  ├ Error Budget消費予測
  └ infrasim whatif / infrasim capacity CLI
```

## v4.0 新機能アーキテクチャ

v4.0では2つの新しいエンジンと、対応するCLIコマンドを追加しました。

```
src/infrasim/
├── simulator/
│   ├── ops_engine.py           # v3.x 運用シミュレーション（既存）
│   ├── whatif_engine.py         # v4.0 What-if Analysis ← NEW
│   └── capacity_engine.py       # v4.0 Capacity Planning ← NEW
├── cli.py                       # infrasim whatif / capacity コマンド追加
└── model/
    └── components.py            # コンポーネントモデル（既存）
```

### アーキテクチャ概要

```
                    ┌──────────────────────────┐
                    │       infrasim CLI        │
                    │  whatif / capacity コマンド │
                    └─────────┬────────────────┘
                              │
              ┌───────────────┼───────────────┐
              │               │               │
    ┌─────────▼──────┐  ┌────▼──────────┐   │
    │  WhatIfEngine   │  │ CapacityPlan  │   │
    │                 │  │ ningEngine    │   │
    │ 5パラメータ掃引 │  │ 成長率予測    │   │
    │ SLOブレーク     │  │ Error Budget  │   │
    │ ポイント検出    │  │ 消費予測      │   │
    └───────┬─────────┘  └───┬───────────┘   │
            │                │               │
            └────────┬───────┘               │
                     │                       │
            ┌────────▼──────────┐            │
            │  OpsSimulation    │            │
            │  Engine (v3.x)    │◄───────────┘
            │  7日間運用sim     │
            │  MTBF/MTTR/劣化   │
            └────────┬──────────┘
                     │
            ┌────────▼──────────┐
            │   InfraGraph      │
            │  45コンポーネント  │
            └───────────────────┘
```

**WhatIfEngine** は各パラメータの値ごとにグラフのディープコピーを作成し、OpsSimulationEngineで7日間シミュレーションを繰り返します。**CapacityPlanningEngine** はコンポーネントの利用率と成長率から数学的にキャパシティ到達時期を予測し、オプションでopsシミュレーションからError Budget burn rateを算出します。

### What-if分析の掃引パラメータ

| パラメータ | 説明 | 掃引値例 |
|-----------|------|---------|
| `mttr_factor` | 復旧時間の倍率 | 0.25, 0.5, 1.0, 2.0, 4.0 |
| `mtbf_factor` | 障害間隔の倍率 | 0.25, 0.5, 1.0, 2.0, 4.0 |
| `traffic_factor` | トラフィックピークの倍率 | 1.0, 1.5, 2.0, 3.0, 5.0 |
| `replica_factor` | レプリカ数の倍率 | 0.5, 0.75, 1.0, 1.25, 1.5 |
| `maint_duration_factor` | メンテナンス時間の倍率 | 0.5, 1.0, 2.0, 3.0, 5.0 |

## 実装時に発見した課題と修正（7件）

v4.0の実装は3つのエージェント（CLI担当・WhatIfEngine担当・CapacityEngine担当）が並行開発しました。結合時に発見された7件の課題とその修正を記録します。

### 3.1 CLIとエンジンのAPI不整合

3つのエージェントが並行でCLI・WhatIfEngine・CapacityEngineを開発した結果、**CLIのメソッド呼び出しがエンジンの実際のAPIと一致しない**問題が多数発生しました。

**What-if側の不整合:**

```python
# CLI（当初の実装）
engine.run_whatif(parameter, values)  # 引数直渡し

# エンジンの実際のAPI
engine.run_whatif(WhatIfScenario(...))  # Pydanticモデルを渡す
```

**Capacity Planning側の不整合:**

```python
# CLI（当初の実装）
engine.plan()  # メソッド名が違う

# エンジンの実際のAPI
engine.forecast()                    # 静的分析
engine.forecast_with_simulation()    # opsシミュレーション付き
```

フィールド名の不一致も多数ありました:

| CLI側 | エンジン側 | 修正 |
|-------|----------|------|
| `entries` | `values` | `values` に統一 |
| `breakpoint` | `breakpoint_value` | `breakpoint_value` に統一 |
| `result.availability` | `result.avg_availabilities` | リストとして参照 |

**教訓**: 並行開発では**インターフェース契約（API contract）を先に定義**すべきです。Pydanticモデルの定義を先に共有し、CLIとエンジンの両方がそれに準拠する形にすれば、結合時の手戻りを防げます。

### 3.2 メンテナンス時間ファクターが無効

What-if分析で `maint_duration_factor=0.5`（メンテナンス時間半減）を設定すると、**可用性が改善ではなく悪化する**異常な結果が出ました。

```
maint_duration_factor=0.5 → 99.89%（改善のはずが悪化？）
maint_duration_factor=1.0 → 99.92%（ベースライン）
```

**原因**: `ops_engine.py` がメンテナンス時間を計算する際、コンポーネントの `operational_profile.maintenance_downtime_minutes` を無視し、**モジュール定数 `_DEFAULT_MAINT_SECONDS` を直接使用**していました。

```python
# ops_engine.py（修正前）
# _DEFAULT_MAINT_SECONDS を常に使い、プロファイルの値を無視
maint_seconds = _DEFAULT_MAINT_SECONDS.get(comp_type, 3600)
```

What-ifエンジンがプロファイルの値を変更しても、ops_engineはそれを参照しないため効果がありませんでした。

**修正**: `OpsScenario` に `maintenance_duration_factor` フィールドを追加し、`_DEFAULT_MAINT_SECONDS` にファクターを乗算する方式に変更しました。

```python
# ops_engine.py（修正後）
# src/infrasim/simulator/ops_engine.py L1154-L1161
maint_factor = scenario.maintenance_duration_factor
base_duration = _DEFAULT_MAINT_SECONDS.get(comp_type, 3600)
maint_duration = int(base_duration * maint_factor)
```

### 3.3 MTBF/MTTRファクター無効化問題

What-if分析で `mttr_factor=2.0` や `mtbf_factor=0.5` を設定しても、**一部のコンポーネントでまったく効果がない**問題が発生しました。

**原因**: 多くのコンポーネントのoperational_profileで `mtbf_hours=0` / `mttr_minutes=0` がデフォルト値になっており:

```
0 × factor = 0  →  デフォルト値にフォールバック  →  factor変更の効果なし
```

What-ifエンジンが `comp.operational_profile.mttr_minutes *= factor` を実行しても、`0 * 2.0 = 0` のためops_engineがデフォルト値を使い、実質的にfactor=1.0と同じ結果になります。

**修正**: `_schedule_events` でランダム障害を生成する前に、ゼロ値をタイプ別デフォルトで**プリポピュレート**する処理を追加しました。

```python
# src/infrasim/simulator/ops_engine.py L1104-L1114
# Pre-populate zero profile values with type-based
# defaults so What-if factor modifications take effect
# (0 * factor = 0, so we need a real base value).
if comp.operational_profile.mtbf_hours <= 0:
    comp.operational_profile.mtbf_hours = (
        _DEFAULT_MTBF_HOURS.get(comp_type, 2160.0)
    )
if comp.operational_profile.mttr_minutes <= 0:
    comp.operational_profile.mttr_minutes = (
        _DEFAULT_MTTR_MINUTES.get(comp_type, 30.0)
    )
```

これにより、What-ifでファクターを乗算する前にベース値が確実に非ゼロになり、掃引の効果が反映されるようになりました。

### 3.4 What-if結果の非決定性

同じパラメータ値で複数回実行すると**結果が異なる**問題が発覚。さらに深刻なのは、`maint_duration_factor=0.5`（メンテナンス半減）がベースラインより**悪い結果**を示す場合がありました。

**原因**: 各スイープ値でシミュレーションを実行するたびに、`_ops_rng`（モジュールレベルの乱数生成器）の状態が消費され、**次のスイープでは異なるランダムイベント列**が生成されていました。

```
factor=0.5 → ランダム障害3件（たまたま多い）→ 99.89%
factor=1.0 → ランダム障害1件（たまたま少ない）→ 99.92%
```

パラメータの影響ではなく、**ランダムノイズが結果を支配**していました。

**修正**: `WhatIfScenario` に `seed=42` フィールドを追加し、各スイープ値の実行前に `_ops_rng` を**同じシードでリセット**するようにしました。

```python
# src/infrasim/simulator/whatif_engine.py L182-L183
# Reset the module-level RNG to ensure identical random
# event sequences across sweep values, making results
# truly comparable.
ops_engine_mod._ops_rng = random.Random(whatif.seed)
```

これにより、全スイープ値で**同一のランダムイベント列**が生成され、パラメータ変更の影響だけを純粋に比較できるようになりました。

### 3.5 メンテナンス時間リグレッション（最も深刻）

3.2の修正（プロファイルからメンテナンス時間を読む）を適用したところ、**全シナリオがSLO FAILに転落**しました。

```
修正前: ops-7d-full = 99.92% (PASS)
修正後: ops-7d-full = 99.37% (FAIL)  ← 大幅悪化！
```

**原因**: `Component.operational_profile.maintenance_downtime_minutes` のPydanticデフォルト値が `60.0` でした。これは「60分」を意味し:

```
app_serverのメンテナンス時間:
  旧: _DEFAULT_MAINT_SECONDS["app_server"] = 60秒
  新: operational_profile.maintenance_downtime_minutes = 60.0 → 3600秒

60倍の延長！
```

全コンポーネントのメンテナンスが60倍に延長されたため、可用性が壊滅しました。

**修正**: `_DEFAULT_MAINT_SECONDS` を**常に使用**する方式に戻し、ファクター制御は `OpsScenario.maintenance_duration_factor` フィールド経由で行う設計に変更しました。

```python
# src/infrasim/simulator/ops_engine.py L1158-L1161
base_duration = _DEFAULT_MAINT_SECONDS.get(comp_type, 3600)
maint_duration = int(base_duration * maint_factor)
```

プロファイルの値は参照せず、検証済みのモジュール定数をベースにファクターを適用する安全な設計です。

### 3.6 Capacity Planning利用率の未分化

Capacity Planningの最初の実装では、全コンポーネントの利用率が**デフォルト30%**（または実測値の5-8%）で均一に報告されていました。

```
aurora-primary:    8% (database)   ← 本来もっと高いはず
app-server-01:    5% (app_server) ← 非現実的
redis-primary:    7% (cache)      ← 全部似たような値
```

実測メトリクスがないシミュレーション環境では、コンポーネントタイプに関わらず同じデフォルト値が使われるため、**DBとLBが同じ利用率**という非現実的な結果になります。

**修正**: タイプ別の利用率推定テーブルを導入し、レプリカ数による補正も追加しました。

```python
# src/infrasim/simulator/capacity_engine.py L30-L38
_DEFAULT_TYPE_UTILIZATION: dict[str, float] = {
    "app_server": 45.0,      # 中程度の利用率
    "web_server": 40.0,      # 同上だがやや低め
    "database": 55.0,        # DBは高利用率で稼働
    "cache": 35.0,           # キャッシュは余裕を持つ設計
    "load_balancer": 25.0,   # LBはバースト対応で過剰プロビジョニング
    "queue": 30.0,           # キューは変動大
    "proxy": 30.0,           # プロキシは軽量
}
```

さらに、レプリカ数による補正:

```python
# src/infrasim/simulator/capacity_engine.py L271-L276
if comp.replicas == 1:
    base += 10.0  # 単一障害点、高負荷で稼働
elif comp.replicas >= 5:
    base -= 5.0   # 負荷分散が効いている
```

10%未満の実測値は非現実的と判断し、タイプ別デフォルトにフォールバックする閾値を設定しました。

### 3.7 Error Budget計算の誤り

Capacity Planningのシミュレーション付き予測で、Error Budget消費が**509%**という異常値を返していました。

**原因**: `total_downtime_seconds`（全コンポーネントのダウンタイム合計）をサービスレベルのダウンタイムとして使用していました。

```
例: 3コンポーネントが同時に各100秒ダウン
  total_downtime_seconds = 300秒（合計）
  実際のサービス劣化 = 100秒（同時発生）
```

**修正**: SLIタイムラインの**平均可用性**からburn rateを計算する方式に変更:

```python
# capacity_engine.py（修正後）
avg_avail = sum(p.availability_percent for p in result.sli_timeline) / len(...)
unavail_fraction = (100.0 - avg_avail) / 100.0
service_downtime_minutes = unavail_fraction * total_sim_minutes
```

修正後の結果:

| 指標 | 修正前 | 修正後 |
|------|--------|--------|
| 消費率 | 509% | 15.9% |
| Burn rate | 31.4 min/day | 0.98 min/day |
| ステータス | exhausted | warning |

## What-if分析結果

`infrasim whatif --defaults` で5つのパラメータすべてを掃引した結果です。ベースシナリオは**7日間フル運用シミュレーション**（デプロイ・メンテナンス・ランダム障害・劣化すべて有効、seed=42で再現性確保）。

### MTTR Factor（復旧時間）

| Factor | Avg Avail | SLO |
|--------|-----------|-----|
| 0.25 | 99.9284% | PASS |
| 0.50 | 99.9229% | PASS |
| 1.00 | 99.9130% | PASS |
| 2.00 | 99.8931% | FAIL |
| 4.00 | 99.8535% | FAIL |

**Breakpoint: `mttr_factor=2.0`**

MTTRが2倍になるだけでSLOが破綻します。復旧時間の短縮が**最も費用対効果の高い投資**であることを数値で証明しました。

### MTBF Factor（障害間隔）

全値（0.25〜4.0）でPASS。

7日間のシミュレーション期間では、MTBF（平均90〜365日）に対して期間が短すぎるため、障害発生確率の変動が結果に大きく影響しません。30日シミュレーションでは差が出る可能性があります。

### Traffic Factor（トラフィック倍率）

| Factor | Avg Avail | SLO |
|--------|-----------|-----|
| 1.00 | 99.9130% | PASS |
| 3.00 | 99.9130% | PASS |
| 5.00 | 98.5644% | FAIL |

**Breakpoint: `traffic_factor=5.0`**

3倍までは耐えられるが、5倍で大幅に破綻。バイラルイベントやメディア露出による急激なトラフィック増加への対策が必要です。

### Replica Factor（レプリカ倍率）

全値（0.5〜1.5）でPASS。

レプリカを半分に減らしても（`factor=0.5`）SLOを維持できました。これは**過剰プロビジョニングの可能性**を示唆しており、コスト最適化の余地があります。

### Maintenance Duration Factor（メンテナンス時間倍率）

| Factor | Avg Avail | SLO |
|--------|-----------|-----|
| 0.50 | 99.9350% | PASS |
| 1.00 | 99.9130% | PASS |
| 2.00 | 99.8667% | FAIL |
| 3.00 | 99.8204% | FAIL |
| 5.00 | 99.7279% | FAIL |

**Breakpoint: `maint_duration_factor=2.0`**

メンテナンス時間が2倍になるとSLO破綻。逆に `factor=0.5` で99.935%まで改善しており、**Blue-Greenデプロイやゼロダウンタイムメンテナンス**の導入効果を定量的に示しています。

### What-ifブレークポイントサマリー

```
┌──────────────────────────┬────────────┬───────────────────┐
│ パラメータ                │ Breakpoint │ 感度              │
├──────────────────────────┼────────────┼───────────────────┤
│ mttr_factor              │ 2.0        │ 高（即FAIL）      │
│ mtbf_factor              │ なし       │ 低（7日間では）   │
│ traffic_factor           │ 5.0        │ 中（3xまで安全）  │
│ replica_factor           │ なし       │ 低（過剰余裕あり）│
│ maint_duration_factor    │ 2.0        │ 高（即FAIL）      │
└──────────────────────────┴────────────┴───────────────────┘
```

## Capacity Planning結果

`infrasim capacity --growth 0.10 --slo 99.9` で、月間10%成長を想定したキャパシティ予測を実行しました。

### コンポーネント予測概要

```
Capacity Plan: 45 components analysed.
  Urgency: 0 critical, 4 warning, 41 healthy.
  First bottleneck: aurora-primary.
  Error budget (99.9% SLO): 0.0% consumed, status=healthy.
  Estimated 3-month cost increase: 38.5%.
```

### 主要コンポーネントの予測

| コンポーネント | タイプ | 利用率 | 80%到達 | 現在 | 3ヶ月後 | Urgency |
|---------------|--------|--------|---------|------|---------|---------|
| aurora-primary | database | 65% | 2.2ヶ月 | 2 | 3 | **WARNING** |
| aurora-replica-1 | database | 65% | 2.2ヶ月 | 2 | 3 | **WARNING** |
| aurora-replica-2 | database | 65% | 2.2ヶ月 | 2 | 3 | **WARNING** |
| app-server-* | app_server | 53% | 4.4ヶ月 | 33 | 46 | WARNING |
| redis-primary | cache | 35% | 8.7ヶ月 | 2 | 2 | healthy |
| alb-main | load_balancer | 25% | 12.2ヶ月 | 2 | 2 | healthy |
| sqs-* | queue | 30% | 10.3ヶ月 | 2 | 2 | healthy |

**Databaseが最初のボトルネック**: 利用率65%で月10%成長の場合、**2.2ヶ月後にキャパシティ上限（80%）に到達**します。Aurora read replicaの追加が最優先です。

### 利用率推定ロジック

実メトリクスがない場合のタイプ別推定値と、その根拠:

```python
_DEFAULT_TYPE_UTILIZATION = {
    "database": 55.0,        # + 10.0（replica=1時）= 65%
    "app_server": 45.0,      # + 補正なし = 45%〜53%
    "cache": 35.0,           # キャッシュは余裕設計
    "load_balancer": 25.0,   # バースト対応で過剰プロビジョニング
    "queue": 30.0,           # 非同期処理はピーク吸収
}
```

Databaseはデータ量増加の影響を直接受けるため高く、Load Balancerはステートレスで水平スケールしやすいため低く設定しています。

### コスト増予測

3ヶ月後のスケーリングに必要なコスト増: **38.5%**

これは主にapp_server群のレプリカ増（33→46台）とDBレプリカ追加によるものです。

## Error Budget分析

### SLO 99.9%のError Budget

```
SLO Target:       99.9%
月間バジェット:     43.2分（30日 × 24時間 × 0.1%）
```

### シミュレーション付きError Budget予測（`--simulate`）

`infrasim capacity --simulate` で7日間のopsシミュレーションからburn rateを算出した結果:

| 指標 | 値 |
|------|-----|
| Burn rate | **0.98分/日** |
| 7日間消費 | 6.9分（15.9%） |
| 予測月間消費 | **68.3%** |
| 枯渇まで | 36.9日 |
| ステータス | **warning** |

月間バジェット43.2分に対し、現在のburn rateでは68.3%を消費する見込み。SLOは維持できますが、**1件の大きなインシデントでバジェットが枯渇するリスク**があります。

### シナリオ別結果

| シナリオ | 期間 | 可用性 | SLO | 状態 |
|---------|------|--------|-----|------|
| ops-7d-baseline | 7日 | 100.00% | PASS | ベースライン |
| ops-7d-with-deploys | 7日 | 99.98% | PASS | デプロイ影響 |
| ops-7d-full | 7日 | 99.91% | PASS | フル運用 |
| ops-14d-growth | 14日 | 99.91% | PASS | 成長トレンド |
| ops-30d-stress | 30日 | 99.90% | FAIL(-0.004%) | ストレス限界 |

30日ストレステスト（3.5xピーク、15%成長、17件障害）で0.004%のみSLO未達。極限条件下でのマージンの薄さを示す結果ですが、これは意図的に厳しいシナリオです。

Error Budgetの薄さは、**1件の予期しないインシデントでSLO違反になるリスク**を意味します。What-if分析でMTTR 2.0xがbreakpointだった結果と一致しています。

## 発見したインサイト

### 1. MTTRが最も敏感なパラメータ

MTTRを2倍にするだけでSLOが即座に破綻します（99.913%→99.893%）。これは「障害を防ぐ」よりも**「素早く復旧する」ことの方がSLOへの影響が大きい**ことを示しています。

**アクション**: 復旧自動化（Auto-remediation）、Runbookの整備、オンコール対応訓練に投資すべきです。

### 2. メンテナンス窓の最適化余地

`maint_duration_factor=0.5` で可用性が99.935%まで改善。現在のメンテナンス窓を半分にできれば、Error Budgetに**14分の余裕**が生まれます。

**アクション**: Blue-Greenデプロイ、ローリングアップデートの高速化、メンテナンス手順の自動化。

### 3. トラフィック5倍がクリティカルライン

3倍トラフィックまでは可用性に影響なし。しかし5倍で98.56%まで急落。これは**非線形な崩壊パターン**を示しており、「4倍までは大丈夫」と安心していると危険です。

**アクション**: CDN強化、レートリミッティング、オートスケーリングのmax_replicasを現在の3倍以上に設定。

### 4. DBがボトルネック

Capacity Planningの結果、DBが**2.2ヶ月以内にキャパシティ上限に到達**します。他のコンポーネントは8-12ヶ月の余裕があるため、DBのスケーリングが**最も緊急**です。

**アクション**: Aurora read replicaの追加、クエリ最適化、読み取りのキャッシュ層へのオフロード。

### 5. レプリカ半減でもSLO維持

`replica_factor=0.5` でもSLOを維持できた事実は、**過剰プロビジョニング**の可能性を示唆しています。ただし、これはWhat-if分析の1パラメータ変更の結果であり、MTTRやトラフィックが同時に悪化する場合は別です。

**アクション**: コスト最適化の検討対象として、レプリカ数の段階的削減をテスト。ただし他パラメータの組み合わせ分析が必要。

## CLIの使い方

### What-if Analysis

```bash
# デフォルトの5パラメータ全掃引
infrasim whatif --model infrasim-model.json --defaults

# 特定パラメータの掃引
infrasim whatif --model infrasim-model.json \
  --parameter mttr_factor \
  --values "0.25,0.5,1.0,2.0,4.0"

# YAMLモデルからの実行
infrasim whatif --yaml infrasim-model.yaml --defaults
```

### Capacity Planning

```bash
# デフォルト（月10%成長、SLO 99.9%）
infrasim capacity --model infrasim-model.json

# カスタム成長率
infrasim capacity --model infrasim-model.json \
  --growth 0.20 \
  --slo 99.95

# opsシミュレーション付き（実際のburn rateを算出）
infrasim capacity --model infrasim-model.json --simulate
```

## v4.0 → v4.1 に向けたロードマップ

v4.0でパラメトリックスイープとキャパシティ予測の基盤は整いました。次のステップとして:

1. **実メトリクス連携（Prometheus/CloudWatch）** — 現在はタイプ別推定値を使用しているため、実際のメトリクスを取得して予測精度を向上
2. **AI駆動シナリオ生成** — LLMによるカオスシナリオの自動提案（「過去のインシデントパターンに基づくWhat-ifシナリオ生成」）
3. **Multi-Regionシミュレーション** — リージョン間フェイルオーバーのWhat-if分析
4. **Error Budget burn rateのリアルタイム追跡** — 時系列でのburn rate推移と、SLO違反までの予測残日数

## まとめ

InfraSim v4.0のWhat-if AnalysisとCapacity Planningにより、**「今のインフラは安全か」だけでなく「いつ、何が原因で破綻するか」を事前に把握**できるようになりました。

```
v4.0で得られた定量的知見:

1. MTTR 2.0x → SLO FAIL（最も敏感なパラメータ）
2. Traffic 5.0x → SLO FAIL（非線形崩壊）
3. Maintenance 2.0x → SLO FAIL（窓の最適化余地あり）
4. DB → 2.2ヶ月でキャパシティ到達（最優先スケーリング対象）
5. Replica 0.5x → SLO PASS（過剰プロビジョニングの可能性）
6. 3ヶ月後のコスト増 → 38.5%
```

実装過程で発見された7件の課題（API不整合・メンテナンスファクター無効・MTBF/MTTRゼロ値・非決定性・リグレッション・利用率未分化・Error Budget計算誤り）は、**並行開発における結合テストの重要性**と**シミュレーションの正確性を検証する難しさ**を改めて示しました。特に3.5のリグレッション（Pydanticデフォルト値による60倍延長）は、「修正したはずが壊れた」という典型的なパターンであり、**変更前後の結果比較を必ず行う**教訓を得ました。
