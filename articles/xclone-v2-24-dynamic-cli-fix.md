---
title: "InfraSim v5.3: 動的シミュレーションCLIのTypeError修正"
emoji: "🐛"
type: "tech"
topics: ["python", "cli", "bugfix", "infrastructure", "chaosengineering"]
published: true
---

## はじめに

InfraSim v5.3 では、`infrasim dynamic` コマンド実行時に **TypeError でクラッシュする**ランタイムバグを修正しました。

## 問題

CLI の `dynamic` コマンドは `--duration` と `--step` オプションを受け付けますが、内部で呼び出す `run_all_dynamic_defaults()` メソッドはこれらのパラメータを受け付けませんでした。

```python
# cli.py:153 — キーワード引数を渡しているが…
results = engine.run_all_dynamic_defaults(duration=duration, step=step)

# dynamic_engine.py:310 — メソッドは引数を取らない！
def run_all_dynamic_defaults(self) -> DynamicSimulationReport:
```

`infrasim dynamic --duration 600 --step 10` を実行すると即座に `TypeError: run_all_dynamic_defaults() got an unexpected keyword argument 'duration'` が発生していました。

## 原因

CLI のオプション追加時に、対応するエンジンメソッドのシグネチャ更新が漏れていました。さらに、デフォルトシナリオ生成メソッド `_generate_default_dynamic_scenarios()` 内で `duration_seconds=300` と `time_step_seconds=5` がハードコードされていたため、CLI から渡された値が一切反映されていませんでした。

## 修正

1. `run_all_dynamic_defaults()` に `duration` と `step` パラメータを追加
2. `_generate_default_dynamic_scenarios()` にも同パラメータを伝播
3. メソッド内のハードコード値（`300`, `5`）を全てパラメータ参照に変更

```python
def run_all_dynamic_defaults(
    self, duration: int = 300, step: int = 5,
) -> DynamicSimulationReport:
    scenarios = self._generate_default_dynamic_scenarios(
        duration=duration, step=step,
    )
```

## 検証

```python
engine = DynamicSimulationEngine(graph)
report = engine.run_all_dynamic_defaults(duration=60, step=10)
assert report.results[0].scenario.time_step_seconds == 10  # ✅
assert report.results[0].scenario.duration_seconds == 60   # ✅
```

## 教訓

CLI オプションを追加する際は、対応するエンジンメソッドのシグネチャも必ず更新する。型チェッカー（mypy）を CI に導入すれば、この種のミスマッチを事前に検出できます。
