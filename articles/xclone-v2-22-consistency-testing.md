---
title: "InfraSim v5.1: エンジン間一貫性・What-If正確性・テストカバレッジ強化"
emoji: "🔧"
type: "tech"
topics: ["python", "testing", "infrastructure", "chaosengineering", "quality"]
published: false
---

## はじめに

InfraSim v5.1 では、v5.0 の監査で特定された**エンジン間の一貫性問題**・**What-If シミュレーションの正確性**・**テストカバレッジのギャップ**に対処しました。

## 修正一覧

| 優先度 | カテゴリ | 内容 |
|--------|---------|------|
| MED | 正確性 | whatif レプリカ clamping 後のメトリクス不整合修正 |
| LOW | API設計 | dynamic_engine の `_graph` 直接参照を公開 API に修正 |
| LOW | ドキュメント | ops_engine の利用率閾値コメント修正 |
| LOW | UX | `--diurnal-peak` に >= 1.0 バリデーション追加 |
| MED | テスト | 4 新テスト追加（71 テスト合計） |

## 1. What-If レプリカ clamping 修正

### 問題

`replica_factor` を 0.1 のような小さい値に設定すると、レプリカ数は `max(1, round(original * 0.1))` で 1 にクランプされます。しかし CPU/メモリなどのメトリクスは `original * 0.1` の比率で調整され、**レプリカ数は変わらないのにメトリクスだけ下がる**不整合が発生していました。

### 修正

```python
unclamped = round(original * value)
new_replicas = max(1, unclamped)

# メトリクスはレプリカ数が実際に変わった場合のみ調整
if unclamped == new_replicas:
    # クランプされていない → メトリクスも比例調整
    comp.metrics.cpu_percent *= ratio
else:
    # クランプされた → メトリクスは変更しない
    pass
```

## 2. 公開 API の使用

`dynamic_engine.py` が `self.graph._graph.edges` というプライベート属性に直接アクセスしていたのを、公開メソッド `self.graph.all_dependency_edges()` に修正。

```python
# Before: プライベートAPI直接参照
for edge in self.graph._graph.edges:
    dep = self.graph.get_dependency_edge(src, tgt)

# After: 公開API使用
for dep in self.graph.all_dependency_edges():
    cb_states[(dep.source_id, dep.target_id)] = CircuitBreakerState.CLOSED
```

## 3. テストカバレッジ強化（67→71テスト）

### 新規テスト

| テスト | 検証内容 |
|--------|---------|
| `test_cascade_path_direction` | `get_cascade_path()` が障害コンポーネントから下流方向のパスを返すことを検証 |
| `test_critical_paths_max_guard` | `max_paths` パラメータで組み合わせ爆発が制限されることを検証 |
| `test_optional_dependency_propagation` | optional 依存関係のセットアップと型を検証 |
| `test_ops_default_time_unit_override` | `time_unit_override` が全デフォルトシナリオに適用されることを検証 |

### テスト結果

```
71 passed in 0.85s
```

## 4. CLI バリデーション追加

`--diurnal-peak` に 1.0 未満の値を指定するとエラーになるようバリデーションを追加。日周期パターンのピークが 1.0 未満では物理的に意味がないためです。

## まとめ

v5.1 は「見えにくいバグ」に焦点を当てたイテレーションです。What-If 分析の正確性、内部 API の健全性、テストカバレッジの充実により、シミュレーション結果の信頼性が向上しました。
