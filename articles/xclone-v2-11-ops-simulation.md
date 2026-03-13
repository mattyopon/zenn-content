---
title: "Xクローン v2.11 — InfraSim v3.0: 本番運用シミュレーション（SLOトラッキング・Error Budget・段階的劣化モデル）"
emoji: "📊"
type: "tech"
topics: ["infrasim", "sre", "slo", "chaosengineering", "kubernetes"]
published: false
---

## はじめに — v2.10で障害耐性は完成した、しかし…

[前回のv2.10記事](https://qiita.com/ymaeda_it/items/)では、**二重遮断Circuit Breaking**（sidecar→pgbouncer + pgbouncer→aurora）を完備し、**3,351シナリオ完全PASSED**を達成しました。静的シミュレーション1,647 + 動的シミュレーション1,695 + カスタム9 = 合計3,351。CRITICAL/WARNINGはゼロ。

```
v2.10 の到達点:

  静的シミュレーション:    1,647 PASSED (100%)
  動的シミュレーション:    1,695 PASSED (100%)
  カスタム動的:                9 PASSED (100%)
  ────────────────────────────────────────────
  合計:                    3,351 PASSED (100%)
  CRITICAL: 0  |  WARNING: 0
```

これで障害耐性設計は完了しました。しかし、**本番運用では「設計上正しい」だけでは不十分**です。

```
本番運用で起きること:

  1. デプロイ      — 火・木 14:00 にローリングアップデート（30秒のダウンタイム）
  2. メンテナンス  — 日曜 2:00 にパッチ適用（60分のメンテナンスウィンドウ）
  3. ランダム障害  — ハードウェア故障、ネットワーク瞬断（MTBF: 720h = 月1回）
  4. 段階的劣化    — メモリリーク → OOM → 再起動
                     ディスク充填 → 書き込み不可
                     コネクションリーク → プール枯渇
  5. トラフィック  — 24時間の日内変動 + 週末減少 + 月次成長

  これらが「7日間」「30日間」の長期スパンで複合的に発生する
  → v2.10の300秒シミュレーションでは検出不可能
```

v2.10までのシミュレーションは最長300秒（5分）でした。これでは「デプロイが月に8回ある」「メモリリークが72時間かけてOOMに到達する」「月次成長で2週間後にキャパシティ上限に達する」といった**長期運用の問題**を検出できません。

v2.11では、InfraSim v3.0の**運用シミュレーションエンジン（`OpsSimulationEngine`）**を導入し、日〜週〜月単位の本番運用を事前にシミュレートします。

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
| **12** | **v2.11 -- 運用シミュレーション（本記事）** | **InfraSim v3.0 / SLOトラッキング / Error Budget / 段階的劣化** |

### InfraSimバージョンの進化

```
InfraSim のバージョン進化:

v1.0 (v2.5~v2.7): 静的シミュレーション
  ├ SPOF検出
  ├ カスケード障害分析
  └ 1,647シナリオ（単一時点の障害注入）

v2.0 (v2.8): 動的シミュレーション
  ├ トラフィックパターン（Spike / Wave / DDoS / Flash Crowd）
  ├ オートスケーリング
  ├ フェイルオーバー
  └ 1,695シナリオ（300秒 × 5秒ステップ）

v2.1 (v2.9~v2.10): レジリエンス機構
  ├ Circuit Breaker
  ├ Adaptive Retry
  ├ Cache Warming / Singleflight
  └ 3,351シナリオ全PASSED

v3.0 (v2.11, 本記事): 運用シミュレーション  ← NEW
  ├ Long-Running Simulation（7〜30日）
  ├ Operational Event Injection（デプロイ/メンテナンス/障害/劣化）
  ├ SLO/Error Budget Tracker
  └ Diurnal-Weekly + Growth Trend トラフィック
```

---

## 2. InfraSim v3.0 — 3つの新機能

### 2.1 Long-Running Simulation（日→週→月単位）

v2.0までのシミュレーションは**300秒 × 5秒ステップ = 60ステップ**でした。5分間で何が起きるかを評価するには十分ですが、「7日間の運用」を表現するには力不足です。

v3.0では**時間軸を大幅に拡大**し、日〜月単位のシミュレーションに対応しました。

```
シミュレーション時間軸の比較:

v2.0 (動的シミュレーション):
  Duration:   300秒 (5分)
  Step:       5秒
  Steps:      60
  時間解像度: 秒単位
  検出可能:   瞬間的な障害応答、スパイク耐性

v3.0 (運用シミュレーション):
  Duration:   7日 (604,800秒) 〜 30日 (2,592,000秒)
  Step:       5分 (300秒) 〜 1時間 (3,600秒)
  Steps:      2,016 (7日/5分) 〜 8,640 (30日/5分)
  時間解像度: 分〜時間単位
  検出可能:   デプロイ累積影響、メモリリーク蓄積、
              Error Budget消費推移、容量計画の妥当性

ステップ数の比較:
  v2.0:       60 steps              |■
  v3.0 7d:  2,016 steps             |■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■ (33x)
  v3.0 30d: 8,640 steps (hourly)    |■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■ (144x)
```

時間ステップの粒度は `TimeUnit` 列挙型で選択します。

```python
class TimeUnit(str, Enum):
    """Granularity for the operational simulation time steps."""

    MINUTE = "1min"          # 60秒  — 短期シミュレーション向け
    FIVE_MINUTES = "5min"    # 300秒 — 7日シミュレーションのデフォルト
    HOUR = "1hour"           # 3600秒 — 30日シミュレーション向け
```

30日シミュレーションを5分ステップで実行すると8,640ステップになりますが、各ステップの計算は軽量（コンポーネント状態の更新とSLI計測のみ）なので、実行時間は数秒です。

### 2.2 Diurnal-Weekly Traffic + Growth Trend

本番環境のトラフィックは一定ではありません。朝に増え、昼にピーク、深夜に最小。平日と週末で異なり、月次で成長します。v3.0ではこれを**2つのトラフィックパターンの複合**で表現します。

```
Diurnal-Weekly トラフィックパターン（7日間）:

Traffic
Multiplier
  3.0x  │         ▲           ▲           ▲           ▲           ▲
        │        ╱ ╲         ╱ ╲         ╱ ╲         ╱ ╲         ╱ ╲
  2.5x  │       ╱   ╲       ╱   ╲       ╱   ╲       ╱   ╲       ╱   ╲
        │      ╱     ╲     ╱     ╲     ╱     ╲     ╱     ╲     ╱     ╲
  2.0x  │     ╱       ╲   ╱       ╲   ╱       ╲   ╱       ╲   ╱       ╲
        │    ╱         ╲ ╱         ╲ ╱         ╲ ╱         ╲ ╱         ╲      ▲       ▲
  1.5x  │   ╱                                                              ╱ ╲     ╱ ╲
        │                                                                 ╱   ╲   ╱   ╲
  1.0x  │──╱───────────────────────────────────────────────────────────╱─────╲─╱─────╲──
        │                                                                 Weekend (0.6x)
  0.5x  │
        └──Mon────Tue────Wed────Thu────Fri────Sat────Sun──
            ├───── Weekday Peak: 3.0x ──────┤  ├── Weekend: 1.8x ──┤

  24時間サイクル:
    03:00  最小トラフィック（深夜帯）
    11:00  トラフィック上昇開始
    13:00  ピーク（昼休み）
    17:00  トラフィック減少
    23:00  深夜帯に向けて低下

  週末係数（weekend_factor）:
    平日: peak_multiplier そのまま
    週末: peak_multiplier × weekend_factor (default: 0.6)
```

**Growth Trend** は月次成長率の指数関数モデルです。

```
Growth Trend: (1 + monthly_rate) ^ (elapsed_days / 30)

月次成長率10%の例:
  Day  0:  1.000x  (ベースライン)
  Day  7:  1.023x  (+2.3%)
  Day 14:  1.047x  (+4.7%)
  Day 21:  1.071x  (+7.1%)
  Day 30:  1.100x  (+10.0%)

2つのパターンの複合:
  composite_multiplier = diurnal_weekly(t) × growth_trend(t)

  例: Day 14 の 13:00 (ピーク)
    diurnal_weekly: 3.0x
    growth_trend:   1.047x
    composite:      3.0 × 1.047 = 3.14x
```

複合トラフィックの実装は**乗算方式**です。

```python
@staticmethod
def _composite_traffic(t: int, scenario: OpsScenario) -> float:
    """Compute the composite traffic multiplier at time *t*.

    When multiple traffic patterns are configured, their multipliers
    are combined multiplicatively.  For example, a diurnal pattern
    producing 2.0x and a growth trend producing 1.05x yields 2.1x.
    """
    if not scenario.traffic_patterns:
        return 1.0

    composite = 1.0
    for pattern in scenario.traffic_patterns:
        mult = pattern.multiplier_at(t)
        composite *= mult

    return max(1.0, composite)
```

### 2.3 Operational Event Injection

本番環境では、インフラに対する「計画的な変更」と「予期しない障害」が定常的に発生します。v3.0ではこれらを**7種類のOperational Event**としてモデル化します。

```python
class OpsEventType(str, Enum):
    """Types of operational events that can occur during simulation."""

    DEPLOY = "deploy"                          # スケジュールデプロイ
    MAINTENANCE = "maintenance"                # メンテナンスウィンドウ
    CERT_RENEWAL = "cert_renewal"              # 証明書更新
    RANDOM_FAILURE = "random_failure"          # ランダム障害（MTBF準拠）
    MEMORY_LEAK_OOM = "memory_leak_oom"        # メモリリーク → OOM
    DISK_FULL = "disk_full"                    # ディスク充填
    CONN_POOL_EXHAUSTION = "conn_pool_exhaustion"  # コネクションプール枯渇
```

#### スケジュールデプロイ

```
スケジュールデプロイの生成ロジック:

  設定:
    deploy_days: [tue, thu]  (day_of_week: 1, 3)
    deploy_hour: 14          (14:00)
    downtime_seconds: 30     (30秒のダウンタイム)

  7日間シミュレーション (Day 0 = Monday):
    Day 0 (Mon):  — (デプロイなし)
    Day 1 (Tue):  14:00 → deploy event (30s downtime)  ← hono-api × 12
    Day 2 (Wed):  — (デプロイなし)
    Day 3 (Thu):  14:00 → deploy event (30s downtime)  ← hono-api × 12
    Day 4 (Fri):  — (デプロイなし)
    Day 5 (Sat):  — (デプロイなし)
    Day 6 (Sun):  — (デプロイなし)

  1週間あたりのデプロイイベント数:
    deploy_targets (app_server/web_server) × 2回/週
    例: hono-api 12台 → 12 × 2 = 24 events/週
    7日間: ~24 deploy events (対象コンポーネント数による)
```

#### ランダム障害（MTBF準拠の指数分布）

ランダム障害は**指数分布**で生成されます。MTBF（Mean Time Between Failures）から次の障害発生までの待ち時間を決定し、MTTR（Mean Time To Repair）の間ダウンします。

```python
# Random failures based on MTBF (exponential distribution)
if scenario.enable_random_failures:
    for comp_id, comp in self.graph.components.items():
        mtbf_hours = comp.operational_profile.mtbf_hours
        if mtbf_hours <= 0:
            mtbf_hours = 720.0  # default: 30 days

        mtbf_seconds = mtbf_hours * 3600.0
        mttr_seconds = comp.operational_profile.mttr_minutes * 60.0

        # Exponential distribution: next failure
        t_cursor = rng.expovariate(1.0 / mtbf_seconds)
        while t_cursor < total_seconds:
            events.append(OpsEvent(
                time_seconds=int(t_cursor),
                event_type=OpsEventType.RANDOM_FAILURE,
                target_component_id=comp_id,
                duration_seconds=int(mttr_seconds),
                description=f"Random failure of {comp_id} ..."
            ))
            # Next: MTTR + exponential wait
            t_cursor += mttr_seconds + rng.expovariate(1.0 / mtbf_seconds)
```

```
指数分布によるランダム障害の発生パターン（MTBF=720h の例）:

Time (days)
  0   1   2   3   4   5   6   7
  │   │   │   │   │   │   │   │
  ├───┤   │   │   │   │   │   │
  │   │   │   │   ├─┤ │   │   │   ← comp-A: failure at Day 4
  │   │   │   │   │ │ │   │   │     (MTTR: 30min)
  │   ├─┤ │   │   │   │   │   │   ← comp-B: failure at Day 1
  │   │ │ │   │   │   │   │   │
  │   │   │   │   │   │   │ ├─┤   ← comp-C: failure at Day 6.5
  │   │   │   │   │   │   │ │ │
  └───┴───┴───┴───┴───┴───┴───┘

  指数分布の性質:
    - 平均: MTBF = 720h (30日)
    - 分散が大きい → 早期に連続発生することもあれば、長期間発生しないことも
    - Memoryless: 「前回からの経過時間」に依存しない
    - 7日間で0〜3回の障害が発生するのが一般的
```

#### メンテナンスウィンドウ

```
メンテナンスウィンドウ:

  設定:
    maintenance_day_of_week: 6  (Sunday, 0=Mon)
    maintenance_hour: 2         (02:00)

  効果:
    全コンポーネントに対して maintenance_downtime_minutes 分のダウンタイム
    各コンポーネントの OperationalProfile.maintenance_downtime_minutes を使用

  時系列:
    Sun 02:00 → 全コンポーネントが順次ダウン
    Sun 02:30 → hono-api復旧（downtime: 30min）
    Sun 03:00 → aurora復旧（downtime: 60min）
    ...
```

### 2.4 段階的劣化モデル（Gradual Degradation）

現実のインフラでは、障害は突然発生するだけではありません。**メモリリーク、ディスク充填、コネクションリーク**のように、**徐々に劣化してから閾値を超えてダウンする**パターンがあります。

```python
class DegradationConfig(BaseModel):
    """Gradual degradation model for a component."""

    memory_leak_mb_per_hour: float = 0.0        # 1時間あたりのメモリリーク量
    disk_fill_gb_per_hour: float = 0.0          # 1時間あたりのディスク充填量
    connection_leak_per_hour: float = 0.0       # 1時間あたりのコネクションリーク数
```

```
段階的劣化のシミュレーションフロー:

  [メモリリークの例]

  Component: hono-api-1
    max_memory_mb: 2048
    memory_leak_mb_per_hour: 10

  Time    Leaked    Utilization    Health      Event
  ─────  ────────  ───────────    ──────────  ──────
  t=0h       0 MB      12.0%      HEALTHY     —
  t=24h    240 MB      17.9%      HEALTHY     —
  t=48h    480 MB      23.7%      HEALTHY     —
  t=72h    720 MB      29.6%      HEALTHY     —
  t=96h    960 MB      35.5%      HEALTHY     —
  t=120h  1200 MB      41.3%      HEALTHY     —
  t=144h  1440 MB      47.2%      HEALTHY     —
  t=168h  1680 MB      53.0%      HEALTHY     —
  t=192h  1920 MB      56.0%      HEALTHY     —
  t=204h  2040 MB      56.9%      HEALTHY     —
  t=205h  2050 MB      -.-%       DOWN        OOM! → restart
  t=205h     0 MB      12.0%      HEALTHY     Leaked memory reset

  メモリリークの影響:
    leaked_memory_mb / max_memory_mb → mem_pressure (0~100%)
    effective_util += mem_pressure × 0.5

  閾値を超えた時:
    OpsEventType.MEMORY_LEAK_OOM イベント生成
    → コンポーネントDOWN（MTTR分のダウンタイム）
    → leaked_memory_mb リセット（再起動）
```

```
段階的劣化 — 3種類の劣化パターン:

Memory Leak:
  蓄積: leaked_mb += leak_rate × step_hours
  圧力: utilization += (leaked_mb / max_mb) × 50%
  閾値: leaked_mb >= max_mb → OOM → restart

Disk Fill:
  蓄積: filled_gb += fill_rate × step_hours
  圧力: utilization += (filled_gb / max_gb) × 30%
  閾値: filled_gb >= max_gb → DISK_FULL → cleanup

Connection Leak:
  蓄積: leaked_conns += leak_rate × step_hours
  圧力: utilization += (leaked_conns / pool_size) × 40%
  閾値: leaked_conns >= pool_size → CONN_POOL_EXHAUSTION → restart

重み付けの設計意図:
  Memory  (× 0.5): メモリ不足はCPU使用率に直結
  Disk    (× 0.3): ディスク圧迫は間接的な影響
  Conn    (× 0.4): コネクション枯渇はリクエスト処理に直結
```

### 2.5 SLO/Error Budget Tracker

v3.0の最も重要な新機能が**SLOトラッカー**です。シミュレーション中にSLI（Service Level Indicator）をリアルタイム計測し、Error Budgetの消費状況を追跡します。

```
SLO/Error Budget のコンセプト:

┌─────────────────────────────────────────────────────────────┐
│                                                             │
│  SLI (Service Level Indicator):                             │
│    計測する指標                                              │
│    - availability: UP状態コンポーネントの割合                │
│    - latency_p99: 推定p99レイテンシ                         │
│    - error_rate: DOWN/OVERLOADEDコンポーネントの割合         │
│                                                             │
│  SLO (Service Level Objective):                             │
│    達成すべき目標値                                          │
│    - availability >= 99.9%                                  │
│    - latency_p99 < 500ms                                    │
│    - error_rate < 0.1%                                      │
│                                                             │
│  Error Budget:                                              │
│    「SLOを達成しつつ許容できる障害の量」                     │
│    - budget = window × (1 - SLO_target)                     │
│    - 例: 99.9% over 30日 → 30 × 24 × 60 × 0.001           │
│                            = 43.2分のダウンタイムが許容範囲  │
│                                                             │
│  Burn Rate:                                                 │
│    Error Budgetの消費速度                                    │
│    burn_rate = (直近window内の違反率) / (許容違反率)          │
│    - 1.0: ちょうどSLO上で動作中（持続可能）                  │
│    - 2.0: SLOの2倍速でBudget消費中（要注意）                 │
│    - 10.0: 重大インシデント進行中                            │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. 新しいPydanticモデル — 運用シミュレーションのデータ構造

### 3.1 コンポーネント側のモデル

```python
class SLOTarget(BaseModel):
    """Service Level Objective definition."""

    name: str = ""
    metric: str = "availability"  # availability | latency_p99 | error_rate
    target: float = 99.9          # 目標値
    unit: str = "percent"         # percent | ms | ratio
    window_days: int = 30         # 評価ウィンドウ（日数）


class DegradationConfig(BaseModel):
    """Gradual degradation model for a component."""

    memory_leak_mb_per_hour: float = 0.0
    disk_fill_gb_per_hour: float = 0.0
    connection_leak_per_hour: float = 0.0


class OperationalProfile(BaseModel):
    """Operational characteristics of a component."""

    mtbf_hours: float = 0.0                     # Mean Time Between Failures
    mttr_minutes: float = 30.0                  # Mean Time To Repair
    deploy_downtime_seconds: float = 30.0       # デプロイ時のダウンタイム
    maintenance_downtime_minutes: float = 60.0  # メンテナンス時のダウンタイム
    degradation: DegradationConfig = Field(default_factory=DegradationConfig)
```

### 3.2 シミュレーションエンジン側のモデル

```python
@dataclass
class OpsEvent:
    """A single operational event occurring at a specific time."""

    time_seconds: int                    # 発生時刻（シミュレーション開始からの秒数）
    event_type: OpsEventType             # イベント種別
    target_component_id: str             # 対象コンポーネント
    duration_seconds: int = 0            # 継続時間（ダウンタイム）
    description: str = ""                # 人間可読な説明


class OpsScenario(BaseModel):
    """Configuration for an operational simulation run."""

    id: str
    name: str
    description: str = ""
    duration_days: int = 7
    time_unit: TimeUnit = TimeUnit.FIVE_MINUTES
    traffic_patterns: list[TrafficPattern] = Field(default_factory=list)
    scheduled_deploys: list[dict[str, Any]] = Field(default_factory=list)
    enable_random_failures: bool = False
    enable_degradation: bool = False
    enable_maintenance: bool = False
    maintenance_day_of_week: int = 6     # 0=Mon, 6=Sun
    maintenance_hour: int = 2            # 02:00
    random_seed: int = 2024              # 再現可能な乱数シード
```

### 3.3 SLI計測とError Budget

```python
@dataclass
class SLIDataPoint:
    """A single SLI measurement at a point in time."""

    time_seconds: int
    total_components: int = 0
    healthy_count: int = 0
    degraded_count: int = 0
    overloaded_count: int = 0
    down_count: int = 0
    availability_percent: float = 100.0
    estimated_latency_p99_ms: float = 0.0
    error_rate: float = 0.0
    max_utilization: float = 0.0


@dataclass
class ErrorBudgetStatus:
    """Error budget status for a single SLO target."""

    slo: SLOTarget
    component_id: str
    budget_total_minutes: float = 0.0          # 全Error Budget（分）
    budget_consumed_minutes: float = 0.0       # 消費済みBudget（分）
    budget_remaining_minutes: float = 0.0      # 残りBudget（分）
    budget_remaining_percent: float = 100.0    # 残り割合（%）
    burn_rate_1h: float = 0.0                  # 直近1時間のBurn Rate
    burn_rate_6h: float = 0.0                  # 直近6時間のBurn Rate
    is_budget_exhausted: bool = False          # Budget枯渇フラグ


@dataclass
class OpsSimulationResult:
    """Result of running an operational simulation."""

    scenario: OpsScenario
    events: list[OpsEvent] = field(default_factory=list)
    sli_timeline: list[SLIDataPoint] = field(default_factory=list)
    error_budget_statuses: list[ErrorBudgetStatus] = field(default_factory=list)
    total_downtime_seconds: int = 0
    total_deploys: int = 0
    total_failures: int = 0
    total_degradation_events: int = 0
    peak_utilization: float = 0.0
    min_availability: float = 100.0
    summary: str = ""
```

### 3.4 モデル間の関係図

```
データモデルの関係図:

Component
  ├── slo_targets: list[SLOTarget]           ← SLO定義
  ├── operational_profile: OperationalProfile ← 運用パラメータ
  │     ├── mtbf_hours                        ← ランダム障害の頻度
  │     ├── mttr_minutes                      ← 復旧時間
  │     ├── deploy_downtime_seconds           ← デプロイダウンタイム
  │     ├── maintenance_downtime_minutes      ← メンテナンスダウンタイム
  │     └── degradation: DegradationConfig    ← 劣化パラメータ
  │           ├── memory_leak_mb_per_hour
  │           ├── disk_fill_gb_per_hour
  │           └── connection_leak_per_hour
  └── capacity: CapacityConfig
        ├── max_memory_mb                     ← OOM閾値
        ├── max_disk_gb                       ← Disk Full閾値
        └── connection_pool_size              ← コネクション枯渇閾値

OpsScenario
  ├── duration_days, time_unit                ← シミュレーション時間
  ├── traffic_patterns: list[TrafficPattern]  ← トラフィックモデル
  ├── scheduled_deploys: list[dict]           ← デプロイスケジュール
  ├── enable_random_failures                  ← ランダム障害ON/OFF
  ├── enable_degradation                      ← 段階的劣化ON/OFF
  └── enable_maintenance                      ← メンテナンスON/OFF

OpsSimulationResult
  ├── events: list[OpsEvent]                  ← 全イベント（時系列）
  ├── sli_timeline: list[SLIDataPoint]        ← SLI計測値（時系列）
  ├── error_budget_statuses: list[ErrorBudgetStatus]  ← Budget状況
  ├── total_downtime_seconds
  ├── total_deploys / total_failures
  ├── peak_utilization / min_availability
  └── summary                                 ← 人間可読なサマリー
```

---

## 4. 実装のポイント — OpsSimulationEngine

### 4.1 アーキテクチャ: Composition over Inheritance

`OpsSimulationEngine` は既存の `DynamicSimulationEngine` を継承するのではなく、**独立したエンジン**として実装しています。

```
設計判断: Composition over Inheritance

  ✗ 継承パターン:
    class OpsSimulationEngine(DynamicSimulationEngine):
      # DynamicSimulationEngineの300秒制約に縛られる
      # step_seconds=5 前提のコードが多い
      # オーバーライドだらけで保守困難

  ✓ コンポジションパターン（採用）:
    class OpsSimulationEngine:
      def __init__(self, graph: InfraGraph):
          self.graph = graph  # InfraGraphだけ共有

      # 独自の時間軸、独自のイベントスケジューリング、
      # 独自のSLOトラッキングを実装
      # DynamicSimulationEngineとは完全に独立

  理由:
    1. 時間軸が根本的に異なる（5秒 vs 5分）
    2. 目的が異なる（障害応答 vs 長期運用品質）
    3. トラフィックモデルが異なる（Spike/Wave vs Diurnal-Weekly）
    4. 出力が異なる（severity vs SLO/Error Budget）
```

### 4.2 Seeded RNG for Reproducible Results

運用シミュレーションの結果は**再現可能**でなければなりません。同じシナリオを何度実行しても同じ結果を得るために、**シード付き乱数生成器**を使います。

```python
# Global seeded RNG (module level)
_ops_rng = random.Random(2024)

# Per-scenario seeded RNG
def run_ops_scenario(self, scenario: OpsScenario) -> OpsSimulationResult:
    rng = random.Random(scenario.random_seed)
    # このrngを全ての確率的処理に使用
    # → 同じ random_seed → 同じイベントスケジュール → 同じ結果
```

```
再現性の保証:

  Scenario A (seed=2024, 7日):
    Run 1: 8 random failures, 66 deploys → availability 99.87%
    Run 2: 8 random failures, 66 deploys → availability 99.87%  ← 完全一致
    Run 3: 8 random failures, 66 deploys → availability 99.87%  ← 完全一致

  Scenario B (seed=42, 30日):
    Run 1: 12 random failures → availability 99.45%
    Run 2: 12 random failures → availability 99.45%  ← 完全一致

  seedを変えると:
  Scenario A (seed=12345, 7日):
    Run 1: 5 random failures, 66 deploys → availability 99.92%
    → 異なるイベントスケジュール、異なる結果
```

### 4.3 Hockey-Stick Latency Model

p99レイテンシの推定には**ホッケースティックカーブ**を使用します。利用率が低い間はレイテンシが線形に増加しますが、高利用率になるとキュー待ちにより指数的に急上昇します。

```python
@staticmethod
def _estimate_latency(max_utilization: float) -> float:
    """Estimate p99 latency using a hockey-stick curve."""
    base_ms = 5.0
    if max_utilization <= 0:
        return base_ms

    u = max_utilization / 100.0  # Normalise to 0-1

    if u < 0.5:
        # Low utilization: linear
        return base_ms * (1.0 + u)
    elif u < 0.8:
        # Medium: gentle curve
        return base_ms * (1.0 + u + (u - 0.5) ** 2 * 10)
    else:
        # High utilization: hockey stick
        overshoot = max(0.0, u - 0.8)
        return base_ms * (1.0 + u + overshoot ** 2 * 500)
```

```
Hockey-Stick Latency Curve:

p99
Latency
(ms)
 200 │                                                          ╱
     │                                                        ╱
 150 │                                                      ╱
     │                                                    ╱
 100 │                                                  ╱
     │                                                ╱
  50 │                                              ╱
     │                                          ╱╱╱
  30 │                                       ╱╱
  20 │                                   ╱╱╱
  15 │                             ╱╱╱╱╱
  10 │                     ╱╱╱╱╱╱╱
   7 │             ╱╱╱╱╱╱╱
   5 │─────╱╱╱╱╱╱╱
     └──────────────────────────────────────────────────────────
     0%   10%  20%  30%  40%  50%  60%  70%  80%  90% 100% 120%
                         Utilization

     ├── Linear Zone ──┤├─ Curve ──┤├──── Hockey Stick ────┤

  Zone          Range       Latency at boundary
  ──────────    ─────────   ───────────────────
  Linear        0-50%       5.0ms → 7.5ms
  Gentle Curve  50-80%      7.5ms → 14.0ms
  Hockey Stick  80-100%+    14.0ms → 50ms → 200ms+

  実世界との対応:
    50%以下: CPU/メモリに余裕があり、キュー待ちなし
    50-80%:  スレッドプールの競合開始、軽微なキュー待ち
    80%以上: キューが指数的に増加（M/M/1キューイング理論に準拠）
```

### 4.4 メインシミュレーションループ

`run_ops_scenario` のメインループは6つのフェーズで構成されています。

```
メインシミュレーションループ（各ステップで実行）:

  for step_idx in range(num_steps + 1):
      t = step_idx * step_seconds

      ┌─────────────────────────────────────────────────────────┐
      │ Phase 1: Composite Traffic                              │
      │   traffic_mult = diurnal_weekly(t) × growth_trend(t)    │
      └────────────────────────┬────────────────────────────────┘
                               ▼
      ┌─────────────────────────────────────────────────────────┐
      │ Phase 2: Apply Degradation                              │
      │   leaked_memory += rate × step_hours                    │
      │   if leaked_memory >= max → OOM event                   │
      └────────────────────────┬────────────────────────────────┘
                               ▼
      ┌─────────────────────────────────────────────────────────┐
      │ Phase 3: Get Active Faults                              │
      │   events where start <= t < start + duration            │
      │   → deploy/maintenance/failure/degradation events       │
      └────────────────────────┬────────────────────────────────┘
                               ▼
      ┌─────────────────────────────────────────────────────────┐
      │ Phase 4: Update Component Health                        │
      │   if faulted → DOWN                                     │
      │   else → utilization × traffic / replicas + degradation │
      │   → HEALTHY / DEGRADED / OVERLOADED / DOWN              │
      └────────────────────────┬────────────────────────────────┘
                               ▼
      ┌─────────────────────────────────────────────────────────┐
      │ Phase 5: Autoscaling                                    │
      │   if util > scale_up_threshold → add replicas           │
      │   if util < scale_down_threshold → remove replicas      │
      │   (cooldown enforcement)                                │
      └────────────────────────┬────────────────────────────────┘
                               ▼
      ┌─────────────────────────────────────────────────────────┐
      │ Phase 6: Record SLI                                     │
      │   availability, latency_p99, error_rate, max_util       │
      │   + per-component SLO violation tracking                │
      └─────────────────────────────────────────────────────────┘
```

### 4.5 Health判定ロジック

コンポーネントのHealthは利用率から決定されます。

```python
# Determine health from utilization
if effective_util > 100.0:
    state.current_health = HealthStatus.DOWN
elif effective_util > 90.0:
    state.current_health = HealthStatus.OVERLOADED
elif effective_util > 70.0:
    state.current_health = HealthStatus.DEGRADED
else:
    state.current_health = HealthStatus.HEALTHY
```

```
Health判定の閾値:

Utilization   Health        意味
──────────    ──────────    ─────────────────────────────
  0-70%       HEALTHY       正常動作。余裕あり。
 70-90%       DEGRADED      性能劣化。レイテンシ増加。
 90-100%      OVERLOADED    過負荷。エラー発生。
100%+         DOWN          キャパシティ超過。サービス不能。

effective_util の構成:
  effective_util = base_util × traffic_mult / replicas
                   + memory_pressure × 0.5
                   + disk_pressure × 0.3
                   + connection_pressure × 0.4

  上限: min(effective_util, 120.0)
```

### 4.6 Error Budget計算

Error Budgetは「SLOを達成しつつ許容できる障害の量」を定量化します。

```python
def _budget_total(self, slo: SLOTarget) -> float:
    """Calculate total error budget in minutes."""
    window_minutes = slo.window_days * 24.0 * 60.0

    if slo.metric == "availability":
        # 例: 99.9% over 30日 → 43.2分
        return window_minutes * (1.0 - slo.target / 100.0)
    else:
        # latency/error_rate: window の 0.1%
        return window_minutes * 0.001
```

```
Error Budget の計算例:

SLO: availability >= 99.9% (30日ウィンドウ)
  budget_total = 30 × 24 × 60 × (1 - 99.9/100)
               = 43,200分 × 0.001
               = 43.2分

  つまり「30日間で43.2分のダウンタイムは許容」

Burn Rate の計算:
  burn_rate = (直近window内の違反率) / (許容違反率)

  例: 直近1時間で5分間DOWN
    violation_ratio = 5/60 = 0.0833
    allowed_ratio = 1 - 99.9/100 = 0.001
    burn_rate = 0.0833 / 0.001 = 83.3x

  → 83.3倍の速度でBudgetを消費中（重大インシデント！）

Burn Rate の解釈:
  burn_rate    意味                    アクション
  ──────────   ──────────────────      ─────────────────
  0.0          違反なし                問題なし
  0.5          Budget消費は半速        余裕あり
  1.0          ちょうどSLO上          持続可能だが余裕なし
  2.0          2倍速で消費中          要注意（14.4日でBudget枯渇）
  10.0         10倍速で消費中         緊急対応必要
  83.3         重大インシデント進行中  全リソース投入
```

---

## 5. デフォルト5シナリオ — 段階的な運用テスト

`OpsSimulationEngine.run_default_ops_scenarios()` は5つのデフォルトシナリオを順番に実行します。段階的に運用条件を厳しくしていき、インフラの耐性を評価します。

```
5つのデフォルトシナリオ:

┌──────────────────────────────────────────────────────────────────┐
│ # │ Scenario ID        │ Days │ Step │ Features                  │
├───┼────────────────────┼──────┼──────┼───────────────────────────┤
│ 1 │ ops-7d-baseline    │   7  │ 5min │ Diurnal-weekly traffic    │
│   │                    │      │      │ (No events)               │
├───┼────────────────────┼──────┼──────┼───────────────────────────┤
│ 2 │ ops-7d-with-deploys│   7  │ 5min │ Diurnal-weekly + Tue/Thu  │
│   │                    │      │      │ deploys at 14:00          │
├───┼────────────────────┼──────┼──────┼───────────────────────────┤
│ 3 │ ops-7d-full        │   7  │ 5min │ Diurnal-weekly (2.5x) +   │
│   │                    │      │      │ deploys + random failures │
│   │                    │      │      │ + degradation + maint     │
├───┼────────────────────┼──────┼──────┼───────────────────────────┤
│ 4 │ ops-14d-growth     │  14  │ 5min │ Diurnal-weekly + 10%      │
│   │                    │      │      │ monthly growth + all ops  │
├───┼────────────────────┼──────┼──────┼───────────────────────────┤
│ 5 │ ops-30d-stress     │  30  │ 1h   │ Diurnal-weekly (3.5x) +   │
│   │                    │      │      │ 15% growth + all ops      │
│   │                    │      │      │ (seed=42)                 │
└───┴────────────────────┴──────┴──────┴───────────────────────────┘
```

### 5.1 Scenario 1: Baseline (7日, イベントなし)

```
ops-7d-baseline:
  目的: 「通常運用でのSLIベースラインを確立する」

  設定:
    duration: 7日
    step: 5分 (2,016 steps)
    traffic: diurnal-weekly (peak 2.0x, weekend 0.6x)
    deploys: なし
    random_failures: なし
    degradation: なし
    maintenance: なし

  期待結果:
    availability: 100%（障害なし）
    downtime: 0分
    events: 0
    → ベースラインSLI値を取得
```

### 5.2 Scenario 2: With Deploys (7日, Tue/Thu デプロイ)

```
ops-7d-with-deploys:
  目的: 「定期デプロイのSLOへの影響を定量化する」

  設定:
    duration: 7日
    traffic: diurnal-weekly (peak 2.0x)
    deploys: Tue/Thu 14:00 (app_server/web_server targets)

  デプロイイベント生成:
    Day 1 (Tue 14:00): hono-api-1~N × deploy (30s each)
    Day 3 (Thu 14:00): hono-api-1~N × deploy (30s each)
    → 合計: deploy_targets × 2

  期待結果:
    availability: 99.9%+ (各デプロイ30秒)
    downtime: deploy_targets × 2 × 30秒
    → デプロイがSLOにどれだけ影響するかを定量化
```

### 5.3 Scenario 3: Full Operations (7日, 全機能有効)

```
ops-7d-full:
  目的: 「本番同等の運用条件でのSLO達成率を評価」

  設定:
    duration: 7日
    traffic: diurnal-weekly (peak 2.5x, weekend 0.6x)  ← ピーク高め
    deploys: Tue/Thu 14:00
    random_failures: ENABLED (MTBF準拠)
    degradation: ENABLED (memory/disk/connection leak)
    maintenance: Sun 02:00

  イベント内訳（想定）:
    deploys: ~66 events (deploy_targets × 2回/週)
    random_failures: ~8 events (MTBF=720h, 7日間で各コンポーネント0~1回)
    degradation: ~5 events (メモリリーク蓄積 → OOM)
    maintenance: ~40 events (全コンポーネント × 1回/週)
    ──────────
    合計: ~119 events

  期待結果:
    availability: 99.0%〜99.9%
    downtime: 数十分〜数百分
    → Error Budget消費の実態を把握
```

### 5.4 Scenario 4: Growth (14日, 月次10%成長)

```
ops-14d-growth:
  目的: 「トラフィック成長に対するキャパシティ計画の妥当性を検証」

  設定:
    duration: 14日
    traffic: diurnal-weekly (peak 2.0x) × growth_trend (10%/月)
    deploys: Tue/Thu 14:00
    全ops機能: ENABLED

  トラフィック推移:
    Day 0:   2.0x × 1.000 = 2.00x peak
    Day 7:   2.0x × 1.023 = 2.05x peak
    Day 14:  2.0x × 1.047 = 2.09x peak

  期待結果:
    → オートスケーリングが成長に追従できるか
    → 2週間後の利用率がどこまで上昇するか
    → 容量計画の見直しが必要なタイミングを予測
```

### 5.5 Scenario 5: 30-Day Stress Test

```
ops-30d-stress:
  目的: 「長期ストレステスト — Error Budget枯渇リスクの評価」

  設定:
    duration: 30日
    step: 1時間 (720 steps)  ← 30日は1時間刻みで高速化
    traffic: diurnal-weekly (peak 3.5x, weekend 0.5x) × growth (15%/月)
    deploys: Tue/Thu 14:00
    全ops機能: ENABLED
    seed: 42  ← 異なるseedで異なる障害パターン

  トラフィック推移:
    Day 0:   3.5x × 1.000 = 3.50x peak
    Day 15:  3.5x × 1.073 = 3.76x peak
    Day 30:  3.5x × 1.150 = 4.03x peak  ← 4倍超!

  期待結果:
    → 30日間でError Budgetが枯渇するか
    → 月末にキャパシティが不足するか
    → SLO 99.9%を維持できる成長率の上限を特定
```

---

## 6. XClone v2 での実行結果

### 6.1 7日間ベースライン (ops-7d-baseline)

```
╔══════════════════════════════════════════════════════════════════╗
║  InfraSim Operational Simulation Report                         ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  Scenario: 7-day baseline (no events)                           ║
║  Duration: 7 days    Steps: 2,016                               ║
║                                                                  ║
║  Avg Availability: 100.0000%                                    ║
║  Min Availability: 100.00%                                      ║
║  Total Downtime: 0.0 min                                        ║
║  Peak Utilization: 18.2%                                        ║
║  Deploys: 0   Failures: 0   Degradation Events: 0              ║
║  Total Events: 0                                                ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
```

ベースラインは期待通り100%可用性。ピーク利用率18.2%は、Diurnal-Weeklyの2.0xピークでもキャパシティに十分な余裕があることを示しています。

### 6.2 7日間デプロイあり (ops-7d-with-deploys)

```
╔══════════════════════════════════════════════════════════════════╗
║  InfraSim Operational Simulation Report                         ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  Scenario: 7-day with Tue/Thu deploys                           ║
║  Duration: 7 days    Steps: 2,016                               ║
║                                                                  ║
║  Avg Availability: 99.9305%                                     ║
║  Min Availability: 97.78%                                       ║
║  Total Downtime: 10.0 min                                       ║
║  Peak Utilization: 18.2%                                        ║
║  Deploys: 66   Failures: 0   Degradation Events: 0             ║
║  Total Events: 66                                               ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
```

66回のデプロイで合計10分のダウンタイム。各デプロイは30秒のダウンタイムですが、コンポーネントが冗長化されているため、全体の可用性への影響は限定的です。**99.93%は SLO 99.9%を満たしています。**

### 6.3 7日間フルオペレーション (ops-7d-full)

```
╔══════════════════════════════════════════════════════════════════╗
║  InfraSim Operational Simulation Report                         ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  Scenario: 7-day full operations                                ║
║  Duration: 7 days    Steps: 2,016                               ║
║                                                                  ║
║  Avg Availability: 99.2800%                                     ║
║  Min Availability: 89.47%                                       ║
║  Total Downtime: 305.0 min                                      ║
║  Peak Utilization: 24.4%                                        ║
║  Deploys: 66   Failures: 8   Degradation Events: 5             ║
║  Total Events: 119                                              ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
```

119イベントが発生し、ダウンタイムは305分（約5時間）。可用性99.28%は**SLO 99.9%を下回っています**。これは重要な発見です。

```
SLO違反の分析 (ops-7d-full):

  SLO Target:      99.9% availability (30日ウィンドウ)
  Error Budget:    43.2分 (30日間の許容ダウンタイム)

  7日間で消費:     305分
  → 30日換算:      305 / 7 × 30 = 1,307分

  Error Budget消費率: 1,307 / 43.2 = 3,025%

  ⚠️ 7日間のフル運用でError Budgetを30倍超過
  → SLO 99.9%は現在の運用条件では達成不可能

  Downtime内訳:
    デプロイ起因:    ~10分  (66 deploys × 30s, 一部は冗長で吸収)
    ランダム障害:    ~240分 (8 failures × 30min MTTR)
    メンテナンス:    ~50分  (全コンポーネント日曜メンテ)
    劣化(OOM等):     ~5分   (5 degradation events)
    ────────────────────────
    合計:            ~305分

  最大の要因: ランダム障害のMTTR (30分/回)
  対策案:
    1. MTTR短縮: 30分 → 5分（自動復旧強化）
    2. 冗長化強化: single-replica → multi-replica
    3. SLO再検討: 99.9% → 99.5%
```

### 6.4 結果の比較テーブル

| シナリオ | イベント数 | デプロイ | 障害 | 劣化 | ダウンタイム | 可用性 | SLO 99.9% |
|---------|:---------:|:-------:|:----:|:---:|:-----------:|:------:|:---------:|
| Baseline | 0 | 0 | 0 | 0 | 0分 | 100.00% | PASS |
| With deploys | 66 | 66 | 0 | 0 | 10分 | 99.93% | PASS |
| Full ops | 119 | 66 | 8 | 5 | 305分 | 99.28% | **FAIL** |

```
可用性の推移（3シナリオ比較）:

Availability
 100.0% │■■■■■■■■■■■■■■■■■■■■■■■■■■■ Baseline
        │
  99.9% │──────────────────────────────── SLO Target (99.9%)
        │■■■■■■■■■■■■■■■■■■■■■■■■■■  With deploys (99.93%)
  99.5% │
        │
  99.0% │
        │■■■■■■■■■■■■■■■■■■■■■■■    Full ops (99.28%)  ← SLO FAIL
  98.5% │
        └─────────────────────────────────────────────────
         Baseline    With deploys    Full ops
```

### 6.5 カスタムシナリオの結果

CLIからカスタムシナリオを実行した結果です。

```bash
# 7日間、デプロイ+障害+10%成長
infrasim ops-sim -y infra/infrasim-xclone.yaml \
  --days 7 \
  --deploy-days "tue,thu" \
  --growth 0.1
```

```
╔══════════════════════════════════════════════════════════════════╗
║  InfraSim Operational Simulation Report                         ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  Scenario: Custom 7d (deploys + failures + 10% growth)          ║
║  Duration: 7 days    Steps: 2,016                               ║
║                                                                  ║
║  Avg Availability: 99.8700%                                     ║
║  Min Availability: 94.74%                                       ║
║  Total Downtime: 45.0 min                                       ║
║  Peak Utilization: 24.4%                                        ║
║  Deploys: 66   Failures: 8   Degradation Events: 0             ║
║  Total Events: 74                                               ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
```

カスタムシナリオでは劣化を無効にした（デフォルト `--no-degradation` なし、メンテナンスも無効）ため、イベント数74で可用性99.87%。SLO 99.9%にはわずかに届きませんが、Full opsの99.28%よりは大幅に改善しています。

---

## 7. Error Budget分析 — SLO 99.9%は達成可能か

### 7.1 Error Budget Statusの出力例

```
Error Budget Status (ops-7d-full):

Component            Metric        Budget   Consumed  Remaining  Burn 1h  Burn 6h  Status
──────────────────   ───────────   ──────   ────────  ─────────  ───────  ───────  ──────
hono-api-1           availability   43.20     12.50     30.70     0.00     0.83    OK
hono-api-2           availability   43.20      8.75     34.45     0.00     0.42    OK
pgbouncer-1          availability   43.20     15.00     28.20     0.00     1.25    OK
aurora-primary       availability   43.20      5.00     38.20     0.00     0.00    OK
redis-primary        availability   43.20      3.75     39.45     0.00     0.00    OK
envoy-ingress        availability   43.20      0.00     43.20     0.00     0.00    OK
```

### 7.2 Budget消費の可視化

```
Error Budget消費推移（7日間フルオペレーション）:

Budget
Remaining
(min)
  43.2 │■────────────
       │              ╲
  40.0 │               ╲──── Deploy (Tue 14:00)
       │                 ╲
  35.0 │                  ╲── Random failure (Wed 03:00)
       │                    ╲
  30.0 │                     ╲
       │                      ╲── Deploy (Thu 14:00)
  25.0 │                        ╲
       │                         ╲── Failure + OOM (Fri)
  20.0 │                           ╲
       │                            ╲
  15.0 │                             ╲── Maintenance (Sun 02:00)
       │                               ╲
  10.0 │                                ╲
       │                                 ╲
   5.0 │                                  ╲
       │                                   ╲
   0.0 │─────────────────────────────────────╳── EXHAUSTED!
       └──────────────────────────────────────
       Mon   Tue   Wed   Thu   Fri   Sat   Sun

  ⚠️ 日曜メンテナンス前にError Budgetが枯渇
  → 現在の構成ではSLO 99.9% (30日) は達成不可能
```

### 7.3 Burn Rateアラートの設計

Google SREのMulti-Window Multi-Burn-Rate Alertsに基づいて、Burn Rateからアラート閾値を設計します。

```
Burn Rate Alert設計:

  Error Budget: 43.2分 (30日間)

  ┌─────────────────────────────────────────────────────────────┐
  │ Severity │ Burn Rate │ Budget枯渇  │ Window    │ Action    │
  ├──────────┼───────────┼─────────────┼───────────┼───────────┤
  │ P1 (緊急)│ > 14.4x   │ 2日で枯渇   │ 1h / 6h   │ PAGE      │
  │ P2 (警告)│ > 6.0x    │ 5日で枯渇   │ 1h / 6h   │ TICKET    │
  │ P3 (注意)│ > 1.0x    │ 30日で枯渇  │ 6h / 3d   │ MONITOR   │
  │ 正常     │ < 1.0x    │ 枯渇しない  │ —         │ —         │
  └──────────┴───────────┴─────────────┴───────────┴───────────┘

  Multi-Window の理由:
    短いwindow (1h): 急激なインシデントを素早く検出
    長いwindow (6h): 緩やかな劣化を見逃さない
    両方でアラート条件を満たした時のみ発報 → 誤報削減

  v2.11のシミュレーション結果:
    ops-7d-full での最大 burn_rate_6h: 1.25x (pgbouncer-1)
    → P3 (注意) レベル
    → ただし7日間の累積で Budget枯渇 → SLO達成不可能
```

---

## 8. CLI使い方 — `infrasim ops-sim`

### 8.1 コマンドオプション

```bash
infrasim ops-sim --help
```

```
Usage: infrasim ops-sim [OPTIONS]

  Run long-running operational simulation with SLO tracking.

Options:
  -m, --model PATH                Model file path (JSON or YAML)
  -y, --yaml PATH                 YAML file with ops config
  --days INTEGER                  Simulation duration in days (1-30)  [default: 7]
  --step TEXT                     Time step: 1min, 5min, 1hour  [default: 5min]
  --html PATH                    Export HTML report
  --growth FLOAT                  Monthly traffic growth rate (0.1 = 10%)
  --diurnal-peak FLOAT           Diurnal peak multiplier  [default: 3.0]
  --weekend-factor FLOAT         Weekend traffic reduction  [default: 0.6]
  --deploy-days TEXT              Deploy days (e.g., 'tue,thu')
  --deploy-hour INTEGER          Deploy hour (0-23)  [default: 14]
  --no-random-failures           Disable random failures
  --no-degradation               Disable degradation
  --defaults                     Run all default ops scenarios
```

### 8.2 実行例

```bash
# デフォルト5シナリオ一括実行
infrasim ops-sim -y infra/infrasim-xclone.yaml --defaults

# 7日間運用シミュレーション（カスタム）
infrasim ops-sim -y infra/infrasim-xclone.yaml \
  --days 7 \
  --deploy-days "tue,thu" \
  --growth 0.1

# 30日間ストレステスト
infrasim ops-sim -y infra/infrasim-xclone.yaml \
  --days 30 \
  --step 1hour \
  --diurnal-peak 3.5 \
  --growth 0.15

# ランダム障害なし（デプロイ影響のみ評価）
infrasim ops-sim -y infra/infrasim-xclone.yaml \
  --days 7 \
  --deploy-days "mon,wed,fri" \
  --no-random-failures \
  --no-degradation

# 段階的劣化のみ評価（デプロイ・障害なし）
infrasim ops-sim -y infra/infrasim-xclone.yaml \
  --days 14 \
  --no-random-failures
```

### 8.3 YAML設定との連携

CLIオプションに加えて、YAML設定ファイルの `operational_profile` でコンポーネントごとの運用パラメータを定義できます。

```yaml
# infra/infrasim-xclone.yaml — 運用プロファイル設定例

components:
  - id: hono-api-1
    name: "Hono API Server 1"
    type: app_server
    # ... (既存の設定)

    operational_profile:
      mtbf_hours: 720          # 30日に1回の障害（平均）
      mttr_minutes: 30         # 復旧に30分
      deploy_downtime_seconds: 30  # デプロイ30秒ダウン
      maintenance_downtime_minutes: 15  # メンテナンス15分
      degradation:
        memory_leak_mb_per_hour: 10    # 1時間に10MBリーク
        disk_fill_gb_per_hour: 0.0     # ディスクリーク なし
        connection_leak_per_hour: 5    # 1時間に5コネクションリーク

    slo_targets:
      - name: "API Availability"
        metric: availability
        target: 99.9
        unit: percent
        window_days: 30
      - name: "API Latency P99"
        metric: latency_p99
        target: 500
        unit: ms
        window_days: 30

  - id: aurora-primary
    name: "Aurora Primary"
    type: database
    operational_profile:
      mtbf_hours: 2160         # 90日に1回の障害（AuroraのSLA相当）
      mttr_minutes: 60         # 復旧に60分（フェイルオーバー含む）
      deploy_downtime_seconds: 0  # DBにデプロイはない
      maintenance_downtime_minutes: 60  # メンテナンス60分
      degradation:
        memory_leak_mb_per_hour: 0
        disk_fill_gb_per_hour: 0.1  # ログ・WalTEMP蓄積
        connection_leak_per_hour: 2
```

---

## 9. v2.10までのシミュレーションとの比較

### 9.1 3つのシミュレーションモードの全体像

```
InfraSim シミュレーション3モードの比較:

┌──────────────────┬──────────────────┬──────────────────┬──────────────────┐
│                  │ v1.0 静的        │ v2.0 動的        │ v3.0 運用        │
├──────────────────┼──────────────────┼──────────────────┼──────────────────┤
│ 時間軸           │ 単一時点         │ 300秒            │ 7〜30日          │
│ ステップ         │ なし             │ 5秒              │ 5分〜1時間       │
│ トラフィック     │ なし             │ Spike/Wave/DDoS  │ Diurnal/Growth   │
│ 障害モデル       │ SPOF/カスケード  │ 動的注入         │ MTBF+劣化        │
│ スケーリング     │ なし             │ オートスケール   │ オートスケール   │
│ 評価指標         │ severity         │ severity         │ SLO/Error Budget │
│ 出力             │ PASS/WARN/CRIT   │ PASS/WARN/CRIT   │ 可用性/Budget    │
│ 用途             │ 設計検証         │ 障害耐性評価     │ 運用品質予測     │
├──────────────────┼──────────────────┼──────────────────┼──────────────────┤
│ XClone結果       │ 1,647 PASSED     │ 1,695 PASSED     │ SLO分析完了      │
│                  │ (100%)           │ (100%)           │                  │
└──────────────────┴──────────────────┴──────────────────┴──────────────────┘
```

### 9.2 検出可能な問題の違い

```
各モードで検出可能な問題:

v1.0 静的:
  ✓ SPOF (Single Point of Failure)
  ✓ カスケード障害の伝播経路
  ✓ 容量不足（静的な閾値超過）
  ✗ トラフィック変動の影響
  ✗ オートスケーリングの遅延
  ✗ 段階的劣化
  ✗ Error Budget消費

v2.0 動的:
  ✓ 上記全て +
  ✓ スパイク/DDoS耐性
  ✓ オートスケーリングの挙動
  ✓ フェイルオーバーの遅延
  ✗ デプロイ累積影響
  ✗ 段階的劣化（メモリリーク等）
  ✗ Error Budget消費推移
  ✗ 月次成長の影響

v3.0 運用:
  ✓ 上記全て +
  ✓ デプロイ頻度とSLOの関係
  ✓ メモリリーク → OOMのサイクル
  ✓ Error Budget消費速度と枯渇予測
  ✓ 月次成長のキャパシティ影響
  ✓ 複合運用条件下のSLO達成率

  v3.0 でのみ検出された問題（XClone v2.11）:
    1. SLO 99.9%が現在のMTTR（30分）では達成不可能
    2. 7日間フル運用でError Budget 3,025%超過
    3. 最大の要因はランダム障害のMTTR
    4. デプロイ単独ではSLO 99.9%を満たす（99.93%）
```

### 9.3 3モードの関係 — 補完的な評価

```
3つのモードは段階的に補完する:

  v1.0 静的                    v2.0 動的                    v3.0 運用
  ─────────────                ─────────────                ─────────────
  「設計は正しいか？」          「障害に耐えられるか？」      「運用で持つか？」

  ┌──────────┐               ┌──────────┐               ┌──────────┐
  │          │               │          │               │          │
  │  SPOF    │               │  Spike   │               │  Deploy  │
  │  検出    │               │  耐性    │               │  累積    │
  │          │    ─→         │          │    ─→         │          │
  │ カスケード│               │ Failover │               │ SLO/     │
  │  分析    │               │  速度    │               │ Budget   │
  │          │               │          │               │          │
  └──────────┘               └──────────┘               └──────────┘
  1,647 scenarios              1,695 scenarios             5 scenarios
  PASSED: 100%                 PASSED: 100%                SLO分析完了

  全体の流れ:
    v2.5: 静的シミュレーションで37個の問題発見
    v2.6-v2.7: 修正 → 静的100% PASSED
    v2.8: 動的シミュレーションで4個の新問題発見
    v2.9-v2.10: 修正 → 動的100% PASSED
    v2.11: 運用シミュレーションでSLO違反を発見  ← NEW
    v2.12+: 修正（MTTR短縮、SLO再検討）→ 運用品質向上
```

---

## 10. 今後の改善方向 — v2.12に向けて

### 10.1 SLO違反の対策案

v2.11のシミュレーション結果から、SLO 99.9%達成のための改善方向が明確になりました。

```
SLO 99.9% 達成のためのロードマップ:

Current State (v2.11):
  ops-7d-full: availability 99.28% (SLO FAIL)
  主因: MTTR 30分 × 8回のランダム障害 = 240分

Option 1: MTTR短縮 → 30分 → 5分
  対策:
    - Pod Disruption Budget (PDB) 設定
    - Liveness/Readiness Probe のチューニング
    - Automatic rollback on failed health check
  期待効果:
    downtime = 5分 × 8 + 10分(deploys) + 50分(maint) + 5分(degrade)
             = 105分
    availability ≈ 99.89% (SLO 99.9%にほぼ到達)

Option 2: 冗長化強化 → ランダム障害の影響ゼロ化
  対策:
    - 全コンポーネント3レプリカ以上
    - Pod Anti-Affinity でAZ分散
    - 1レプリカDOWN → 残りが吸収
  期待効果:
    single-replica failure → availability impact: 0
    downtime ≈ 10分(deploys) + 50分(maint) = 60分
    availability ≈ 99.94% (SLO PASS!)

Option 3: SLO再検討 → 99.5%
  理由:
    - 99.9%は月43分のダウンタイム
    - 99.5%は月216分のダウンタイム
    - 現状の305分/7日 → 30日換算1,307分は99.5%も未達
    - Option 1+2 が先行で必要

推奨: Option 1 (MTTR短縮) + Option 2 (冗長化)
  → v2.12 で実装し、再シミュレーション
```

### 10.2 将来のInfraSim機能

```
InfraSim ロードマップ:

v3.1 (計画):
  ├ Chaos Calendar: 過去のインシデント履歴からのシナリオ生成
  ├ Cost Tracking: 運用シミュレーション中のコスト推定
  └ Multi-Region: リージョン間フェイルオーバーの時間モデル

v3.2 (構想):
  ├ Capacity Planning: 「N月後に何台必要か」の自動予測
  ├ Budget Forecast: Error Budget枯渇日の予測
  └ What-if Analysis: 「MTTRをX分にしたらSLO達成率はY%」
```

---

## 11. まとめ

### 11.1 v2.11の成果

```
v2.11 のキーポイント:

1. InfraSim v3.0 運用シミュレーション機能
   ├ Long-Running Simulation: 7〜30日 × 5分〜1時間ステップ
   ├ Operational Event Injection: デプロイ/メンテナンス/障害/劣化
   ├ SLO/Error Budget Tracker: 可用性/レイテンシ/エラー率
   └ Diurnal-Weekly + Growth Trend: 複合トラフィック

2. XClone v2 での発見
   ├ Baseline (7d): 100% availability ← 問題なし
   ├ With deploys (7d): 99.93% ← SLO 99.9% PASS
   ├ Full ops (7d): 99.28% ← SLO 99.9% FAIL!
   └ 原因: MTTR 30分 × ランダム障害 → Error Budget 3,025%超過

3. 改善方向の明確化
   ├ MTTR 30分 → 5分（自動復旧強化）
   ├ 冗長化強化（3レプリカ以上）
   └ v2.12で実装・再シミュレーション予定
```

### 11.2 InfraSimの進化まとめ

```
InfraSim 進化の全体像:

v1.0 (静的)     →    v2.0 (動的)     →    v3.0 (運用)
─────────────        ─────────────        ─────────────
「壊れないか？」      「耐えられるか？」    「運用で持つか？」

  SPOF検出              Spike耐性            SLO達成率
  カスケード分析        フェイルオーバー      Error Budget
  容量チェック          オートスケール        段階的劣化
                                              デプロイ影響
                                              成長予測

  1,647シナリオ          1,695シナリオ          5シナリオ
  → 100% PASSED          → 100% PASSED         → SLO分析
```

### 11.3 v2シリーズの全体像（v2.11時点）

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
v2.8: 動的シミュレーション           InfraSim v2.0で1,695シナリオ動的シミュレーション
  ↓
v2.9: レジリエンス強化II             InfraSim v2.1 + YAML v8 でWARNING 2→1
  ↓
v2.10: 完全PASSED                    二重遮断CB + 3,351シナリオ全PASSED
  ↓
v2.11: 運用シミュレーション（本記事） InfraSim v3.0 + SLO/Error Budget + 段階的劣化
```

v2.10までの**障害耐性設計**（「壊れないか？」「耐えられるか？」）に加え、v2.11の**運用シミュレーション**（「運用で持つか？」）により、本番投入前に**運用品質まで予測可能**になりました。

次回v2.12では、v2.11で発見されたSLO違反を修正し、**MTTR短縮と冗長化強化**で99.9% SLO達成を目指します。

---

**リポジトリ**: [InfraSim](https://github.com/ymaeda-it/infrasim) / [XClone v2](https://github.com/ymaeda-it/xclone-v2)
