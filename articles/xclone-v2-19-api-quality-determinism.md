---
title: "InfraSim v4.7 — API品質改善・副作用除去・決定論的シミュレーション"
emoji: "🧹"
type: "tech"
topics: ["InfraSim", "infrastructure", "simulation", "SRE"]
published: false
---

## はじめに

前回の[v2.18記事](https://zenn.dev/ymaeda/articles/xclone-v2-18-dependency-aware-availability)では、**InfraSim v4.6**で依存関係グラフ（トポロジー）を考慮した可用性計算とローリングアップデートモデルを導入しました。

v4.6はInfraSimの最も大きなアーキテクチャ変更でしたが、v4.7はそれとは対照的に**小粒だが重要なコード品質改善**を5件まとめたリリースです。プログラミングAPI・CLIの使い勝手、シミュレーションの決定論性、そして入力データを破壊する副作用バグの修正が含まれます。

地味な修正が多いですが、**ライブラリとしての信頼性**を高める上で欠かせない変更ばかりです。

### シリーズ記事

| # | 記事 | テーマ |
|---|------|--------|
| 16 | [**v2.15** -- 利用率計算統一 & 5バグ修正](https://zenn.dev/ymaeda/articles/xclone-v2-15-utilization-consistency) | InfraSim v4.3 / max統一 / 加重ダウンタイム / RNG汚染修正 |
| 17 | [**v2.16** -- MTTR感度分析 & リスクベースError Budget](https://zenn.dev/ymaeda/articles/xclone-v2-16-mttr-sensitivity-burnrate) | InfraSim v4.4 / MTBFキャップ / burn rate推定 / CLI強化 |
| 18 | [**v2.17** -- ダウンタイム精度向上 & トラフィックモデル修正](https://zenn.dev/ymaeda/articles/xclone-v2-17-downtime-precision-traffic) | InfraSim v4.5 / fault-overlap / MTBFキャップ緩和 / base_multiplier |
| 19 | [**v2.18** -- 依存関係トポロジーを考慮した可用性計算](https://zenn.dev/ymaeda/articles/xclone-v2-18-dependency-aware-availability) | InfraSim v4.6 / 固定点反復 / 依存伝播 / ローリングアップデート |
| **20** | **v2.19 -- API品質改善・副作用除去・決定論的シミュレーション（本記事）** | **InfraSim v4.7 / loader柔軟化 / CLI positional / RNG独立化** |

### InfraSimバージョンの進化（抜粋）

```
v4.3 (v2.15): 利用率計算統一 & バグ修正
v4.4 (v2.16): MTTR感度分析 & リスクベースError Budget
v4.5 (v2.17): ダウンタイム精度向上 & トラフィックモデル修正
v4.6 (v2.18): 依存関係トポロジーを考慮した可用性計算

v4.7 (v2.19, 本記事): API品質改善・副作用除去・決定論的シミュレーション  <-- NEW
  ├ load_yaml() が str を受け付けるように拡張
  ├ CLI positional YAML引数を whatif / capacity / ops-sim に追加
  ├ _schedule_events の入力グラフ変更（副作用バグ）を修正
  ├ 非決定的 jitter RNG をシナリオ単位の独立RNGに置換
  └ weekend_factor のセマンティックハックを専用フィールドに分離
```

---

## 課題1: load_yaml() が str を受け付けない

`load_yaml()` はInfraSimのプログラミングAPIの入口関数です。v4.6まで `Path` 型のみ受け付けていました。

```python
from infrasim.model.loader import load_yaml
graph = load_yaml(Path("infra.yaml"))  # OK
graph = load_yaml("infra.yaml")        # TypeError!
```

Python標準ライブラリの `open()` は `str` も `Path` も受け付けます。InfraSimだけ `Path` を強制するのは不自然で、Jupyter NotebookやREPLで煩わしいものでした。

型アノテーションを `Path | str` に拡張し、`str` が渡された場合は内部で `Path()` に変換します。`load_yaml_with_ops()` にも同様に適用。

```python
def load_yaml(path: Path | str) -> InfraGraph:
    if isinstance(path, str):
        path = Path(path)
    # ...以降は同じ
```

既存コードとの後方互換性は完全に保たれます。

---

## 課題2: CLI positional YAML引数

`load` コマンドはYAMLをpositional引数で受け取れるのに、`whatif` / `capacity` / `ops-sim` は `--yaml` オプションが必要でした。

```bash
infrasim load infra.yaml                           # positional: OK
infrasim whatif --yaml infra.yaml --parameter ...  # なぜここだけ --yaml が必要?
```

3コマンドにpositional引数を追加し、`--yaml` も後方互換で残しました。

```python
@app.command()
def whatif(
    yaml_pos: Path | None = typer.Argument(None),
    yaml_file: Path | None = typer.Option(None, "--yaml"),
    # ...
) -> None:
    resolved_yaml = yaml_pos or yaml_file
```

```bash
# v4.7: どちらでもOK
infrasim whatif infra.yaml --parameter replicas --range 1,2,3,4
infrasim capacity infra.yaml --growth 0.15
infrasim ops-sim infra.yaml --defaults
```

---

## 課題3: _schedule_events の入力グラフ変更（副作用バグ）

`_schedule_events()` は障害イベントをスケジューリングする関数です。`mtbf_hours` が0以下のとき、デフォルト値で埋める処理が**グラフオブジェクトの属性を直接変更**していました。

```python
# v4.6（問題コード）— 入力グラフを直接書き換え
if comp.operational_profile.mtbf_hours <= 0:
    comp.operational_profile.mtbf_hours = _DEFAULT_MTBF_HOURS.get(comp_type, 2160.0)
```

この副作用は**capacity engineのburn rate計算**に波及します。`ops-sim` を先に実行すると、ユーザーが「未設定（0）」のつもりだった `mtbf_hours` が `2160` に書き換わった状態でcapacity engineに渡されるのです。1つのグラフオブジェクトを複数エンジンで共有するアーキテクチャでは致命的です。

修正は**ローカル変数**でデフォルト値を処理するだけです。

```python
# v4.7（修正後）— 入力グラフは変更しない
mtbf_hours = comp.operational_profile.mtbf_hours
if mtbf_hours <= 0:
    mtbf_hours = _DEFAULT_MTBF_HOURS.get(comp_type, 2160.0)
```

4行程度の変更ですが、**関数の純粋性を回復**する重要な修正です。

---

## 課題4: 非決定的 jitter RNG

各コンポーネントには「thundering herd」防止のため0.7〜1.3のjitter係数を割り当てています。v4.6まで、この生成にモジュールレベルの `_ops_rng` を使っていました。

```python
# ops_engine.py（v4.6まで）
_ops_rng = random.Random(2024)  # モジュールレベルRNG

class OpsSimulationEngine:
    def _init_ops_states(self):
        for comp_id, comp in self.graph.components.items():
            jitter = 0.7 + _ops_rng.random() * 0.6  # 共有RNGを消費
```

モジュールレベルRNGの問題は**実行順序依存**です。`scenario_a` を先に実行すると `_ops_rng` の状態が変わり、`scenario_b` のjitter値が変動します。同じ `random_seed` を設定しても結果が変わる -- 決定論的シミュレーションの原則に反します。

**シナリオの `random_seed` から導出した独立RNG**に置換しました。

```python
# ops_engine.py（v4.7）
def _init_ops_states(self, scenario: OpsScenario):
    jitter_rng = random.Random(scenario.random_seed + 1)  # +1 でイベントRNGと分離
    for comp_id, comp in self.graph.components.items():
        jitter = 0.7 + jitter_rng.random() * 0.6
```

- **同じシード → 同じ結果**: 実行順序に関係なく再現可能
- **イベントRNGとの分離**: jitterの変更がイベントスケジュールに影響しない

v4.3で修正した「RNG汚染」問題と同じカテゴリのバグです。乱数生成は共有状態を持たないように設計するのが鉄則です。

---

## 課題5: weekend_factor のセマンティックハック

`DIURNAL_WEEKLY` パターンでは週末のトラフィック減衰率が必要です。v4.6まで、この値は `wave_period_seconds`（本来は「波の周期（秒）」）フィールドにパーセンテージとして格納するハックが使われていました。

```python
# v4.6まで — wave_period_seconds を流用
if self.wave_period_seconds > 0:
    weekend_factor = self.wave_period_seconds / 100.0  # 70 → 0.7
else:
    weekend_factor = 0.6
```

問題点:
- **意味の不整合**: 「周期（秒）」フィールドに「倍率%」を入れる
- **精度の損失**: `float → int → float` 変換が暗黙的
- **YAML記述が不自然**: `wave_period_seconds: 70` で「週末70%」を意味する

専用の `weekend_factor` フィールドを追加して分離しました。

```python
# traffic.py（v4.7）
class TrafficPattern(BaseModel):
    weekend_factor: float = Field(
        default=0.6,
        description="Weekend traffic as fraction of weekday peak (0.0-1.0).",
    )
```

```yaml
# v4.7: 専用フィールドで明快
traffic_patterns:
  - pattern_type: diurnal_weekly
    peak_multiplier: 3.0
    weekend_factor: 0.7   # 週末は平日ピークの70%
```

`wave_period_seconds` は本来の「波の周期」として正しく機能を取り戻しています。

---

## v4.1〜v4.7 全修正まとめ

InfraSim v4.1から本バージョンまでの全修正を表にまとめます。

| バージョン | 記事 | 修正数 | 主要変更 |
|-----------|------|--------|---------|
| **v4.1** | v2.14 | 5件 | multi-whatif / overload検出 / utilization統一 / RNG分離 / CLI強化 |
| **v4.2** | v2.14 | 1件 | OVERLOADED partial availability（80%重み） |
| **v4.3** | v2.15 | 5件 | max利用率統一 / 加重ダウンタイム / RNG汚染修正 / 0除算ガード |
| **v4.4** | v2.16 | 5件 | MTTR what-if修正 / burn rate推定 / MTBFキャップ / CLI新コマンド |
| **v4.5** | v2.17 | 5件 | fault-overlap精度向上 / MTBFキャップ緩和 / base_multiplier / トラフィック修正 |
| **v4.6** | v2.18 | 2件 | 依存関係トポロジー可用性計算 / ローリングアップデートモデル |
| **v4.7** | v2.19 | 5件 | loader柔軟化 / CLI positional / 副作用除去 / RNG独立化 / weekend_factor |
| | | **合計 28件** | |

### カテゴリ別の傾向

28件の修正をカテゴリ分けすると、InfraSimの成熟過程が見えてきます。

| カテゴリ | 件数 | 代表例 |
|---------|------|--------|
| **正確性（計算ロジック）** | 10件 | fault-overlap / 加重ダウンタイム / 依存伝播 |
| **決定論性（RNG関連）** | 4件 | RNG分離 / RNG汚染修正 / jitter独立化 |
| **API/CLI使い勝手** | 6件 | multi-whatif / positional引数 / loader柔軟化 |
| **データモデル設計** | 5件 | weekend_factor / base_multiplier / burn rate |
| **副作用・安全性** | 3件 | 入力グラフ変更 / 0除算ガード / OVERLOADEDハンドリング |

初期は「計算が間違っている」系の修正が多く、後半にいくにつれて「使い勝手」「設計の美しさ」系の修正にシフトしています。これはソフトウェアの典型的な成熟パターンです。

### 決定論性の進化

RNG関連の修正がv4.1 → v4.3 → v4.7と3回にわたって発生しています。

| バージョン | 問題 | 原因 |
|-----------|------|------|
| v4.1 | シミュレーション間でRNGが干渉 | 単一のRNGインスタンスを共有 |
| v4.3 | テスト実行順序で結果が変わる | テスト間でRNG状態がリセットされない |
| v4.7 | jitter値が実行順序に依存 | モジュールレベルRNGが状態を引き継ぐ |

「乱数の共有状態」は見落としやすいバグの温床です。原則として、**RNGは使用箇所のスコープでローカルに生成**し、シードから再現可能にすることが重要です。

---

## まとめ

v4.7は**5件の小粒な修正**のリリースですが、ライブラリとしての品質を着実に向上させています。

| 修正 | Before | After | 影響 |
|------|--------|-------|------|
| `load_yaml()` 型拡張 | `Path` のみ | `Path \| str` | API利便性向上 |
| CLI positional引数 | `--yaml file.yaml` | `file.yaml` | `load` コマンドとの一貫性 |
| `_schedule_events` 副作用除去 | 入力グラフを直接変更 | ローカル変数で処理 | エンジン間の独立性回復 |
| jitter RNG独立化 | モジュールレベル共有RNG | シナリオ単位の独立RNG | 決定論的再現性 |
| `weekend_factor` 専用フィールド | `wave_period_seconds` に相乗り | 専用フィールド | モデルの意味的整合性 |

v4.6の「依存関係トポロジー」のような華やかな機能追加はありませんが、**副作用バグの修正**（課題3）と**RNG独立化**（課題4）はシミュレーション結果の信頼性に直結する重要な修正です。

特に課題3の副作用バグは、**関数が入力を変更しない**という原則の重要性を改めて示しています。Pythonでは引数がミュータブルオブジェクトの場合、意図せず呼び出し元のデータを書き換えてしまうことがあります。型チェックでは検出できないため、コードレビューやテストで意識的に確認する必要があります。

v4.7で「地盤固め」が完了し、InfraSimは28件以上のバグ修正を経て安定したシミュレーション基盤になりました。
