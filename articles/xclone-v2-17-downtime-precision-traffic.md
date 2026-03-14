---
title: "InfraSim v4.5 — ダウンタイム精度向上とトラフィックモデル修正"
emoji: "📊"
type: "tech"
topics: ["InfraSim", "infrastructure", "simulation", "SRE"]
published: true
---

## はじめに

前回の[v2.16記事](https://zenn.dev/ymaeda/articles/xclone-v2-16-mttr-sensitivity-burnrate)では、**InfraSim v4.4**でMTTR感度分析の実現とリスクベースError Budget推定を導入しました。

しかしv4.4の修正自体がいくつかの新たな問題を生んでいました。MTBFキャップが**過剰に攻撃的**で全コンポーネントに約3回の障害を強制すること、タイムステップ粒度によりダウンタイムが**最大10倍過大評価**されること、traffic_factorがGROWTH_TRENDパターンの成長率を**破壊**する問題などです。

v4.5ではこれら5件の修正でシミュレーション精度とモデルの正確性を改善しました。

### シリーズ記事

| # | 記事 | テーマ |
|---|------|--------|
| 16 | [**v2.15** -- 利用率計算統一 & 5バグ修正](https://zenn.dev/ymaeda/articles/xclone-v2-15-utilization-consistency) | InfraSim v4.3 / max統一 / 加重ダウンタイム / RNG汚染修正 |
| 17 | [**v2.16** -- MTTR感度分析 & リスクベースError Budget](https://zenn.dev/ymaeda/articles/xclone-v2-16-mttr-sensitivity-burnrate) | InfraSim v4.4 / MTBFキャップ / burn rate推定 / CLI強化 |
| **18** | **v2.17 -- ダウンタイム精度向上 & トラフィックモデル修正（本記事）** | **InfraSim v4.5 / fault-overlap / MTBFキャップ緩和 / base_multiplier** |

### InfraSimバージョンの進化（抜粋）

```
v4.3 (v2.15): 利用率計算統一 & バグ修正
v4.4 (v2.16): MTTR感度分析 & リスクベースError Budget

v4.5 (v2.17, 本記事): ダウンタイム精度向上 & トラフィックモデル修正  <-- NEW
  ├ fault-overlap計算: タイムステップ粒度によるダウンタイム過大評価を解消
  ├ MTBFキャップ緩和: sim期間/3 → duration_hours（168h）
  ├ base_multiplier: traffic_factorとpeak_multiplierの分離
  ├ CLI報告色: min_availability → avg_availabilityベースに変更
  └ burn rate: レプリカ冗長性を考慮した割引適用
```

## 課題1: MTBFキャップの過剰攻撃性

### 症状

v4.4で導入したMTBFキャップは「sim期間の1/3」（7日間で約56時間）でした。MTTR感度分析を機能させる目的では成功しましたが、全コンポーネントに**約3回の障害を強制**していました。

```
v4.4: max_mtbf_hours = 168h / 3 = ~56h → 期待failure数 = 168h / 56h = 3.0回
v4.5: max_mtbf_hours = 168h          → 期待failure数 = 168h / 168h = 1.0回
```

MTBF 2,160時間（90日）のコンポーネントに本来0.078回しか期待されない障害を、38倍（3回）も強制していたことになります。

### v4.5の解法: duration_hoursへのキャップ緩和

```diff
  def _apply_mttr_factor(self, factor, base_scenario):
      graph = copy.deepcopy(self.graph)
-     total_seconds = base_scenario.duration_days * 86400
-     max_mtbf_hours = total_seconds / 3.0 / 3600.0
+     max_mtbf_hours = base_scenario.duration_days * 24.0
```

### MTTR感度の比較

| MTTR factor | v4.4 (56hキャップ) | v4.5 (168hキャップ) |
|-------------|-------------------|-------------------|
| 0.5x | 99.50% | 99.75% |
| 1.0x | 98.70% | 99.25% |
| 2.0x | 97.41% | 98.51% |
| 4.0x | 95.49% | 97.52% |
| 8.0x | 93.56% | 96.03% |

v4.5では可用性の絶対値がより現実的に改善されつつ、MTTR 0.5xから8.0xまでの差分（99.75%→96.03%、約3.7ポイント）は依然として明確です。v4.4の約6ポイントよりは穏やかですが、**MTTR変動の影響を定量的に評価するには十分な感度**を維持しています。

### なぜ「sim期間そのもの」か

期待failure数1.0は「シミュレーション期間中に平均1回の障害が起きる」ことを意味します。Poisson分布では、期待値1.0の場合に障害0回の確率は約36.8%です。

| キャップ値 | 期待failure数 | 0回の確率 | 評価 |
|-----------|-------------|----------|------|
| sim/3 (v4.4) | 3.0 | 5.0% | 攻撃的すぎる |
| **sim/1 (v4.5)** | **1.0** | **36.8%** | **適度なバランス** |
| sim*2 | 0.5 | 60.7% | 障害が起きない確率が高い |

36.8%の確率で障害ゼロのシードが存在しますが、10コンポーネントの**全てで障害ゼロ**の確率は `0.368^10 = 0.004%` とほぼゼロです。インフラ全体では確実に障害が発生し、MTTR感度は測定可能になります。

## 課題2: タイムステップ粒度によるダウンタイム過大評価

### 症状

ops-simはデフォルト5分（300秒）のタイムステップで進行します。30秒のデプロイ障害がタイムステップ内で発生した場合、v4.4ではステップ全体（300秒）がダウンタイムとして計上されていました。

```
v4.4: コンポーネントがDOWN → step_seconds(300s)をそのまま加算
結果: 30秒の障害が300秒として計上 → 10倍の過大評価
```

### v4.5の解法: fault-overlap計算

各コンポーネントの障害イベントとタイムステップの**実際の重なり（overlap）**を計算します。

```python
for comp_id, state in ops_states.items():
    if state.current_health == HealthStatus.DOWN:
        down_count += 1
        max_overlap = 0.0
        for ev in all_events_so_far:
            if ev.target_component_id != comp_id:
                continue
            ev_start = ev.time_seconds
            ev_end = ev_start + ev.duration_seconds
            overlap = min(ev_end, t + step_seconds) - max(ev_start, t)
            if overlap > max_overlap:
                max_overlap = overlap
        component_overlap_total += max_overlap if max_overlap > 0 else step_seconds
```

### 図解

```
タイムステップ:  |←────── 300秒 (5分) ──────→|
                 t=1200                    t=1500

障害イベント:    |←30s→|
                 t=1200  t=1230

v4.4の計上:     |▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓|  → 300秒
v4.5の計上:     |▓▓|                         → 30秒 (overlap)
```

overlap計算: `min(1230, 1500) - max(1200, 1200) = 30秒`。正確な障害期間が計上されます。

### 修正後の結果

10コンポーネントのインフラで、各コンポーネントが30秒のデプロイ障害を持つ場合：

| 項目 | v4.4 | v4.5 |
|------|------|------|
| 計上ダウンタイム | ~50.0分 | ~6.7分 |
| 加重ダウンタイム | 5.0分 | 0.67分 |
| 可用性への影響 | 大幅に悪化 | 現実的な数値 |

フォールバック `max_overlap > 0 else step_seconds` は、イベントリストにマッチが見つからない場合（degradation由来等）に安全側に倒す防御的実装です。通常の障害イベントではオーバーラップが正の値になるため、フォールバックが発動することはありません。

## 課題3: traffic_factorがGROWTH_TREND成長率を破壊

### 症状

v4.4のWhat-if分析で`traffic_factor`を適用すると、`peak_multiplier`が直接スケーリングされていました。

```python
# v4.4
pattern.peak_multiplier *= value
```

DIURNALパターン（peak_multiplier=ピーク倍率）では正しく動作しますが、**GROWTH_TREND**ではpeak_multiplierは「月次成長率」を意味します。

```python
def _growth_trend(self, t):
    monthly_rate = self.peak_multiplier  # 例: 0.1 = 月10%成長
    return math.pow(1.0 + monthly_rate, elapsed_days / 30.0)
```

traffic_factor=2.0を適用すると、成長率が0.1→0.2（月10%→月20%）に変わってしまい、意図した「トラフィック量の2倍化」ではなく「成長速度の加速」になります。

### 問題の本質: peak_multiplierの多重利用

`peak_multiplier`フィールドは、パターンタイプによって**異なるセマンティクス**を持っています。

| パターンタイプ | peak_multiplierの意味 | traffic_factor適用時 |
|--------------|---------------------|-------------------|
| DIURNAL | ピーク時倍率 | 倍率が増加（正しい） |
| SPIKE / WAVE | スパイク/振幅倍率 | 倍率が増加（正しい） |
| **GROWTH_TREND** | **月次成長率** | **成長率が変更される（間違い）** |
| DDoS系 | 攻撃時倍率 | 倍率が増加（正しい） |

### v4.5の解法: base_multiplierフィールドの追加

`TrafficPattern`に新フィールド`base_multiplier`（デフォルト1.0）を追加し、出力スケーリングを分離しました。

```diff
+ base_multiplier: float = Field(default=1.0, description="Output scaling factor")

  def multiplier_at(self, t):
-     return self._diurnal(t)  # 各パターンから直接return
+     raw = self._diurnal(t)   # 各パターンの生の値を取得
+     return raw * self.base_multiplier  # 出力時にスケーリング
```

traffic_factorはbase_multiplierを操作するように変更：

```diff
  elif param == "traffic_factor":
      for pattern in modified_scenario.traffic_patterns:
-         pattern.peak_multiplier *= value
+         pattern.base_multiplier *= value
```

### 修正後の動作比較

**GROWTH_TRENDパターン（月10%成長、traffic_factor=2.0）:**

```
v4.4: peak_multiplier=0.2 → (1.2)^(7/30) = 1.045 ❌ 成長率が変更された
v4.5: peak_multiplier=0.1, base_multiplier=2.0
      → (1.1)^(7/30) * 2.0 = 2.046 ✅ 成長率維持、出力2倍
```

`base_multiplier`は各パターンの計算結果に一律に適用される乗数のため、パターン固有のセマンティクスに干渉しません。

| パターンタイプ | peak_multiplierの役割 | base_multiplierの効果 |
|--------------|---------------------|---------------------|
| CONSTANT / RAMP / SPIKE | 固定/ランプ/スパイク倍率 | 出力を均一にスケーリング |
| WAVE / DIURNAL | 振幅/ピーク倍率 | 波全体をスケーリング |
| GROWTH_TREND | 月次成長率 | 成長率を維持したまま出力をスケーリング |
| DDoS系 | 攻撃時倍率 | 攻撃強度をスケーリング |

全10パターンタイプで正しく動作します。

## 課題4: CLI報告色がmin_availabilityで常に赤

v4.4ではops-simの色分けが`min_availability`に基づいていました。デプロイ時の一時的な再起動（30秒）でも1ステップの可用性が90%台に下がり、**全体の平均が99.9%超でも常に赤表示**になっていました。

v4.5では**avg_availability**ベースに変更しつつ、min値は引き続き数値で表示します。

```diff
+ avg_avail_for_color = sum(p.availability_percent for p in result.sli_timeline) / len(...)
- if avail >= 99.9:
+ if avg_avail_for_color >= 99.9:
      avail_color = "green"
```

- 平均99.95%、最小92.0% → **green**（一時的なデプロイ障害）
- 平均99.5%、最小85.0% → **yellow**（繰り返しの障害）
- 平均98.0%、最小70.0% → **red**（深刻な問題）

## 課題5: burn rateがレプリカ冗長性を無視

### 症状

v4.4のburn rate推定は、3レプリカ構成のコンポーネントでも1レプリカと同じburn rateを返していました。1インスタンスの障害はフェイルオーバーにより**サービス停止にはならない**はずです。

### v4.5の解法: 1/replicas割引

```diff
- daily_burn += (24.0 / mtbf_h) * mttr_min
+ failure_downtime = (24.0 / mtbf_h) * mttr_min
+ if comp.replicas > 1:
+     failure_downtime /= comp.replicas
+ daily_burn += failure_downtime
```

| コンポーネント | レプリカ | v4.4 burn rate | v4.5 burn rate |
|--------------|---------|----------------|----------------|
| PostgreSQL | 3 | 0.333 min/day | 0.111 min/day |
| Redis | 3 | 0.200 min/day | 0.067 min/day |
| App Server | 3 | 0.333 min/day | 0.111 min/day |
| Load Balancer | 1 (SPOF) | 0.333 min/day | 0.333 min/day（割引なし） |

厳密にはN台全同時障害の確率はP^Nですが、部分障害の影響（フェイルオーバー中のレイテンシ増加）や共通モード障害（デプロイが全レプリカに影響）を考慮し、`1/replicas`の線形割引を採用しています。

全体のburn rate（コンポーネント平均）：

```
v4.4: (0.333 + 0.200 + 0.333 + 0.333) / 4 = 0.30 min/day
v4.5: (0.111 + 0.067 + 0.111 + 0.333) / 4 = 0.155 min/day
```

Error Budget消費率（SLO 99.9%、月間予算43.2分）：

```
v4.4: 0.30 * 30 = 9.0 min/month → 20.8%消費
v4.5: 0.155 * 30 = 4.65 min/month → 10.8%消費
```

v4.5ではレプリカ追加の効果がburn rateに正しく反映されるようになりました。

## v4.1〜v4.5の進化まとめ

| バージョン | 主要修正 | 代表的な可用性 | burn rate |
|-----------|---------|--------------|-----------|
| v4.1 | マルチWhat-if導入 | 99.50% | N/A |
| v4.2 | OVERLOADED状態の80%重み | 98.00% | N/A |
| v4.3 | max()統一・加重ダウンタイム | 99.50% | 0.00 min/day |
| v4.4 | MTBFキャップ(56h)・リスクベースburn rate | 98.70% | 0.33 min/day |
| **v4.5** | **fault-overlap・キャップ緩和(168h)・base_multiplier** | **99.25%** | **0.15 min/day** |

- **v4.1→v4.3**: 基盤の正確性向上（計算方式の統一・RNG汚染防止）
- **v4.3→v4.4**: 分析機能の実用化（MTTR感度・burn rate推定）
- **v4.4→v4.5**: 精度の洗練（過大評価の排除・モデルの正確性向上）

v4.5は、v4.4の「機能としては動く」状態から「**正確に動く**」状態への移行です。

## まとめ

### v4.5で修正した5件

| # | 修正内容 | 影響 |
|---|---------|------|
| 1 | MTBFキャップ緩和: sim/3 → duration_hours | 過剰な障害強制を解消（3回→1回/component） |
| 2 | fault-overlap計算 | ダウンタイム過大評価を解消（最大10倍→正確） |
| 3 | base_multiplier追加 | GROWTH_TREND成長率の保護 |
| 4 | CLI色判定: avg_availabilityベースに変更 | 一時的な障害による常時赤表示を解消 |
| 5 | burn rate: 1/replicas割引 | レプリカ冗長性の効果を反映（0.33→0.15 min/day） |

v4.1からv4.5まで累計20件のバグ修正と機能改善を重ね、シミュレーション結果の**定量的な信頼性**が大きく向上しました。

### 今後の展望

次のマイルストーンは**依存関係トポロジーを考慮したavailability計算**です。現在のInfraSimは各コンポーネントを独立に評価していますが、実際のインフラではPostgreSQLのDOWNがApp Serverに伝搬し、さらにLoad Balancerに波及します。

この依存関係の**伝搬**をモデル化し、「どのコンポーネントの障害がシステム全体に最も影響するか」をトポロジカルに評価する -- **グラフ構造としてのレジリエンス**を定量化するのがInfraSim v5.0の目標です。
