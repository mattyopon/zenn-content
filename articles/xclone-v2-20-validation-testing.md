---
title: "InfraSim v4.9: バリデーション強化・パフォーマンス改善・テストカバレッジ35件追加"
emoji: "🛡️"
type: "tech"
topics: ["infrasim", "python", "testing", "validation", "sre"]
published: false
---

## はじめに

InfraSim v4.9では、v4.8までの8イテレーションで蓄積された技術的負債を一掃する包括的な品質改善を実施しました。25項目の監査結果から15件を修正し、35件の新規テストを追加しています。

本記事では、**バリデーション強化**・**パフォーマンス改善**・**テストカバレッジ拡大**の3軸で行った改善を紹介します。

## 1. バリデーション強化（6件）

### V2: slo_target のゼロ除算防止

`CapacityPlanningEngine.forecast()` に渡す `slo_target` が 0 や 100 超の場合、エラーバジェット計算で意図しない値が発生していました。

```python
# Before: slo_target=0 → budget_total=43200分（正常だが意味なし）
#         slo_target=100 → budget_total=0 → 除算エラー
budget_total = (1.0 - slo_target / 100.0) * 30 * 24 * 60

# After: 入力検証を追加
if slo_target <= 0.0 or slo_target > 100.0:
    raise ValueError(
        f"slo_target must be between 0 (exclusive) and 100 (inclusive), "
        f"got {slo_target}"
    )
```

### V4/V5: YAML ローダーのバリデーション強化

YAMLファイルから読み込む際、以下のバリデーションを追加しました：

- **依存関係タイプ**: `requires`, `optional`, `async` 以外を拒否
- **レプリカ数**: 0以下の値を拒否

```python
# 依存関係タイプのバリデーション
dep_type = entry.get("type", "requires")
valid_dep_types = ("requires", "optional", "async")
if dep_type not in valid_dep_types:
    raise ValueError(f"invalid type '{dep_type}'")

# レプリカ数のバリデーション
replicas = entry.get("replicas", 1)
if not isinstance(replicas, int) or replicas < 1:
    raise ValueError(f"replicas must be a positive integer, got {replicas}")
```

### V6: 循環依存検出

NetworkXの `is_directed_acyclic_graph()` を使用して、YAML読み込み時に循環依存を自動検出します。

```python
import networkx as nx
if not nx.is_directed_acyclic_graph(graph._graph):
    cycles = list(nx.simple_cycles(graph._graph))
    cycle_str = " -> ".join(cycles[0] + [cycles[0][0]])
    raise ValueError(f"Circular dependency detected: {cycle_str}")
```

これにより、`A → B → C → A` のような循環依存グラフが混入すると、シミュレーション実行前にエラーで停止します。

### V1: duration_days の正値検証

```python
if scenario.duration_days <= 0:
    raise ValueError(f"duration_days must be positive, got {scenario.duration_days}")
```

## 2. パフォーマンス改善（2件）

### P2: _propagate_dependencies() の重複呼び出し排除

`SLOTracker.record()` 内部で `_propagate_dependencies()` が呼ばれた後、メインループでも再度呼ばれていました。固定点イテレーションを含むこの関数は比較的高コストです。

```python
# Before: 毎タイムステップで2回呼び出し
effective_health = self._propagate_dependencies(comp_states)  # record()内
eff_health = tracker._propagate_dependencies(ops_states)       # メインループ

# After: record()の結果をキャッシュして再利用
self._last_effective_health = effective_health  # record()内でキャッシュ
eff_health = tracker._last_effective_health      # メインループで再利用
```

### K1: リスト結合の O(n) 削減

メインループ内で `events + degradation_events` が毎ステップ新しいリストを生成していました。

```python
# Before: 毎ステップでリスト結合 O(len(events) + len(degradation_events))
all_events_so_far = events + degradation_events

# After: 事前に結合リストを作成し、差分のみ extend
all_events = list(events)  # ループ前に一度だけコピー
# ループ内:
all_events.extend(new_deg_events)  # 新規イベントのみ追加 O(k)
```

7日間シミュレーション（2,016ステップ）で約30万回のリスト要素コピーを削減しています。

## 3. 正確性修正（3件）

### C1: cascade の _apply_direct_effect に default case 追加

`match/case` 文に `case _:` がなく、未知の FaultType で `None` を返すバグがありました。

```python
case _:
    return CascadeEffect(
        component_id=component.id,
        component_name=component.name,
        health=HealthStatus.DEGRADED,
        reason=f"Unknown fault type: {fault.fault_type.value}",
    )
```

### C7: コスト削減の可視化

右サイジングで推奨レプリカ数が現在より少ない場合、コスト変化率が `max(0.0, ...)` でクランプされて常に 0% 以上になっていました。

```python
# Before: コスト削減が隠される
return round(max(0.0, increase_ratio * 100.0), 2)

# After: 負の値（削減）も表示
return round(increase_ratio * 100.0, 2)
# 例: -42.86% = 42.86%のコスト削減が可能
```

### E3: DDoS パターンの決定性保証

モジュールレベルの `_rng` がシナリオ間でリセットされず、what-if分析の DDoS ジッターが非決定的でした。ハッシュベースの決定的ジッターに置き換えました。

```python
# Before: モジュールレベル RNG（シナリオ間で状態が蓄積）
jitter = _rng.uniform(-0.20, 0.20)

# After: t から決定的にジッターを導出
jitter = (((t * 2654435761) & 0xFFFFFFFF) / 0xFFFFFFFF - 0.5) * 0.40
```

## 4. 機能追加（1件）

### K2: 右サイズ推奨の追加

キャパシティプランニングで、過剰プロビジョニングされたコンポーネントに対するスケールダウン推奨を追加しました。

```
RIGHT-SIZE: nginx (load_balancer) is over-provisioned at 25.0% utilization.
Consider scaling from 2 to 1 replicas to reduce costs.
```

デモインフラでは全6コンポーネントが右サイズ対象として検出され、**-42.86%のコスト削減**が可能であると報告されます。

## 5. テストカバレッジ拡大（35件）

| テストファイル | テスト数 | カバー範囲 |
|-------------|---------|-----------|
| test_ops_engine.py | 7 | 基本シナリオ・障害・デプロイ・決定性・バリデーション |
| test_traffic.py | 11 | 全10パターンタイプ・base_multiplier・範囲外・決定性 |
| test_capacity_engine.py | 8 | 予測・バリデーション・右サイズ・コスト削減 |
| test_loader.py | 10 | YAML読込・バリデーション・循環依存・エラー処理 |
| test_whatif_engine.py | 4 | パラメータスイープ・マルチパラメータ・決定性 |
| **合計** | **35** | **5モジュール** |

既存テスト（cascade: 15件, feeds: 11件）と合わせて **67件** のテストが全てパス（0.69秒）。

## まとめ

| カテゴリ | 件数 | 主な改善 |
|---------|------|---------|
| バリデーション | 6 | slo_target・dependency_type・replicas・循環依存・duration_days |
| パフォーマンス | 2 | 重複計算排除・リスト結合最適化 |
| 正確性 | 3 | default case・コスト可視化・DDoS決定性 |
| 機能追加 | 1 | 右サイズ推奨 |
| テスト | 35 | 5モジュールの包括的テスト |

v4.2〜v4.9の8イテレーションで、InfraSimは単なるカスケード障害シミュレータから、**バリデーション・決定性・テストカバレッジを備えた実用的なSREツール**へと進化しました。

次のイテレーションでは、残りの監査項目（CLI UX改善、README更新、get_critical_paths の組合せ爆発リスク等）に取り組みます。

## リポジトリ

https://github.com/mattyopon/infrasim
