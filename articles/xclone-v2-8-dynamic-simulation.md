---
title: "Xクローン v2.8 — InfraSim v2.0: 動的シミュレーションで「定常状態の限界」を突破"
emoji: "🌊"
type: "tech"
topics: ["infrasim", "chaosengineering", "sre", "kubernetes", "aws"]
published: false
---

## はじめに — なぜ「定常状態」では不十分だったのか

[前回のv2.7記事](https://qiita.com/ymaeda_it/items/)で、InfraSimの1,647シナリオを**全てPASSED（100%）**に到達しました。6ラウンドの改善を経て、CRITICALもWARNINGもゼロという理想的な状態です。

しかし、この成果には根本的な限界がありました。

```
v2.7で達成したこと:
  ✅ 1,647シナリオ全PASSED
  ✅ CRITICAL 0 / WARNING 0
  ✅ レジリエンススコア 100/100

v2.7の限界:
  ❌ 全て「ある瞬間の状態」でしかない
  ❌ トラフィックは固定倍率（1x, 2x, 5x, 10x）のみ
  ❌ 時間経過という概念がない
  ❌ オートスケーリングの反応速度を評価できない
  ❌ フェイルオーバー中のダウンタイムを計測できない
```

**実際の障害は「定常状態」で起きるのではなく、時間変動するトラフィックパターンの中で発生します。**

- DDoS攻撃は10秒で0→10倍に急増し、ジッターを伴いながら持続する
- バイラルツイートは指数関数的に60秒で15倍に膨張し、その後緩やかに減衰する
- フラッシュクラウドは30秒で8倍に急騰し、その後直線的に戻る
- 日中のトラフィックはサイン波状に3倍まで上昇し、夜間に戻る

InfraSim v1.0では、これらの「時間軸上の変化」を一切シミュレートできませんでした。

### InfraSim v1.0の5つの限界

| # | 限界 | 影響 |
|---|------|------|
| 1 | **静的シミュレーション** — 時間経過の概念がない | DDoSの「10秒で10倍に急増」を表現できない |
| 2 | **オートスケーリング未対応** — HPAの反応速度を評価できない | 15秒のスケールアップ遅延中にPodが過負荷になる可能性を見落とす |
| 3 | **フェイルオーバー時間未計測** — プロモーション中のダウンタイムを見落とす | Aurora Primaryが落ちた後、30秒のプロモーション中はDB不在 |
| 4 | **レイテンシカスケード未対応** — 遅い依存がリトライストームを引き起こす | Aurora 20x遅延 → PgBouncer timeout → リトライ → コネクションプール枯渇 |
| 5 | **定常状態メトリクスのみ** — 日中/夜間の変動パターンを表現できない | ピーク時間帯にキャッシュが落ちるシナリオを評価できない |

本記事では、これらの限界を突破するために開発した**InfraSim v2.0**の設計・実装と、XClone v2インフラに対する**1,695シナリオの動的シミュレーション結果**を報告します。

### シリーズ記事

| # | 記事 | テーマ |
|---|------|--------|
| 1 | [**v2.0** — フルスタック基盤](https://qiita.com/ymaeda_it/items/902aa019456836624081) | Hono+Bun / Next.js 15 / Drizzle / ArgoCD / Linkerd / OTel |
| 2 | [**v2.1** — 品質・運用強化](https://qiita.com/ymaeda_it/items/e44ee09728795595efaa) | Playwright / OpenSearch ISM / マルチリージョンDB / tRPC / CDC |
| 3 | [**v2.2** — パフォーマンス](https://qiita.com/ymaeda_it/items/d858969cd6de808b8816) | 分散Rate Limit / 画像最適化 / マルチリージョンWebSocket |
| 4 | [**v2.3** — DX・コスト最適化](https://qiita.com/ymaeda_it/items/cf78cb33e6e461cdc2b3) | Feature Flag / GraphQL Federation / コストダッシュボード |
| 5 | [**v2.4** — テスト完備](https://qiita.com/ymaeda_it/items/44b7fca8fc0d07298727) | E2Eテスト拡充 / Terratest インフラテスト |
| 6 | [**v2.5** — カオステスト](https://qiita.com/ymaeda_it/items/bfe98a49e07cc80dbf32) | InfraSim / 296シナリオ / レジリエンス評価 |
| 7 | [**v2.6** — レジリエンス強化](https://qiita.com/ymaeda_it/items/817724b2936816f4f28c) | 3ラウンド改善 / WARNING 36→2 / 95%改善 |
| 8 | **v2.7** — 完全レジリエンス | 6ラウンド完結 / 1,647シナリオ全PASSED / 100%達成 |
| **9** | **v2.8 — 動的シミュレーション（本記事）** | **InfraSim v2.0 / 1,695シナリオ / 動的トラフィック / オートスケーリング / フェイルオーバー** |

### v2シリーズの全体像

```
v2.0: フルスタック基盤               (39ファイル)
  ↓
v2.1: 品質・運用強化                 (50ファイル)
  ↓
v2.2: パフォーマンス                 (55ファイル)
  ↓
v2.3: DX・コスト最適化               (61ファイル)
  ↓
v2.4: テスト完備                     (65ファイル) ← 機能的な改善点ゼロ
  ↓
v2.5: カオステスト                   InfraSimで296シナリオ実行
  ↓
v2.6: レジリエンス強化               3ラウンドで WARNING 36→2（95%削減）
  ↓
v2.7: 完全レジリエンス               6ラウンドで 1,647シナリオ全PASSED
  ↓
v2.8: 動的シミュレーション（本記事）  InfraSim v2.0で1,695シナリオ動的シミュレーション
```

---

## 2. InfraSim v2.0 — 5つの改良ポイント

InfraSim v2.0は、v1.0の「単一パス・固定倍率」モデルを**時間ステップ型シミュレーション**に進化させました。5つの改良ポイントを順に解説します。

### 2.1 TrafficPattern: 8種の時間変動トラフィックモデル

v1.0の `traffic_multiplier: float` は「トラフィックが常に一定」という非現実的な前提でした。v2.0ではこれを **8種類の時間変動パターン** に置き換えています。

```python
# src/infrasim/simulator/traffic.py

class TrafficPatternType(str, Enum):
    """シミュレート可能なトラフィックパターンの種類"""

    CONSTANT = "constant"           # 一定（v1.0互換）
    RAMP = "ramp"                   # 線形ランプ（上昇→維持→下降）
    SPIKE = "spike"                 # 瞬間スパイク（即座に急増→維持→即座に低下）
    WAVE = "wave"                   # サイン波（周期的な振動）
    DDoS_VOLUMETRIC = "ddos_volumetric"  # ボリュメトリックDDoS（急増+ジッター）
    DDoS_SLOWLORIS = "ddos_slowloris"    # Slowloris（緩やかな線形増加）
    FLASH_CROWD = "flash_crowd"     # フラッシュクラウド（指数増加→線形減衰）
    DIURNAL = "diurnal"             # 日中/夜間サイクル（コサイン波）
```

各パターンは `multiplier_at(t)` メソッドで**任意の秒数におけるトラフィック倍率**を返します。

```python
class TrafficPattern(BaseModel):
    """時間変動するトラフィックパターン"""

    pattern_type: TrafficPatternType
    peak_multiplier: float        # ベースラインに対するピーク倍率
    duration_seconds: int = 300   # パターンの総時間（秒）
    ramp_seconds: int = 0         # ランプアップ時間
    sustain_seconds: int = 0      # ピーク維持時間
    cooldown_seconds: int = 0     # クールダウン時間
    wave_period_seconds: int = 60 # WAVEパターンの1周期
    affected_components: list[str] = []  # 空なら全コンポーネント対象

    def multiplier_at(self, t: int) -> float:
        """時刻t（秒）におけるトラフィック倍率を返す（常に >= 1.0）"""
        if t < 0 or t >= self.duration_seconds:
            return 1.0
        # パターンタイプに応じた計算ロジックにディスパッチ
        ...
```

#### DDoS Volumetricパターンの詳細

最も重要なパターンであるボリュメトリックDDoSの動作を図示します。

```
DDoS Volumetric (10x peak, 300秒)

倍率
 10x |          ┌──────────────────────────────── (ジッター付き維持)
     |         /  ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~
  8x |        /     ±20%のランダムジッター
     |       /
  6x |      /
     |     /
  4x |    /
     |   /
  2x |  /
     | /
  1x |/
     └──────────────────────────────────────────→ 時間(秒)
     0   10                                   300
      ↑ ramp
```

実装は以下の通りです。

```python
def _ddos_volumetric(self, t: int) -> float:
    """10秒で急速ランプ → ±20%ジッター付きで維持"""
    peak = self.peak_multiplier
    ramp_duration = 10  # 固定10秒ランプ

    if t < ramp_duration:
        # 線形ランプ: 1.0 → peak
        return 1.0 + (peak - 1.0) * (t / ramp_duration)

    # peak ± 20%のジッター（シード固定RNGで再現可能）
    jitter = _rng.uniform(-0.20, 0.20)
    return max(1.0, peak * (1.0 + jitter))
```

#### Flash Crowdパターン: 指数関数的ランプ + 線形減衰

フラッシュクラウドはバイラルコンテンツによる急激なトラフィック増加を模倣します。

```
Flash Crowd (8x peak, 30秒ランプ, 300秒)

倍率
  8x |    *
     |   * \
  6x |  *   \
     | *     \
  4x |*       \
     |          \
  2x |           \
     |            \
  1x |─            ──────────────────────────→
     └───────────────────────────────────────→ 時間(秒)
     0  30                                  300
     ↑ 指数関数ランプ      ↑ 線形減衰
```

```python
def _flash_crowd(self, t: int) -> float:
    """Phase 1: 指数関数ランプ, Phase 2: 線形減衰"""
    ramp = self.ramp_seconds
    peak = self.peak_multiplier

    if ramp > 0 and t < ramp:
        # 指数関数: 1.0 * e^(k*t), t=ramp で peak に到達
        k = math.log(peak) / ramp
        return math.exp(k * t)

    # 残り時間で peak → 1.0 に線形減衰
    decay_duration = self.duration_seconds - ramp
    if decay_duration <= 0:
        return peak
    t_decay = t - ramp
    return peak - (peak - 1.0) * (t_decay / decay_duration)
```

#### ファクトリ関数

よく使うパターンはファクトリ関数で簡単に生成できます。

```python
# ボリュメトリックDDoS: 10秒でピークに達し、ジッター付きで維持
ddos = create_ddos_volumetric(peak=10.0, duration=300)

# Slowloris: 300秒かけて線形に5倍まで上昇
slowloris = create_ddos_slowloris(peak=5.0, duration=300)

# フラッシュクラウド: 30秒で指数関数的に8倍、その後線形減衰
flash = create_flash_crowd(peak=8.0, ramp=30, duration=300)

# バイラルイベント: 60秒ランプ→120秒維持→120秒クールダウン
viral = create_viral_event(peak=15.0, duration=300)

# 日中/夜間サイクル: サイン波で3倍ピーク
diurnal = create_diurnal(peak=3.0, duration=300)
```

---

### 2.2 DynamicSimulationEngine: 時間ステップ型シミュレーション

v1.0の `SimulationEngine` は「障害注入 → カスケード計算 → severity算出」の**単一パス**でした。v2.0の `DynamicSimulationEngine` は**5秒間隔 x 60ステップ = 300秒**の時間ステップ型シミュレーションです。

```
DynamicSimulationEngine のタイムステップフロー

     t=0s      t=5s      t=10s     t=15s     ...     t=295s    t=300s
      │         │          │         │                  │         │
      ▼         ▼          ▼         ▼                  ▼         ▼
  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐      ┌────────┐ ┌────────┐
  │Step 0  │ │Step 1  │ │Step 2  │ │Step 3  │ ...  │Step 59 │ │Step 60 │
  └───┬────┘ └───┬────┘ └───┬────┘ └───┬────┘      └───┬────┘ └───┬────┘
      │          │          │          │                │          │
      ▼          ▼          ▼          ▼                ▼          ▼
  各ステップで以下を実行:
    1. TrafficPattern.multiplier_at(t) でトラフィック倍率を取得
    2. 全コンポーネントの utilization を更新
    3. AutoScaling: 利用率 > 70% → 15秒後にスケールアップ
    4. Failover: 3回連続ヘルスチェック失敗 → プロモーション開始
    5. CascadeEngine: 障害のカスケード伝播を計算
    6. TimeStepSnapshot に全コンポーネント状態を記録
    7. peak_severity を追跡
```

#### DynamicScenario モデル

```python
class DynamicScenario(BaseModel):
    """動的シミュレーション用のカオスシナリオ"""

    id: str
    name: str
    description: str
    faults: list[Fault] = []            # 注入する障害
    traffic_pattern: TrafficPattern | None = None  # 時間変動トラフィック
    duration_seconds: int = 300         # シミュレーション時間
    time_step_seconds: int = 5          # ステップ間隔
```

#### TimeStepSnapshot: ある瞬間のシステム全体状態

```python
@dataclass
class TimeStepSnapshot:
    """シミュレーション時刻のシステム全体スナップショット"""

    time_seconds: int                                       # 時刻
    component_states: dict[str, ComponentSnapshot] = {}     # 各コンポーネントの状態
    active_replicas: dict[str, int] = {}                    # レプリカ数
    traffic_multiplier: float = 1.0                         # 現在のトラフィック倍率
    cascade_effects: list[CascadeEffect] = []               # カスケード効果

@dataclass
class ComponentSnapshot:
    """1コンポーネントのポイントインタイム状態"""

    component_id: str
    health: HealthStatus           # HEALTHY / DEGRADED / OVERLOADED / DOWN
    utilization: float             # 現在の利用率 (%)
    replicas: int                  # 現在のレプリカ数
    is_failing_over: bool = False  # フェイルオーバー中か
    failover_elapsed_seconds: int = 0  # プロモーション経過秒数
```

#### DynamicScenarioResult: シミュレーション結果

```python
@dataclass
class DynamicScenarioResult:
    """動的シナリオの実行結果"""

    scenario: DynamicScenario
    snapshots: list[TimeStepSnapshot] = []     # 全タイムステップの記録
    peak_severity: float = 0.0                 # 最大severity
    peak_time_seconds: int = 0                 # peak severityの時刻
    recovery_time_seconds: int | None = None   # 回復時刻
    autoscaling_events: list[str] = []         # スケーリングイベントログ
    failover_events: list[str] = []            # フェイルオーバーイベントログ

    @property
    def is_critical(self) -> bool:
        """severity >= 7.0 でCRITICAL"""
        return self.peak_severity >= 7.0

    @property
    def is_warning(self) -> bool:
        """severity 4.0-6.9 でWARNING"""
        return 4.0 <= self.peak_severity < 7.0
```

#### エンジンの中核: run_dynamic_scenario

```python
class DynamicSimulationEngine:

    def run_dynamic_scenario(self, scenario: DynamicScenario) -> DynamicScenarioResult:
        result = DynamicScenarioResult(scenario=scenario)

        # コンポーネントごとの可変状態を初期化
        comp_states = self._init_component_states()

        # トラフィックパターンの対象コンポーネントを解決
        affected_ids = self._resolve_affected_components(scenario.traffic_pattern)

        total_steps = scenario.duration_seconds // scenario.time_step_seconds

        for step_idx in range(total_steps + 1):
            t = step_idx * scenario.time_step_seconds

            # 1. トラフィック倍率を取得
            multiplier = 1.0
            if scenario.traffic_pattern is not None:
                multiplier = scenario.traffic_pattern.multiplier_at(t)

            # 2. 利用率を更新（レプリカ数を考慮）
            self._apply_traffic(comp_states, multiplier, affected_ids)

            # 3. オートスケーリング判定
            scaling_msgs = self._evaluate_autoscaling(comp_states, step_sec, t)
            result.autoscaling_events.extend(scaling_msgs)

            # 4. フェイルオーバー判定
            failover_msgs = self._evaluate_failover(comp_states, faults_by_target, step_sec, t)
            result.failover_events.extend(failover_msgs)

            # 5. カスケード計算
            step_effects = self._run_cascade_at_step(faults_by_target, comp_states, t)

            # 6. スナップショット記録
            snapshot = self._build_snapshot(comp_states, t, multiplier, step_effects)
            result.snapshots.append(snapshot)

            # 7. severity追跡
            step_severity = self._severity_for_step(comp_states, step_effects)
            if step_severity > peak_severity:
                peak_severity = step_severity
                peak_time = t

        result.peak_severity = round(peak_severity, 1)
        return result
```

---

### 2.3 AutoScaling シミュレーション

v2.0の最も重要な改良の1つが**オートスケーリングのシミュレーション**です。Kubernetes HPAやKEDAのスケーリング動作を、遅延付きでモデリングしています。

#### AutoScalingConfig

```python
class AutoScalingConfig(BaseModel):
    """HPA/KEDAオートスケーリング設定"""

    enabled: bool = False
    min_replicas: int = 1
    max_replicas: int = 1
    scale_up_threshold: float = 70.0     # 利用率がこれを超えたらスケールアップ
    scale_down_threshold: float = 30.0   # 利用率がこれを下回ったらスケールダウン
    scale_up_delay_seconds: int = 15     # スケールアップ遅延（Pod起動時間）
    scale_down_delay_seconds: int = 300  # スケールダウンクールダウン
    scale_up_step: int = 2              # 1回のスケールアップで追加するレプリカ数
```

#### スケーリングロジック

```python
def _evaluate_autoscaling(self, states, step_sec, t):
    events = []
    for comp_id, state in states.items():
        cfg = self.graph.get_component(comp_id).autoscaling
        if not cfg.enabled:
            continue

        util = state.current_utilization

        # --- スケールアップ ---
        if util > cfg.scale_up_threshold:
            state.pending_scale_up_seconds += step_sec
            if state.pending_scale_up_seconds >= cfg.scale_up_delay_seconds:
                new_replicas = min(
                    state.current_replicas + cfg.scale_up_step,
                    cfg.max_replicas,
                )
                if new_replicas > state.current_replicas:
                    events.append(
                        f"[t={t}s] AUTO-SCALE UP {comp_id}: "
                        f"{state.current_replicas} -> {new_replicas} replicas"
                    )
                    state.current_replicas = new_replicas
                state.pending_scale_up_seconds = 0

        # --- スケールダウン ---
        if util < cfg.scale_down_threshold:
            state.pending_scale_down_seconds += step_sec
            if state.pending_scale_down_seconds >= cfg.scale_down_delay_seconds:
                new_replicas = max(state.current_replicas - 1, cfg.min_replicas)
                if new_replicas < state.current_replicas:
                    events.append(
                        f"[t={t}s] AUTO-SCALE DOWN {comp_id}: "
                        f"{state.current_replicas} -> {new_replicas} replicas"
                    )
                    state.current_replicas = new_replicas

    return events
```

#### 利用率とレプリカの関係

スケールアウト後の利用率は以下の式で計算されます。

```
effective_utilization = base_utilization * traffic_multiplier * (base_replicas / current_replicas)
```

**実例: DDoS 10x時のhono-api-1**

```
初期状態:
  base_utilization = 7%
  base_replicas = 6
  traffic_multiplier = 10x
  → 実効利用率 = 7% * 10 * (6/6) = 70%  ← threshold超過!

15秒後（スケールアップ実行）:
  current_replicas = 6 + 2 = 8
  → 実効利用率 = 7% * 10 * (6/8) = 52.5%  ← threshold以下

さらに15秒後（利用率が依然高い場合）:
  current_replicas = 8 + 2 = 10
  → 実効利用率 = 7% * 10 * (6/10) = 42%

最終的に:
  current_replicas = 12
  → 実効利用率 = 7% * 10 * (6/12) = 35%  ← 安定
```

```
DDoS 10x でのオートスケーリング動作タイムライン

  レプリカ数
  12 |                              ┌───────────────────────
     |                    ┌─────────┘
  10 |                    │
     |          ┌─────────┘
   8 |          │
     |    ┌─────┘
   6 |────┘
     └──────────────────────────────────────────────→ 時間(秒)
     0   10  15  25  30  40  45                     300
         ↑   ↑       ↑       ↑
       DDoS  1st     2nd     3rd
       開始  scale   scale   scale
```

---

### 2.4 Failover タイミングシミュレーション

オートスケーリングが「水平スケーリングの遅延」を評価するなら、フェイルオーバーシミュレーションは**「プロモーションに要する時間中のダウンタイム」**を正確に計測します。

#### FailoverConfig

```python
class FailoverConfig(BaseModel):
    """フェイルオーバー/プロモーション設定"""

    enabled: bool = False
    promotion_time_seconds: int = 30    # レプリカ→プライマリのプロモーション時間
    health_check_interval_seconds: int = 10  # ヘルスチェック間隔
    failover_threshold: int = 3         # 連続失敗回数しきい値
```

#### 3フェーズのフェイルオーバーステートマシン

```
フェイルオーバーの3フェーズ

Phase 1: 検出                    Phase 2: プロモーション         Phase 3: 回復
┌─────────────────┐             ┌──────────────────────┐        ┌────────────────┐
│ コンポーネントDOWN│             │ プロモーション中     │        │ 回復中         │
│                  │             │                      │        │                │
│ ヘルスチェック    │  threshold  │ ステータス: DOWN     │ 完了   │ ステータス:     │  完了
│ 毎10秒実行       │──到達──→   │ promotion_time_sec   │──→    │  DEGRADED      │──→ HEALTHY
│                  │  (3回連続)  │ 秒間待機             │        │ (promotion/2   │
│ 失敗カウント++   │             │                      │        │  秒間)         │
└─────────────────┘             └──────────────────────┘        └────────────────┘

タイムライン:
  t=0s     障害発生                  ステータス: DOWN
  t=10s    ヘルスチェック #1 失敗    DOWN (1/3)
  t=20s    ヘルスチェック #2 失敗    DOWN (2/3)
  t=30s    ヘルスチェック #3 失敗    DOWN (3/3) → プロモーション開始!
  t=30-60s プロモーション中          DOWN (30秒間)
  t=60s    プロモーション完了        DEGRADED
  t=60-75s 回復期間                  DEGRADED (15秒間)
  t=75s    完全回復                  HEALTHY
```

**合計ダウンタイム: 約60秒**（検出30秒 + プロモーション30秒）

#### 実装

```python
def _evaluate_failover(self, states, faults_by_target, step_sec, t):
    events = []
    for comp_id, state in states.items():
        cfg = self.graph.get_component(comp_id).failover
        if not cfg.enabled:
            continue

        # Phase 3: ポストフェイルオーバー回復
        if state.post_failover_recovery_seconds > 0:
            state.post_failover_recovery_seconds -= step_sec
            if state.post_failover_recovery_seconds <= 0:
                state.current_health = HealthStatus.HEALTHY
                events.append(f"[t={t}s] FAILOVER RECOVERED {comp_id}")
            continue

        # Phase 2: プロモーション進行中
        if state.is_failing_over:
            state.failover_elapsed_seconds += step_sec
            state.current_health = HealthStatus.DOWN
            if state.failover_elapsed_seconds >= state.failover_total_seconds:
                state.is_failing_over = False
                state.current_health = HealthStatus.DEGRADED
                recovery_period = max(step_sec, cfg.promotion_time_seconds // 2)
                state.post_failover_recovery_seconds = recovery_period
                events.append(
                    f"[t={t}s] FAILOVER PROMOTED {comp_id}: "
                    f"entering recovery (DEGRADED for ~{recovery_period}s)"
                )
            continue

        # Phase 1: 障害検出（連続ヘルスチェック失敗カウント）
        if state.current_health == HealthStatus.DOWN or is_faulted_down:
            state.current_health = HealthStatus.DOWN
            checks = max(1, step_sec // max(1, cfg.health_check_interval_seconds))
            state.consecutive_health_failures += checks

            if state.consecutive_health_failures >= cfg.failover_threshold:
                state.is_failing_over = True
                state.failover_total_seconds = cfg.promotion_time_seconds
                events.append(
                    f"[t={t}s] FAILOVER STARTED {comp_id}: "
                    f"promoting replica ({cfg.promotion_time_seconds}s)"
                )
```

#### Aurora Primary障害時の計測例

```
Aurora Primary (promotion_time=30s, health_check_interval=10s, threshold=3)

  t=0s    障害発生             → DOWN
  t=5s    ステップ処理          → 1回分ヘルスチェック失敗カウント
  t=10s   ステップ処理          → 2回分ヘルスチェック失敗カウント
  t=15s   ステップ処理          → 3回分 → threshold到達! → FAILOVER STARTED
  t=15-45s プロモーション中     → DOWN (30秒間)
  t=45s   プロモーション完了    → DEGRADED
  t=45-60s 回復期間             → DEGRADED (15秒間)
  t=60s   完全回復             → HEALTHY

正確なダウンタイム: 約60秒
（v1.0ではこの60秒のダウンタイムを一切計測できなかった）
```

---

### 2.5 レイテンシカスケード: タイムアウト伝播とリトライストーム

フェイルオーバーシミュレーションが「コンポーネントがDOWNした場合」を扱うのに対し、レイテンシカスケードは**「コンポーネントがDOWNではないが遅い場合」**に何が起きるかをシミュレートします。

これは実際の本番障害で最も厄介なパターンです。

```
レイテンシカスケードの連鎖

  Aurora 20x遅延
      │
      ▼
  PgBouncer: timeout=30s, 実際応答=60s → タイムアウト!
      │                                  → リトライ発生 (3x)
      │                                  → コネクションプール枯渇
      ▼
  Envoy Circuit Breaker: 上流遅延伝播
      │                                  → リトライストーム増幅
      │                                  → pool_size 100 に対し 420-630接続が殺到
      ▼
  hono-api-1~12: タイムアウト待ち → スレッドプール枯渇
      │
      ▼
  ALB: 504 Gateway Timeout → ユーザー影響
```

#### simulate_latency_cascade の実装

```python
def simulate_latency_cascade(self, slow_component_id, latency_multiplier=10.0):
    """遅いコンポーネントからのレイテンシカスケードをシミュレート"""

    chain = CascadeChain(
        trigger=f"Latency cascade from {slow_component_id} ({latency_multiplier}x)",
        total_components=len(self.graph.components),
    )

    slow_comp = self.graph.get_component(slow_component_id)

    # ベースレイテンシ = timeout_seconds * 1000 * 0.1 (タイムアウトの10%が通常レイテンシ)
    base_latency = slow_comp.capacity.timeout_seconds * 1000 * 0.1
    slow_latency = base_latency * latency_multiplier

    # BFSで依存コンポーネントに伝播
    visited = {slow_component_id}
    bfs_queue = deque()

    # 遅延コンポーネントに依存するコンポーネントをシードとしてキューに追加
    for dep_comp in self.graph.get_dependents(slow_component_id):
        edge = self.graph.get_dependency_edge(dep_comp.id, slow_component_id)
        edge_latency = edge.latency_ms if edge else 0.0
        bfs_queue.append((dep_comp.id, slow_latency + edge_latency))
        visited.add(dep_comp.id)

    while bfs_queue:
        comp_id, accumulated_latency = bfs_queue.popleft()
        comp = self.graph.get_component(comp_id)

        timeout_ms = comp.capacity.timeout_seconds * 1000
        retry_mult = comp.capacity.retry_multiplier
        pool_size = comp.capacity.connection_pool_size

        if timeout_ms > 0 and accumulated_latency > timeout_ms:
            # タイムアウト超過 → リトライストーム
            effective_connections = comp.metrics.network_connections * retry_mult

            if pool_size > 0 and effective_connections > pool_size:
                # コネクションプール枯渇 → DOWN
                health = HealthStatus.DOWN
                reason = (
                    f"Pool exhausted: {effective_connections:.0f} "
                    f"effective connections > pool size {pool_size}"
                )
            else:
                health = HealthStatus.DOWN
                reason = f"Timeout: {accumulated_latency:.0f}ms > {timeout_ms:.0f}ms"

            chain.effects.append(CascadeEffect(
                component_id=comp.id,
                health=health,
                reason=reason,
                latency_ms=accumulated_latency,
            ))

            # カスケード継続: 次の依存に伝播
            for next_dep in self.graph.get_dependents(comp_id):
                if next_dep.id not in visited:
                    edge = self.graph.get_dependency_edge(next_dep.id, comp_id)
                    next_latency = accumulated_latency + (edge.latency_ms if edge else 0)
                    bfs_queue.append((next_dep.id, next_latency))
                    visited.add(next_dep.id)

    return chain
```

#### Aurora 20x遅延時の実結果

```
Aurora 20x レイテンシカスケード:

  起点: aurora-primary (base_latency=3000ms, 20x → 60,000ms)
    │
    ├→ pgbouncer-1~4: timeout=30,000ms < 60,000ms → TIMEOUT
    │   └→ リトライ 3x → connections 200*3 = 600 > pool_size 100 → DOWN
    │
    ├→ envoy-cb-1~12: 上流DOWN → タイムアウト伝播
    │   └→ connections 350*3 = 1,050 > pool_size 100 → DOWN
    │
    ├→ hono-api-1~12: 依存先DOWN → カスケードDOWN
    │
    └→ ALB/CloudFront: 全バックエンドDOWN → 504

影響コンポーネント: 32
severity: 6.8 (WARNING)
```

---

## 3. XClone v2 YAML v7 — オートスケーリング/フェイルオーバー設定追加

InfraSim v2.0の動的シミュレーション機能を活用するため、XCloneのインフラ定義YAMLをv6からv7にアップグレードしました。主要な追加設定を示します。

### API Pods (hono-api): HPA設定

```yaml
# infra/infrasim-xclone.yaml (v7)
- id: hono-api-1
  name: "Hono API Pod 1 (EKS)"
  type: app_server
  replicas: 6
  capacity:
    max_connections: 5000
    connection_pool_size: 100
    timeout_seconds: 30
    retry_multiplier: 3.0
  metrics:
    cpu_percent: 8
    memory_percent: 7
    disk_percent: 5
    network_connections: 350
  autoscaling:
    enabled: true
    min_replicas: 6
    max_replicas: 24
    scale_up_threshold: 70
    scale_down_threshold: 30
    scale_up_delay_seconds: 15
    scale_down_delay_seconds: 300
    scale_up_step: 2
```

**設計思想**: 通常時は6レプリカ。10xトラフィック時にはHPAが15秒ごとに2レプリカずつ追加し、最大24レプリカまでスケールアウト。

### Aurora PostgreSQL: フェイルオーバー設定

```yaml
- id: aurora-primary
  name: "Aurora PostgreSQL (Primary)"
  type: database
  replicas: 3  # Primary + 2 Replicas
  capacity:
    max_connections: 5000
    timeout_seconds: 30
  metrics:
    cpu_percent: 7
    memory_percent: 8
    disk_percent: 8
    network_connections: 150
  failover:
    enabled: true
    promotion_time_seconds: 30
    health_check_interval_seconds: 10
    failover_threshold: 3
```

**設計思想**: Aurora Primaryが障害を起こした場合、3回のヘルスチェック失敗（30秒）後にレプリカがプロモーション開始。30秒のプロモーション時間を経て復旧。

### Redis Cluster: フェイルオーバー設定

```yaml
- id: redis-cluster
  name: "ElastiCache Redis Cluster (3 shards x 3 replicas)"
  type: cache
  replicas: 9
  capacity:
    max_connections: 200000
  metrics:
    cpu_percent: 3
    memory_percent: 5
    network_connections: 1500
  failover:
    enabled: true
    promotion_time_seconds: 15
    health_check_interval_seconds: 5
    failover_threshold: 3
```

**設計思想**: Redis Clusterは各シャードにレプリカがあるため、プロモーション時間はAuroraの半分（15秒）。ヘルスチェック間隔も5秒と短い。

### PgBouncer: オートスケーリング + フェイルオーバー

```yaml
- id: pgbouncer-1
  name: "PgBouncer (Connection Pooler) Pod 1"
  type: app_server
  replicas: 2
  capacity:
    max_connections: 5000
    connection_pool_size: 100
    timeout_seconds: 30
  metrics:
    cpu_percent: 5
    memory_percent: 5
    network_connections: 200
  autoscaling:
    enabled: true
    min_replicas: 2
    max_replicas: 8
    scale_up_threshold: 60
    scale_down_threshold: 25
    scale_up_delay_seconds: 10
    scale_up_step: 2
  failover:
    enabled: true
    promotion_time_seconds: 5
    health_check_interval_seconds: 5
    failover_threshold: 2
```

**設計思想**: PgBouncerはステートレスなため、フェイルオーバーは非常に高速（5秒）。スケーリングも10秒遅延で反応する。

### WebSocket: オートスケーリング設定

```yaml
- id: websocket-1
  name: "Socket.io WebSocket Server 1 (EKS)"
  type: web_server
  replicas: 3
  capacity:
    max_connections: 50000
  metrics:
    cpu_percent: 5
    memory_percent: 7
    network_connections: 1500
  autoscaling:
    enabled: true
    min_replicas: 3
    max_replicas: 12
    scale_up_threshold: 60
    scale_down_threshold: 25
    scale_up_delay_seconds: 10
    scale_up_step: 2
```

### 全コンポーネントの設定一覧

| コンポーネント | AutoScaling | Failover | min→max | threshold | promotion |
|---------------|:-----------:|:--------:|---------|-----------|-----------|
| hono-api (x12) | ✅ | - | 6→24 | 70% | - |
| websocket (x6) | ✅ | - | 3→12 | 60% | - |
| pgbouncer (x4) | ✅ | ✅ | 2→8 | 60% | 5s |
| aurora-primary | - | ✅ | - | - | 30s |
| aurora-replica (x2) | - | ✅ | - | - | 30s |
| redis-cluster | - | ✅ | - | - | 15s |
| opensearch | ✅ | - | 2→8 | 75% | - |
| kafka (x3) | ✅ | - | 3→9 | 70% | - |

---

## 4. テスト結果 — 1,695シナリオ動的シミュレーション

### 4.1 全体結果

InfraSim v2.0で実行した1,695シナリオの結果です。

```
╔══════════════════════════════════════════════════════════════════╗
║  InfraSim v2.0 Dynamic Simulation Report                        ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  Total Scenarios:  1,695                                         ║
║    - Static (v1.0 wrapped):      1,647                          ║
║    - Dynamic traffic patterns:       9                          ║
║    - Dynamic wrappers (compound):   39                          ║
║                                                                  ║
║  Results:                                                        ║
║    CRITICAL:  2  (全インフラ同時故障 / LB-App全面ネットワーク分断)║
║    WARNING:   2  (Rolling restart + Flash crowd cache stampede)  ║
║    PASSED: 1,691                                                 ║
║                                                                  ║
║  Pass Rate: 99.76% (1,691 / 1,695)                              ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
```

v2.7（InfraSim v1.0）では1,647シナリオ全PASSEDでしたが、v2.0の動的シミュレーションにより**現実的に検出すべき問題を新たに発見**しました。

| 種別 | 件数 | 内容 |
|------|------|------|
| CRITICAL | 2 | 全コンポーネント同時障害（理論的最悪ケース）/ LB-App間全面ネットワーク分断 |
| WARNING | 1 (static) | Rolling restart failure |
| WARNING | 1 (dynamic) | Flash crowd 15x + cache stampede（severity 4.3） |
| PASSED | 1,691 | その他全てのシナリオ |

CRITICALの2件はv2.7と同じ「理論的最悪ケース」であり、実運用で発生する確率は極めて低いシナリオです。注目すべきは**動的シミュレーションで新たにWARNINGとなった1件**（Flash crowd 15x + cache stampede）です。

---

### 4.2 動的トラフィックパターン結果（9シナリオ詳細）

| # | シナリオ | パターン | Peak倍率 | Severity | AutoScale | Failover | 結果 |
|---|---------|----------|---------|----------|-----------|----------|------|
| 1 | DDoS Volumetric 10x | ddos_volumetric | 10x | 0.9 | 5イベント | - | **PASSED** |
| 2 | DDoS Slowloris 5x | ddos_slowloris | 5x | 0.0 | 2イベント | - | **PASSED** |
| 3 | Flash Crowd 8x | flash_crowd | 8x | 0.0 | - | - | **PASSED** |
| 4 | Viral Event 15x + DB failure | ramp | 15x | 3.5 | 16イベント | 24イベント | **PASSED** |
| 5 | Diurnal 3x + cache failure | diurnal | 3x | 0.9 | 3イベント | - | **PASSED** |
| 6 | Spike 5x during deployment | spike | 5x | 0.3 | - | - | **PASSED** |
| 7 | DDoS 10x + network partition | ddos_volumetric | 10x | 2.1 | 5イベント | 15イベント | **PASSED** |
| 8 | Wave 5x + memory exhaustion | wave | 5x | 0.3 | 1イベント | - | **PASSED** |
| 9 | Flash Crowd 15x + cache stampede | flash_crowd | 15x | **4.3** | 38イベント | 28イベント | **WARNING** |

#### シナリオ1: DDoS Volumetric 10x — severity 0.9, PASSED

```
DDoS Volumetric 10x — タイムライン:

  t=0s     トラフィック: 1x      全コンポーネント HEALTHY
  t=10s    トラフィック: 10x     hono-api利用率: 70% → threshold超過
  t=15s    AUTO-SCALE UP: hono-api 6→8  (15秒の遅延後)
  t=25s    AUTO-SCALE UP: hono-api 8→10
  t=35s    AUTO-SCALE UP: hono-api 10→12
  t=45s    AUTO-SCALE UP: hono-api 12→14
  t=55s    AUTO-SCALE UP: hono-api 14→16
  ...
  t=300s   終了。peak_severity: 0.9

  スケーリングイベント: 5回
  最大レプリカ数: 16
  ダウンタイム: なし
```

**10x DDoSに対してオートスケーリングが正常に機能。** 15秒の遅延はあるものの、初期の6レプリカが十分なヘッドルームを持っているため（ベースライン利用率7%）、10x時でも70%程度に収まり、スケーリングが追いつきます。

#### シナリオ4: Viral Event 15x + DB failure — severity 3.5, PASSED

最も過酷なPASSEDシナリオです。15倍のバイラルトラフィックとDB Primary障害が同時発生します。

```
Viral Event 15x + DB failure — タイムライン:

  t=0s     Aurora Primary DOWN + トラフィック: 1x
  t=5s     フェイルオーバー検出開始（ヘルスチェック失敗 1/3）
  t=10s    ヘルスチェック失敗 2/3
  t=15s    ヘルスチェック失敗 3/3 → FAILOVER STARTED（30秒プロモーション）
  t=30s    トラフィック: 5x（ランプ中）、hono-api AUTO-SCALE UP 6→8
  t=45s    FAILOVER PROMOTED aurora-primary → DEGRADED
  t=50s    トラフィック: 10x、さらにスケーリング続行
  t=60s    aurora-primary → HEALTHY（回復完了）
  t=60s    トラフィック: 15x（ピーク到達）
  t=60-180s ピーク維持、スケーリングイベント多数
  t=180-300s クールダウン、スケールダウン開始

  スケーリングイベント: 16回
  フェイルオーバーイベント: 24回
  peak_severity: 3.5（DB障害 + 15xトラフィックの複合効果）
  ダウンタイム: aurora-primary が約60秒間DOWNだがレプリカがカバー
```

#### シナリオ9: Flash Crowd 15x + cache stampede — severity 4.3, WARNING

**唯一の動的WARNING。** 15倍のフラッシュクラウドと全キャッシュノード障害の同時発生です。

```
Flash Crowd 15x + cache stampede — タイムライン:

  t=0s     全cache DOWN + トラフィック: 1x
  t=10s    トラフィック: 3x（指数関数ランプ中）
  t=20s    トラフィック: 7x
  t=25s    トラフィック: 12x
  t=30s    トラフィック: 15x（ピーク到達）
           └→ キャッシュ不在 × 15xトラフィック = Auroraに全リクエスト直撃
           └→ hono-api AUTO-SCALE UP 6→8→10→12...
           └→ PgBouncer AUTO-SCALE UP 2→4→6→8
           └→ aurora-primary 利用率急上昇
  t=30-60s フェイルオーバー多数発生（Redis Cluster、PgBouncer）
  t=60s    peak_severity: 4.3（WARNING帯に突入）

  スケーリングイベント: 38回（大量のスケールアップ/ダウン）
  フェイルオーバーイベント: 28回
  peak_severity: 4.3
  → キャッシュウォーミング戦略の不在が根本原因
```

**このWARNINGはv1.0では検出不可能でした。** v1.0の「キャッシュDOWN + 15xトラフィック」はPASSEDでしたが、動的シミュレーションでは「指数関数的に急増するトラフィック × キャッシュ不在 × オートスケーリング遅延」の複合効果が正しく計測されます。

---

### 4.3 レイテンシカスケード結果

レイテンシカスケードシミュレーションはDynamicSimulationEngineとは別に `CascadeEngine.simulate_latency_cascade()` で実行しました。

```
Aurora 20x レイテンシカスケード — 結果:

  起点: aurora-primary (base_latency=3,000ms, 20x → 60,000ms)

  影響の伝播:
  ┌──────────────────────────────────────────────────────────────┐
  │ コンポーネント      │ 蓄積レイテンシ │ timeout  │ 結果     │
  ├──────────────────────────────────────────────────────────────┤
  │ aurora-primary      │ 60,000ms       │ -        │ DEGRADED │
  │ pgbouncer-1~4       │ 60,000ms+      │ 30,000ms │ DOWN     │
  │ envoy-cb-1~12       │ 60,000ms+      │ 30,000ms │ DOWN     │
  │ hono-api-1~12       │ カスケードDOWN  │ 30,000ms │ DOWN     │
  │ websocket-1~6       │ カスケードDOWN  │ -        │ DOWN     │
  │ ALB                 │ 全バックエンドDOWN│ -       │ DOWN     │
  └──────────────────────────────────────────────────────────────┘

  リトライストーム詳細:
    PgBouncer: connections 200 * retry_multiplier 3.0 = 600 > pool_size 100
    Envoy CB: connections 350 * retry_multiplier 3.0 = 1,050 > pool_size 100

  影響コンポーネント: 32 / 全コンポーネント
  severity: 6.8 (WARNING)
  原因: PgBouncer→Aurora間のサーキットブレーカーが未設定
```

**重要な発見**: Envoy Circuit Breakerは各API Pod前段にあるが、PgBouncer→Aurora間にはサーキットブレーカーがない。Aurora遅延時にPgBouncerのコネクションプール（100）が3xリトライで600接続に膨張し、プール枯渇を引き起こす。

```
リトライストームの増幅メカニズム:

  正常時:
    クライアント → PgBouncer(200conn) → Aurora
                    pool_size: 100
                    リトライなし

  Aurora 20x遅延時:
    クライアント → PgBouncer(200conn * 3retry = 600conn) → Aurora(60,000ms応答)
                    pool_size: 100
                    ↑ 600 > 100 → プール枯渇 → DOWN

    さらに:
    Envoy CB → PgBouncer(DOWN) → タイムアウト
    Envoy CB(350conn * 3retry = 1,050conn) → PgBouncer
              pool_size: 100
              ↑ 1,050 > 100 → プール枯渇 → DOWN
```

---

## 5. v2.7 (静的) vs v2.8 (動的) の比較

| 項目 | v2.7 (InfraSim v1.0) | v2.8 (InfraSim v2.0) |
|------|---------------------|---------------------|
| **シミュレーション方式** | 単一パス、固定倍率 | 時間ステップ（5秒 x 60） |
| **トラフィックモデル** | `traffic_multiplier: float` | `TrafficPattern` (8種) |
| **オートスケーリング** | 未対応 | HPA/KEDA シミュレーション |
| **フェイルオーバー** | 未対応 | 検出→プロモーション→復旧 |
| **レイテンシカスケード** | 未対応 | タイムアウト伝播+リトライストーム |
| **シナリオ数** | 1,647 | 1,695+ |
| **CRITICAL** | 2件 | 2件（同一シナリオ） |
| **WARNING** | 0件 | 2件（+Rolling restart, +Flash crowd stampede） |
| **PASSED** | 1,645件 | 1,691件 |
| **検出可能な問題** | SPOF、容量超過 | +スケーリング遅延、フェイルオーバーダウンタイム、カスケード遅延 |
| **YAML version** | v6 | v7（autoscaling + failover設定追加） |

### 新たに検出できた問題

| # | 問題 | 検出方法 | v1.0での結果 |
|---|------|---------|-------------|
| 1 | Flash crowd 15x + cache stampede の複合影響 | 動的トラフィック + オートスケーリング遅延 | PASSED（静的10xは耐えた） |
| 2 | Aurora 20x遅延時のリトライストーム | レイテンシカスケード | severity未計測 |
| 3 | フェイルオーバー中の60秒ダウンタイム | フェイルオーバーシミュレーション | 時間の概念なし |
| 4 | DDoS初期15秒のスケーリング遅延期間 | オートスケーリングシミュレーション | 瞬時スケール前提 |

### InfraSim v1.0 vs v2.0 のアーキテクチャ比較

```
InfraSim v1.0:
  ┌─────────────┐     ┌──────────────┐     ┌─────────────┐
  │ Scenario     │────→│ CascadeEngine │────→│ ScenarioResult│
  │ (固定倍率)   │     │ (単一パス)    │     │ (severity)    │
  └─────────────┘     └──────────────┘     └─────────────┘

InfraSim v2.0:
  ┌─────────────────┐     ┌───────────────────────────────────┐
  │ DynamicScenario  │────→│ DynamicSimulationEngine            │
  │ + TrafficPattern │     │                                     │
  └─────────────────┘     │  for t in range(0, 300, 5):         │
                          │    ├── multiplier_at(t)              │
                          │    ├── _apply_traffic()              │
                          │    ├── _evaluate_autoscaling()       │
                          │    ├── _evaluate_failover()          │
                          │    ├── _run_cascade_at_step()        │
                          │    └── _build_snapshot()             │
                          │                                      │
                          │  ┌─────────────────────────────┐     │
                          │  │ DynamicScenarioResult        │     │
                          │  │ - snapshots[61]              │     │
                          │  │ - peak_severity              │     │
                          │  │ - autoscaling_events[]       │     │
                          │  │ - failover_events[]          │     │
                          │  └─────────────────────────────┘     │
                          └───────────────────────────────────────┘
```

---

## 6. 残る課題と今後

### 6.1 Flash Crowd 15x + cache stampede (severity 4.3)

このWARNINGの根本原因は**キャッシュウォーミング戦略の不在**です。

```
現状の問題:
  全キャッシュDOWN + 15xフラッシュクラウド
  → 全リクエストがAuroraに直撃
  → オートスケーリングが追いつかない（38回のスケールイベントが発生）

対策案:
  1. キャッシュウォーミング
     - キャッシュ復旧時にホットデータを事前ロード
     - local-cache (in-memory LRU) がフォールバックとして機能するが、
       15xトラフィックには容量不足
  2. Singleflightパターン
     - 同一キーへの並行リクエストを1つにまとめる
     - キャッシュミス時のDB負荷を大幅に軽減
  3. Request Coalescing
     - PgBouncer層でリクエスト集約
     - 同一クエリの重複実行を防止
```

### 6.2 レイテンシカスケード severity 6.8

```
現状の問題:
  PgBouncer → Aurora間にサーキットブレーカーがない
  → Aurora遅延時にリトライストームがコネクションプールを枯渇させる

対策案:
  1. PgBouncer→Aurora間のサーキットブレーカー追加
     - PgBouncer設定: server_connect_timeout + query_timeout
     - 連続タイムアウト時に接続を切断し、リトライを抑制
  2. Adaptive Retry
     - 固定3xリトライから、指数バックオフ + ジッター付きリトライに変更
     - retry_budget (1秒あたりのリトライ数上限) を導入
  3. Connection Pool Sizing
     - pool_size 100 は通常時には十分だが、リトライストーム耐性が不足
     - pool_size を 300 に拡大し、バースト耐性を確保
```

### 6.3 シミュレーションの理想化について

現在のオートスケーリングシミュレーションには以下の簡略化があります。

```
現在のモデル:
  - スケールアップ遅延: 15秒（一律）
  - スケールアップ: 即座にレプリカが稼働
  - CPU/メモリ: ベースライン利用率のスケーリングのみ

実際のKubernetes HPA:
  - Pod起動: 30-60秒（コンテナイメージのプル + 起動シーケンス）
  - メトリクス収集: 15-30秒の遅延（metrics-server polling interval）
  - Stabilization Window: 連続してしきい値を超えないとスケールしない
  - Node追加: Cluster Autoscalerの場合、さらに2-5分の遅延
```

今後のバージョンでは、これらの現実的な遅延を組み込むことで、より精度の高いシミュレーションを実現する予定です。

### 6.4 将来の発展方向

```
将来の発展ロードマップ:

InfraSim v2.0 (現在):
  - 時間ステップ型シミュレーション
  - 8種のトラフィックパターン
  - オートスケーリング / フェイルオーバー
  - レイテンシカスケード

InfraSim v2.1 (予定):
  - 現実的なPod起動遅延 (30-60秒)
  - Cluster Autoscaler シミュレーション
  - カスタムHPAメトリクス (KEDA ScaledObject)

InfraSim v3.0 (構想):
  - Prometheus/CloudWatch連携
  - 実メトリクス駆動シミュレーション
  - ML-based トラフィック予測
  - Chaos Mesh / LitmusChaos 連携
```

---

## 7. まとめ

### 達成したこと

InfraSim v2.0で「定常状態の限界」を突破し、**時間軸を持つ動的シミュレーション**を実現しました。

```
InfraSim v1.0 → v2.0 の進化:

  v1.0: 「この障害が起きたら、システムの状態はどうなるか？」
         → 単一時点のスナップショット
         → 1,647シナリオ全PASSED

  v2.0: 「この障害とトラフィック変動が300秒間続いたら、
          オートスケーリングとフェイルオーバーは間に合うか？」
         → 61タイムステップの完全なタイムライン
         → 1,695シナリオ、新たなWARNINGを検出
```

### 1,695シナリオの最終結果

```
╔════════════════════════════════════════════════════════════╗
║  XClone v2.8 — InfraSim v2.0 Dynamic Simulation          ║
╠════════════════════════════════════════════════════════════╣
║                                                            ║
║  CRITICAL:    2  (理論的最悪ケースのみ)                    ║
║  WARNING:     2  (Rolling restart + Flash crowd stampede)  ║
║  PASSED:  1,691                                            ║
║                                                            ║
║  Pass Rate: 99.76%                                         ║
║                                                            ║
║  新たに検出した問題:                                       ║
║    - Flash crowd 15x + cache stampede (severity 4.3)       ║
║    - Aurora 20x latency cascade (severity 6.8)             ║
║    - Failover downtime: ~60秒 (Aurora Primary)             ║
║    - Scaling delay: 15秒 (HPA初回反応)                     ║
║                                                            ║
║  オートスケーリング検証:                                   ║
║    ✅ DDoS 10x → 6→16 pods で吸収                         ║
║    ✅ Viral 15x → 16回のスケールイベントで対処             ║
║    ⚠️ Flash 15x + cache → 38回のスケールで追いつかず       ║
║                                                            ║
║  フェイルオーバー検証:                                     ║
║    ✅ Aurora Primary → 60秒で回復                          ║
║    ✅ Redis Cluster → 30秒で回復                           ║
║    ✅ PgBouncer → 15秒で回復                               ║
║                                                            ║
╚════════════════════════════════════════════════════════════╝
```

### 本記事のポイント

1. **v1.0の「定常状態」の限界を認識** — 1,647シナリオ全PASSEDでも、時間変動するトラフィックパターンに対する耐性は未検証だった

2. **InfraSim v2.0で5つの改良を実装**:
   - 8種のトラフィックパターン（DDoS, Flash Crowd, Diurnal, etc.）
   - 時間ステップ型シミュレーション（5秒 x 60ステップ）
   - オートスケーリング（HPA/KEDAの遅延付きスケーリング）
   - フェイルオーバー（検出→プロモーション→回復の3フェーズ）
   - レイテンシカスケード（タイムアウト伝播 + リトライストーム）

3. **1,695シナリオの動的シミュレーションでCRITICAL 2件** — 理論的最悪ケースのみ

4. **v1.0では検出できなかった問題を発見**:
   - Flash crowd 15x + cache stampede → キャッシュウォーミング戦略が必要
   - Aurora 20x latency cascade → PgBouncer-Aurora間のサーキットブレーカー強化が必要

5. **オートスケーリング・フェイルオーバーが正しく機能することをシミュレーションレベルで検証** — DDoS 10xでは6→16 podsへのスケールアウトが間に合い、Aurora Primary障害では60秒で回復

---

**リポジトリ**:
- InfraSim: [github.com/ymaeda-it/infrasim](https://github.com/ymaeda-it/infrasim)
- XClone v2: [github.com/ymaeda-it/xclone-v2](https://github.com/ymaeda-it/xclone-v2)
