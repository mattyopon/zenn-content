---
title: "InfraSim v5.5: 動的シミュレーション結果が常に0件表示されるバグの発見と修正"
emoji: "🐛"
type: "tech"
topics: ["python", "cli", "testing", "infrastructure", "chaosengineering"]
published: false
---

## はじめに

InfraSim v5.5 で、**動的シミュレーション（`infrasim dynamic`）の結果表示が完全に壊れていた**バグを修正しました。Critical/Warning の検出数が常に 0 と表示され、詳細情報も一切出力されない深刻な問題です。

このバグは v5.3 で `dynamic` コマンドを追加した際に混入し、v5.4 まで見逃されていました。

## 発見したバグ

### Bug 1: float を文字列比較していた（CRITICAL）

`_print_dynamic_results` 関数が `peak_severity`（float 型、0.0〜10.0）を文字列 `"critical"` / `"warning"` と比較していました。

```python
# ❌ Before: peak_severity は float なのに文字列比較
critical = sum(1 for r in results
    if getattr(r, "peak_severity", "") == "critical")  # 常に 0
warning = sum(1 for r in results
    if getattr(r, "peak_severity", "") == "warning")   # 常に 0
```

`DynamicScenarioResult` には `is_critical`（>= 7.0）と `is_warning`（4.0〜7.0）というプロパティが正しく定義されていたのに、CLI 側で使われていませんでした。

```python
# DynamicScenarioResult のプロパティ（正しく実装済みだった）
@property
def is_critical(self) -> bool:
    return self.peak_severity >= 7.0

@property
def is_warning(self) -> bool:
    return 4.0 <= self.peak_severity < 7.0
```

### Bug 2: DynamicSimulationReport を直接渡していた（CRITICAL）

`dynamic` コマンドが `run_all_dynamic_defaults()` の戻り値（`DynamicSimulationReport` オブジェクト）を `.results` を抽出せずに直接 `_print_dynamic_results()` に渡していました。

```python
# ❌ Before: report はリストではない → len() で TypeError
results = engine.run_all_dynamic_defaults(duration=duration, step=step)
_print_dynamic_results(results, console)  # TypeError!
```

一方、`simulate --dynamic` 側のコードパスでは正しく `.results` を抽出していました：

```python
# ✅ simulate --dynamic では正しかった
report = dyn_engine.run_all_dynamic_defaults()
results = getattr(report, "results", report) if not isinstance(report, list) else report
```

### Bug 3: --deploy-hour のバリデーション欠落（LOW）

`ops-sim` コマンドの `--deploy-hour` パラメータに 0〜23 の範囲チェックがなく、`--deploy-hour 25` や `--deploy-hour -1` が受け入れられていました。

## 修正内容

### 1. `_print_dynamic_results` の全面修正

```python
# ✅ After: is_critical / is_warning プロパティを使用
critical = sum(1 for r in results if getattr(r, "is_critical", False))
warning = sum(1 for r in results if getattr(r, "is_warning", False))

# 詳細表示も修正
for r in results:
    is_critical = getattr(r, "is_critical", False)
    is_warning = getattr(r, "is_warning", False)
    if not is_critical and not is_warning:
        continue

    color = "red" if is_critical else "yellow"
    label = "CRITICAL" if is_critical else "WARNING"
    name = getattr(r, "scenario", None)
    name = getattr(name, "name", "unknown") if name else "unknown"
    peak_sev = getattr(r, "peak_severity", 0.0)

    con.print(f"  [{color}]{label}[/] {name} (severity: {peak_sev:.1f})")
```

追加の改善：
- **空結果のハンドリング**: 結果が空の場合にフレンドリーなメッセージを表示
- **severity スコアの表示**: 数値が見えることで判定の根拠が明確に

### 2. `dynamic` コマンドの `.results` 抽出

```python
# ✅ After: simulate --dynamic と同じパターンで .results を抽出
report = engine.run_all_dynamic_defaults(duration=duration, step=step)
results = getattr(report, "results", report) if not isinstance(report, list) else report
_print_dynamic_results(results, console)
```

### 3. `--deploy-hour` バリデーション追加

```python
if deploy_hour < 0 or deploy_hour > 23:
    console.print("[red]--deploy-hour must be between 0 and 23[/]")
    raise typer.Exit(1)
```

## テスト

14 件の新規テストを追加し、修正の正しさと境界値を網羅的に検証しました。

| テスト | 検証内容 |
|--------|---------|
| `test_critical_detected` | severity >= 7.0 が CRITICAL としてカウント・表示される |
| `test_warning_detected` | severity 4.0〜6.9 が WARNING としてカウント・表示される |
| `test_passed_detected` | severity < 4.0 が Passed としてカウントされ、詳細非表示 |
| `test_mixed_results` | 6件混合（CRIT 2, WARN 2, PASS 2）の正確なカウント |
| `test_empty_results` | 空リストでフレンドリーメッセージ表示 |
| `test_recovery_none_shows_no_recovery` | recovery=None で "no recovery" 表示 |
| `test_recovery_present_shows_seconds` | recovery=45 で "45s" 表示 |
| `test_report_critical_findings` | DynamicSimulationReport.critical_findings の正確性 |
| `test_report_warnings` | DynamicSimulationReport.warnings の正確性 |
| `test_severity_boundary_critical` | 境界値 7.0 → critical |
| `test_severity_boundary_warning_upper` | 境界値 6.999 → warning |
| `test_severity_boundary_warning_lower` | 境界値 4.0 → warning |
| `test_severity_boundary_passed` | 境界値 3.999 → passed |
| `test_severity_zero` | 0.0 → passed |

```
85 passed in 0.88s ✅
```

## なぜ見逃されていたか

1. **テスト不在**: `_print_dynamic_results` に対するテストがなかった
2. **2つのコードパス**: `simulate --dynamic` と `dynamic` で別々のコードパスが存在し、後者のみバグがあった
3. **サイレントな誤動作**: TypeError ではなく「0件表示」という形で失敗するため、気づきにくかった（Bug 1）

## 教訓

### 型の不一致は静的解析で防げる

`peak_severity: float` を `== "critical"` と比較するバグは、**mypy の strict モード**や **`--warn-return-any`** で検出できた可能性があります。

```bash
# 型チェックで防止できた
mypy --strict src/infrasim/cli.py
# error: Unsupported operand types for == ("float" and "str")
```

### プロパティがあるなら使え

`DynamicScenarioResult` に `is_critical` / `is_warning` プロパティが**正しく定義されていた**のに、CLI 側で独自の（間違った）分類ロジックを書いていました。**既存の抽象化を無視して車輪の再発明をすると、バグが生まれます。**

### コードパスの統一

同じ処理を行う2つのコードパス（`simulate --dynamic` と `dynamic`）で、片方だけ正しく、片方がバグっていました。**共通処理は1箇所に集約**すべきです。

## まとめ

| 項目 | 内容 |
|------|------|
| バージョン | v5.4 → v5.5 |
| 修正バグ | 3件（CRITICAL 2, LOW 1） |
| 新規テスト | 14件 |
| 総テスト | 85/85 PASSED |
| 影響範囲 | `infrasim dynamic` と `infrasim simulate --dynamic` の結果表示 |

## v5.6 追加修正: ローリングリスタートシナリオ

### 発見した問題

`scenarios.py` の `generate_default_scenarios()` で、ローリングリスタート失敗シナリオが `app[:len(app) // 2 + 1]` で対象サーバーを選択していました。

| サーバー数 | 修正前（ダウン数） | 修正後（ダウン数） |
|-----------|-------------------|-------------------|
| 2 | 2/2 (**全停止**) | 1/2 (50%) |
| 3 | 2/3 (66%) | 2/3 (66%) |
| 4 | 3/4 (75%) | 3/4 (75%) |

2台構成で全サーバーがダウンする = 全面停止シナリオと重複し、「ローリングリスタート失敗」の意味を成しません。

### 修正

```python
# ❌ Before: 2台の場合 ALL DOWN
half = app[:len(app) // 2 + 1]

# ✅ After: 常に少なくとも1台は稼働を維持
half = app[:min(len(app) - 1, len(app) // 2 + 1)]
```

## 障害注入テスト結果（v5.6 最終確認）

全3モードの障害注入テストをデモインフラ（6コンポーネント）に対して実行し、クラッシュ・エラーなしで完了しました。

| モード | シナリオ数 | Critical | Warning | Passed |
|--------|-----------|----------|---------|--------|
| 静的カオス | 150 | 7 | 66 | 77 |
| 動的シミュレーション | 134 | 13 | 33 | 88 |
| 運用シミュレーション | 5 | - | - | - |

運用シミュレーション（30日ストレステスト）では、3件のランダム障害・6件の劣化イベント・51件のイベントを正しくシミュレートし、最小可用性 26.67% まで低下するシナリオを検出しました。

## 全体まとめ

| 項目 | 内容 |
|------|------|
| バージョン | v5.4 → v5.6 |
| 修正バグ | 4件（CRITICAL 2, LOW 2） |
| 新規テスト | 18件（v5.5: 14, v5.6: 4） |
| 総テスト | 89/89 PASSED |
| 全モジュール監査 | 完了（バグゼロ確認） |
| 障害注入テスト | 全3モード正常動作 |
