---
title: "InfraSim v5.2: SVG XSSの修正とシミュレーション堅牢化"
emoji: "🛡️"
type: "tech"
topics: ["python", "security", "xss", "infrastructure", "chaosengineering"]
published: true
---

## はじめに

InfraSim v5.2 では、これまで未監査だった HTML レポーター・フィードモジュール・シミュレーションエンジンに対する深層監査を実施し、**セキュリティ脆弱性 1 件**と**堅牢性改善 2 件**を修正しました。

## 1. SVG ラベルの XSS 脆弱性修正（SEC-1 HIGH）

### 問題

HTML レポートの依存関係グラフは SVG で描画されますが、コンポーネント名がエスケープされずに `<text>` 要素に埋め込まれていました。

```python
# Before: 名前がそのまま SVG に挿入される
label = comp.name[:20]
parts.append(f'<text ...>{label}</text>')
```

コンポーネント名に `<script>alert(1)</script>` のような文字列が含まれていた場合、ブラウザがスクリプトとして解釈するリスクがありました。

### 修正

`xml.sax.saxutils.escape()` で XML 特殊文字（`<`, `>`, `&`）をエスケープ:

```python
from xml.sax.saxutils import escape

label = comp.name[:20]
label = escape(label)  # <script> → &lt;script&gt;
parts.append(f'<text ...>{label}</text>')
```

### 検証

```python
graph.components['test'].name = '<script>alert(1)</script>'
svg = _build_dependency_svg(graph)
assert '<script>' not in svg      # ✅ 生のタグなし
assert '&lt;script&gt;' in svg    # ✅ エスケープ済み
```

## 2. シナリオ数上限の追加（ROB-1 MED）

### 問題

セキュリティフィードが大量のシナリオを生成した場合、`run_scenarios()` が無制限に実行され CPU を消耗する可能性がありました。

### 修正

`MAX_SCENARIOS = 1000` の定数を追加し、超過時はログ出力して切り捨て:

```python
MAX_SCENARIOS = 1000

def run_scenarios(self, scenarios):
    if len(scenarios) > MAX_SCENARIOS:
        logger.warning(f"Truncating {len(scenarios)} scenarios to {MAX_SCENARIOS}")
        scenarios = scenarios[:MAX_SCENARIOS]
```

## 3. フィード XML パースエラーのログ追加（ROB-2 MED）

RSS/Atom フィードの XML パースが失敗した場合、空リストを返すだけで原因が不明でした。`logger.warning()` を追加し、フィード名とエラー詳細を記録するようにしました。

## 監査結果サマリー

v5.2 の深層監査で 18 件の課題を発見。うち 3 件を修正、2 件は既存ガードで安全であることを確認しました。

| 修正 | 状態 |
|------|------|
| SVG XSS エスケープ | ✅ 修正済み |
| シナリオ数上限 | ✅ 修正済み |
| XML パースログ | ✅ 修正済み |
| utilization() ゼロ除算 | ✅ 既存ガードで安全 |
| feed store JSON 破損 | ✅ 既存リカバリで安全 |

## テスト結果

```
71 passed in 0.81s
```

全 71 テスト通過 + XSS エスケープ手動検証 PASSED。
