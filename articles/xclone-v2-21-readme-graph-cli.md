---
title: "InfraSim v5.0: README全面改訂・依存グラフ修正・CLI UX改善"
emoji: "📊"
type: "tech"
topics: ["python", "infrastructure", "chaosengineering", "cli", "networkx"]
published: true
---

## はじめに

InfraSim の継続的改善シリーズ v5.0 では、**ドキュメント品質**・**グラフアルゴリズムの正確性**・**CLI ユーザー体験**の 3 軸で 7 件の修正を実施しました。

## 修正一覧

| ID | 優先度 | カテゴリ | 内容 |
|----|--------|---------|------|
| R1 | HIGH | ドキュメント | README.md を v3.0/v4.0 機能で全面更新 |
| E2 | HIGH | 正確性 | `get_cascade_path()` のカスケード方向を修正 |
| E1 | MED | 安全性 | `get_critical_paths()` に組み合わせ爆発ガードを追加 |
| P1 | HIGH | パフォーマンス | ダウンタイム計算のイベントスキャンを O(1) ルックアップに最適化 |
| U3 | LOW | UX | イベントタイムライン表示を 10 件→25 件に拡大 |
| U4 | MED | バグ修正 | `--defaults` が `--step` を無視する問題を修正 |
| — | MED | バグ修正 | `TimeUnit` enum メンバー名の誤り修正 |

## 1. README 全面改訂（R1）

v1-v2 時代の README には 13 コマンドしか記載されておらず、v3.0 以降に追加された以下の主要機能が欠落していました：

- **ops-sim**: SLO/SLI トラッキング付き長期運用シミュレーション
- **whatif**: パラメータスイープによる What-If 分析
- **capacity**: 成長予測付きキャパシティプランニング
- **dynamic**: トラフィックパターン対応の動的シミュレーション
- 10 種類のトラフィックパターン（DDoS、フラッシュクラウド、日周期など）

更新後の README は全 17 CLI コマンドを網羅し、アーキテクチャ図にも Ops Engine / What-If Engine / Capacity Engine / Traffic Models を追加しました。

## 2. カスケードパス方向の修正（E2）

### 問題

`get_cascade_path()` は「障害がどのように伝播するか」を返すべきメソッドですが、実装は**逆方向**（上流→障害コンポーネント）のパスを返していました。

```python
# Before: 他のノードから障害ノードへの全パスを探索（逆方向）
for node in self._graph.nodes:
    for path in nx.all_simple_paths(self._graph, node, failed_component_id):
        paths.append(path)
```

### 修正

NetworkX の `reverse()` を使い、障害ノードから下流（依存している側）への全パスを探索するように変更：

```python
# After: 障害ノードから下流への全パスを探索（正しい方向）
reverse = self._graph.reverse()
for node in reverse.nodes:
    for path in nx.all_simple_paths(reverse, failed_component_id, node):
        paths.append(path)
```

PostgreSQL 障害時の出力例：
```
postgres -> app-1 -> nginx
postgres -> app-2 -> nginx
postgres -> app-1
postgres -> app-2
```

## 3. 組み合わせ爆発ガード（E1）

`get_critical_paths()` は全エントリポイントから全リーフノードへの全パスを列挙するため、大規模グラフで組み合わせ爆発が発生するリスクがありました。

```python
def get_critical_paths(self, max_paths: int = 100) -> list[list[str]]:
    # max_paths に達したら早期リターン
    if len(paths) >= max_paths:
        paths.sort(key=len, reverse=True)
        return paths
```

デモインフラ（6 コンポーネント）では 6 パスのみですが、50+ コンポーネントのグラフでは数千パスになり得ます。

## 4. ダウンタイム計算の最適化（P1）

### 問題

各タイムステップで DOWN 状態のコンポーネントごとに、**全イベントリスト**をスキャンしてオーバーラップを計算していました。30 日シミュレーション（8,640 ステップ × 数百イベント）ではこれが顕著なボトルネックになります。

### 修正

コンポーネント→イベントの辞書インデックス `_comp_events` を構築し、O(1) でルックアップ：

```python
# ループ前にインデックス構築
_comp_events: dict[str, list] = {}
for ev in all_events:
    _comp_events.setdefault(ev.target_component_id, []).append(ev)

# ループ内：新規イベントもインデックスに追加
for ev in new_deg_events:
    _comp_events.setdefault(ev.target_component_id, []).append(ev)

# ダウンタイム計算：全イベントではなく該当コンポーネントのイベントのみ
for ev in _comp_events.get(comp_id, []):
    ...
```

## 5. CLI UX 改善

### イベントタイムライン拡大（U3）

ops-sim のイベントタイムラインを 10 件→25 件に拡大。7 日間シミュレーションでは 10 件では全体像が見えませんでした。

### `--defaults` が `--step` を尊重（U4）

`run_default_ops_scenarios()` に `time_unit_override` パラメータを追加し、CLI の `--step` 指定がデフォルトシナリオにも適用されるようにしました。

### TimeUnit enum 名修正

QA で発見されたバグ: `TimeUnit.ONE_MINUTE` / `TimeUnit.ONE_HOUR` は存在しないメンバー名でした。正しい `TimeUnit.MINUTE` / `TimeUnit.HOUR` に修正。

## テスト結果

```
67 passed in 0.62s
```

全 67 テスト（ops_engine: 7, traffic: 11, capacity: 7, loader: 9, whatif: 4, cascade: 16, feeds: 11）が通過。

## まとめ

v5.0 では「使いやすさ」と「正確性」に焦点を当て、ドキュメント・アルゴリズム・CLI の 3 層で改善を行いました。次のイテレーションでは残りの監査項目（カスケード/ops エンジン間の伝播一貫性など）に取り組みます。
