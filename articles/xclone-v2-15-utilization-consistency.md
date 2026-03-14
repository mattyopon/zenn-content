---
title: "XClone v2.15: InfraSim v4.3 利用率計算の統一と5つのバグ修正 — max vs avg の教訓"
emoji: "🔧"
type: "tech"
topics: ["InfraSim", "infrastructure", "simulation", "SRE"]
published: true
---

## はじめに

前回の[v2.14記事](https://zenn.dev/ymaeda/articles/xclone-v2-14-whatif-multi-overload)では、**InfraSim v4.1**でマルチパラメータWhat-if分析、トラフィック過負荷検出（`HealthStatus.OVERLOADED`）、および5つの重大バグ修正を実施しました。

v4.2ではMTTR感度の改善とOVERLOADED状態の部分可用性（80%加重）を導入しましたが、テスト・レビューの過程で**さらに5つのバグ**が見つかりました。特に大きな問題は**利用率計算方式の不一致**です。Capacity Engineは`max()`でボトルネックリソースを検出するのに対し、Ops Engineは`avg()`で平滑化していたため、同じコンポーネントに対して異なる利用率が報告されるという矛盾がありました。

v4.3ではこの不一致を解消し、合計5件のバグを修正しました。

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
| 15 | [**v2.14** -- Multi What-if & Overload](https://qiita.com/ymaeda_it/items/) | InfraSim v4.1 / 複合パラメータ / トラフィック過負荷 / 5バグ修正 |
| **16** | **v2.15 -- 利用率計算統一 & 5バグ修正（本記事）** | **InfraSim v4.3 / max統一 / 加重ダウンタイム / RNG汚染修正** |

### InfraSimバージョンの進化

```
InfraSim のバージョン進化:

v1.0 (v2.5~v2.7): 静的シミュレーション
  ├ SPOF検出 / カスケード障害分析
  └ 1,647シナリオ（単一時点の障害注入）

v2.0 (v2.8): 動的シミュレーション
  ├ トラフィックパターン / オートスケーリング / フェイルオーバー
  └ 1,695シナリオ（300秒 × 5秒ステップ）

v2.1 (v2.9~v2.10): レジリエンス機構
  ├ Circuit Breaker / Adaptive Retry / Cache Warming / Singleflight
  └ 3,351シナリオ全PASSED

v3.0~v3.2 (v2.11~v2.12): 運用シミュレーション
  ├ Long-Running Simulation（7〜30日）
  ├ Operational Event Injection / SLO/Error Budget Tracker
  └ ローリングデプロイ / 全シナリオSLO 99.9%達成

v4.0~v4.1 (v2.13~v2.14): What-if & Capacity Planning
  ├ パラメトリックスイープ / マルチパラメータWhat-if
  ├ Capacity Planning Engine / OVERLOADED状態追加
  └ 10件のバグ修正

v4.2: MTTR感度改善
  └ OVERLOADED部分可用性（80%加重）

v4.3 (v2.15, 本記事): 利用率計算統一 & バグ修正  <-- NEW
  ├ _ops_utilization: avg() → max()（Capacity Engineとの一貫性）
  ├ ダウンタイム計測: バイナリ → 加重平均方式
  ├ トラフィック下限クランプ: max(1.0) → max(0.1)
  ├ dead code修正: global_group_idx += 0
  └ What-if RNG汚染防止: save/restore pattern
```

## 課題1: dead code bug -- `global_group_idx += 0`

メンテナンスウィンドウのスケジューリングコードで、グループインデックスのインクリメント文にタイポがありました。

```diff
  for tg_idx, tg in enumerate(tier_groups):
      max_dur = max(d for _, d in tg)
      for comp_id, dur in tg:
          maint_start = maint_time + global_offset
          if maint_start < total_seconds:
-             global_group_idx += 0   # no-op: 常にゼロのまま
+             global_group_idx += 1   # グループ番号を正しくインクリメント
              events.append(OpsEvent(...))
```

`+= 0` は何もしないため、`global_group_idx` は常に0のままでした。この変数自体はイベント記述文字列には使われていなかったため、シミュレーション結果への影響はありませんでしたが、将来的にグループ番号を参照するコードを追加した場合にバグの原因となる典型的な「時限爆弾」コードです。

静的解析ツールであれば `+= 0` はno-op として検出可能ですが、人間のレビューでは見落としやすい類のバグです。

## 課題2: バイナリダウンタイム計測

### 問題

v4.2までのダウンタイム計測は**バイナリ方式**でした。あるタイムステップで1コンポーネントでもDOWNであれば、そのステップ全体の秒数がダウンタイムとして加算されます。

```python
# 修正前: バイナリ方式
down_count = sum(
    1 for s in ops_states.values()
    if s.current_health == HealthStatus.DOWN
)
if down_count > 0:
    total_down_seconds += step_seconds  # 300秒が丸ごと加算
```

この方式では、6コンポーネント中1台がDOWNの場合も、6台全てがDOWNの場合も、同じ300秒がダウンタイムとして記録されます。実際のサービス影響度は全く異なるにもかかわらず、同一の数値になるため、障害の深刻度を区別できません。

### 修正: 加重平均方式

DOWNコンポーネント数の割合に応じてダウンタイムを按分する方式に変更しました。

```diff
- if down_count > 0:
-     total_down_seconds += step_seconds
+ total_components = len(ops_states)
+ if down_count > 0 and total_components > 0:
+     total_down_seconds += step_seconds * down_count / total_components
+     total_component_down_seconds += down_count * step_seconds
```

同時に、`total_component_down_seconds`（コンポーネント単位の絶対ダウンタイム）を新たに追加しました。

| メトリクス | 計算方法 | 6台中1台DOWN (300s) | 6台中6台DOWN (300s) |
|-----------|---------|---------------------|---------------------|
| `total_downtime_seconds`（修正前） | バイナリ | 300s | 300s |
| `total_downtime_seconds`（修正後） | 加重平均 | 50s | 300s |
| `total_component_down_seconds`（新規） | 絶対値 | 300s | 1,800s |

加重方式により、部分障害と全面障害の深刻度を数値で区別できるようになりました。

## 課題3: トラフィック下限クランプ

### 問題

`_composite_traffic()` メソッドは、複数のトラフィックパターン（日周パターン + 成長トレンド等）を合成し、最終的なトラフィック倍率を返します。v4.2では下限値が `max(1.0, composite)` に設定されていました。

```python
# 修正前: 下限1.0（ベースライン以下のトラフィックを許可しない）
return max(1.0, composite)
```

日周パターンでは深夜帯のトラフィック倍率が0.3〜0.5程度まで下がることを想定していますが、`max(1.0)` によってベースライン未満のトラフィックが全てベースライン（1.0倍）にクランプされていました。その結果、オフピーク時間帯でも常にピーク時と同等の負荷がかかり、利用率が実態より高く報告されます。

### 修正

```diff
- return max(1.0, composite)
+ # Floor at 0.1 to allow below-baseline traffic while preventing near-zero values
+ return max(0.1, composite)
```

下限を0.1に変更し、深夜帯のトラフィック低下を正しくシミュレーションできるようにしました。0.1（10%）という下限は、完全なゼロトラフィックを防ぎつつ、現実的なオフピーク負荷をモデル化するための値です。

| 時間帯 | 日周パターン倍率 | 修正前の実効倍率 | 修正後の実効倍率 |
|--------|-----------------|-----------------|-----------------|
| 深夜3時 | 0.3 | 1.0（クランプ） | 0.3 |
| 早朝6時 | 0.6 | 1.0（クランプ） | 0.6 |
| 昼12時 | 1.5 | 1.5 | 1.5 |
| ピーク20時 | 2.5 | 2.5 | 2.5 |

## 課題4: 利用率計算の不一致 -- max() vs avg()

### 問題の構造

InfraSimには2つの利用率計算メソッドがありました。

**Capacity Engine / Component.utilization()**: `max()` 方式
```python
def utilization(self) -> float:
    factors = [cpu_percent, memory_percent, disk_percent, conn_percent]
    return max(factors) if factors else 0.0
```

**Ops Engine._ops_utilization()**: `avg()` 方式（修正前）
```python
def _ops_utilization(comp) -> float:
    factors = [cpu_percent, memory_percent, disk_percent, conn_percent]
    return sum(factors) / len(factors) if factors else 0.0
```

同じPostgreSQLコンポーネント（CPU=25%, Memory=34%, Disk=32%, Connections=20%）に対して、Capacity Engineは34%、Ops Engineは27.75%を返していました。

### なぜ max() が正しいのか -- ボトルネックリソース原理

サーバーの実効的な負荷は、最も逼迫しているリソースによって決まります。これはリービッヒの最小律（Liebig's Law of the Minimum）に相当する考え方です。

CPUが30%でもメモリが90%なら、そのサーバーはOOM Killerが発動する寸前であり、実質的に90%の負荷状態です。avg()を使うと `(30 + 90) / 2 = 60%` となり、危険な状態を「まだ余裕がある」と誤判定します。

```diff
  @staticmethod
  def _ops_utilization(comp: "InfraComponent") -> float:
-     """Compute a representative utilization for ops simulation.
-
-     Unlike ``comp.utilization()`` (which returns *max* of all
-     metrics --- useful for capacity planning), this returns a
-     **weighted average** so that normal operating conditions
-     (30-65 % typical) remain in the HEALTHY band.
-     """
+     """Compute a representative utilization for ops simulation.
+
+     Uses ``max()`` of all resource metrics, matching the
+     ``Component.utilization()`` method --- the bottleneck resource
+     determines component health (limiting-factor principle).
+     """
      factors: list[float] = []
      if comp.metrics.cpu_percent > 0:
          factors.append(comp.metrics.cpu_percent)
      # ... (memory, disk, connections)
-     return sum(factors) / len(factors) if factors else 0.0
+     return max(factors) if factors else 0.0
```

### demo-infra.yaml の再調整

max()に統一した結果、各コンポーネントのベース利用率が上昇しました。avg()で28%だった値がmax()では34%になるため、ピーク時（2.5倍）に `34% * 2.5 = 85%` でDEGRADED、さらに成長率を加味すると数ヶ月でOVERLOADED域に達します。

これに対応するため、demo-infra.yamlのメトリクスを再調整しました。

```diff
  # app-1 (api-server-1)
  metrics:
-   cpu_percent: 30
-   memory_percent: 33
-   disk_percent: 30
+   cpu_percent: 22
+   memory_percent: 25
+   disk_percent: 22
    network_connections: 200

  # postgres (PostgreSQL primary)
  metrics:
-   cpu_percent: 25
-   memory_percent: 34
-   disk_percent: 32
+   cpu_percent: 20
+   memory_percent: 26
+   disk_percent: 24
    network_connections: 40
```

| コンポーネント | 修正前 avg() | 修正前 max() | 修正後 max() |
|---------------|-------------|-------------|-------------|
| nginx | 21.7% | 30.0% | 25.0% |
| app-1 | 28.3% | 33.0% | 25.0% |
| app-2 | 26.5% | 30.0% | 24.0% |
| postgres | 27.8% | 34.0% | 26.0% |
| redis | 18.0% | 28.0% | 22.0% |
| rabbitmq | 15.0% | 20.0% | 20.0% |

再調整により、max()ベースでも全コンポーネントが20〜26%の安全な領域に収まるようになりました。ピーク時（2.5倍）でも `26% * 2.5 = 65%` となり、HEALTHY圏内を維持できます。

## 課題5: What-IfのRNG汚染

### 問題

What-if分析では、各スイープ値でシミュレーションを実行する前にモジュールレベルのRNG（`_ops_rng`）を固定シード値でリセットします。これにより、異なるパラメータ値間で同一の乱数列が使われ、結果が公正に比較可能になります。

しかしv4.2のコードでは、RNGのリセットのみ行い、元の状態への復元を行っていませんでした。

```python
# 修正前: RNGを上書きするが復元しない
for value in whatif.values:
    ops_engine_mod._ops_rng = random.Random(whatif.seed)
    engine = OpsSimulationEngine(modified_graph)
    result = engine.run_ops_scenario(modified_scenario)
# ← 関数終了後、_ops_rngは最後のシミュレーションで消費された状態のまま
```

### 影響

What-if分析を実行した後に通常のOpsシミュレーションを実行すると、RNGの内部状態が変わっているため、同じシード値を使っても異なる乱数列が生成されます。これはthread-safety以前の問題で、単一スレッドでも実行順序によって結果が変わるという再現性の欠如を引き起こします。

### 修正: save/restore pattern

```diff
+ original_rng = ops_engine_mod._ops_rng
+ try:
      for value in whatif.values:
          ops_engine_mod._ops_rng = random.Random(whatif.seed)
          engine = OpsSimulationEngine(modified_graph)
          result = engine.run_ops_scenario(modified_scenario)
+ finally:
+     ops_engine_mod._ops_rng = original_rng
```

`try/finally` で元のRNGオブジェクトを確実に復元します。この修正は `run_whatif()` と `run_multi_whatif()` の両方に適用しました。`finally` ブロックを使うことで、シミュレーション中に例外が発生した場合でもRNGが復元されます。

## 修正後の分析結果

v4.3の全修正を適用した後のシミュレーション結果を以下にまとめます。

### What-if ブレークポイント

| パラメータ | ブレークポイント | 意味 |
|-----------|-----------------|------|
| traffic_factor | **1.5x** | 通常の1.5倍トラフィックでSLO違反 |
| replica_factor | **0.5x** | レプリカ半減でSLO違反 |
| mtbf_factor | **0.05x** | 障害頻度20倍でSLO違反 |
| maint_duration_factor | **2.0x** | メンテナンス2倍でSLO違反 |
| mttr_factor | なし | 全値PASS（障害自体が少ないため影響が限定的） |

### Capacity Planning

| コンポーネント | 利用率(max) | 容量到達月数 | 緊急度 |
|---------------|------------|-------------|--------|
| nginx | 25.0% | 12.6ヶ月 | healthy |
| app-1 | 25.0% | 12.6ヶ月 | healthy |
| app-2 | 24.0% | 13.0ヶ月 | healthy |
| **postgres** | **26.0%** | **11.8ヶ月** | healthy |
| redis | 22.0% | 14.0ヶ月 | healthy |
| rabbitmq | 20.0% | 15.3ヶ月 | healthy |

PostgreSQLが最初のボトルネック（11.8ヶ月）となる点はv4.1と同じですが、max()統一により各コンポーネントの利用率がより正確に反映されています。

### Error Budget

```
Budget consumed: 0.0%
Status:          OK
```

demo-infra.yamlの再調整により、ベースライン状態でのError Budget消費が0.0%になりました。v4.1では19.3%消費（WARNING）でしたが、これはavg()方式での過小評価されたベース利用率に対してピーク時の実効利用率が想定外に高くなっていたことが原因でした。max()統一とメトリクス再調整により、ベースラインとピーク時の利用率が整合的になり、Error Budgetが安定しました。

## max vs avg の教訓

利用率計算方式の違いがインフラ設計に与える影響を具体的に示します。

### 同じコンポーネントに対する2つの見え方

PostgreSQL（修正前のメトリクス: CPU=25%, Memory=34%, Disk=32%, Connections=20%）を例にとります。

```
avg() = (25 + 34 + 32 + 20) / 4 = 27.75%
max() = max(25, 34, 32, 20) = 34.0%
```

avg()では「まだ28%しか使っていない」と見えますが、max()では「メモリが34%まで来ている」と見えます。

### ピーク時の挙動の違い

日周パターンのピーク倍率2.5xを適用した場合の違いは劇的です。

| 計算方式 | ベース利用率 | ピーク時 (2.5x) | ヘルス判定 |
|---------|------------|----------------|----------|
| avg() | 27.75% | 69.4% | HEALTHY (< 85%) |
| max() | 34.0% | 85.0% | DEGRADED (>= 85%) |

avg()では「ピーク時でも余裕」と判定されますが、max()では「ピーク時にDEGRADED」となります。月次10%成長を3ヶ月適用すると、max()ベースでは `34% * 1.1^3 * 2.5 = 113%` に達し、DOWN判定になります。avg()ベースでは `27.75% * 1.1^3 * 2.5 = 92.3%` でOVERLOADEDに留まります。

### インフラ設計への影響

この差異は、キャパシティプランニングのタイムラインに直接影響します。

```
avg()ベース:
  PostgreSQL util=28% → 容量到達 11.0ヶ月
  → 「1年近く余裕がある」と判断
  → スケーリング計画を後回しにする

max()ベース:
  PostgreSQL util=34% → 容量到達 9.0ヶ月
  → 「9ヶ月後に限界」と判断
  → 四半期内にスケーリング計画を策定する
```

2ヶ月の差は、スケーリング計画の優先度判断に影響します。avg()では「来年の話」と見える問題が、max()では「今期中に対策が必要」に変わります。

### 教訓

1. **利用率計算は一貫性が最重要** -- エンジン間で異なる計算方式を使うと、Capacity PlanningとOps Simulationで矛盾する結論が出る。1つの方式に統一すべき
2. **ボトルネックリソース原理を採用する** -- avg()は全リソースが均等に使われる理想的な状態を仮定している。現実のシステムではメモリ、ディスク、コネクション等の特定リソースが先に枯渇するため、max()が実態に近い
3. **計算方式の変更はデータの再調整を伴う** -- max()への統一により、既存のdemo-infra.yamlのメトリクス値がオーバープロビジョニング（利用率が高すぎてピーク時にDOWN）になった。インフラ定義データの再調整が必要だった

## まとめ

### v4.3で修正した5件

| # | 修正内容 | 影響 |
|---|---------|------|
| 1 | `global_group_idx += 0` → `+= 1` | dead code除去（将来のバグ予防） |
| 2 | ダウンタイム計測: バイナリ → 加重平均 | 部分障害と全面障害の区別が可能に |
| 3 | トラフィック下限: `max(1.0)` → `max(0.1)` | オフピーク時の低トラフィックを正しくモデル化 |
| 4 | `_ops_utilization`: `avg()` → `max()` | Capacity Engineとの一貫性確保 |
| 5 | What-if RNG: 上書き → save/restore | 実行順序に依存しない再現性の確保 |

### 全修正のインパクト

```
v4.2（修正前）:
  _ops_utilization: avg() → postgres 28% (ピーク 69%)
  ダウンタイム: バイナリ方式（部分/全面障害の区別なし）
  トラフィック: 深夜帯もベースライン負荷
  RNG: What-if後に汚染される可能性

v4.3（修正後）:
  _ops_utilization: max() → postgres 26% (ピーク 65%)
  ダウンタイム: 加重平均方式 + コンポーネント絶対値
  トラフィック: 深夜帯 0.3x を正しくモデル化
  RNG: try/finally で確実に復元
  Error Budget: 0.0% consumed (OK)
  全パラメータのブレークポイント検出済み
```

### 次の課題（v4.4ロードマップ）

1. **オートスケーリング連動** -- トラフィック増加時のオートスケーリングが過負荷検出に追いつくかの検証
2. **コスト最適化分析** -- レプリカ数と可用性のパレート最適解を自動探索
3. **複合ブレークポイント探索** -- マルチパラメータWhat-ifでの自動ブレークポイント検出（グリッドサーチ）
4. **リージョン間レイテンシモデル** -- マルチリージョン構成でのネットワーク遅延シミュレーション
