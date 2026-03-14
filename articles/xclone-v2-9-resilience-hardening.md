---
title: "Xクローン v2.9 — サーキットブレーカー＋Singleflight＋キャッシュウォーミングで動的シミュレーションWARNINGを解消"
emoji: "🛡️"
type: "tech"
topics: ["infrasim", "chaosengineering", "sre", "kubernetes", "circuitbreaker"]
published: true
---

## はじめに — v2.8で発見された2つの課題

[前回のv2.8記事](https://qiita.com/ymaeda_it/items/)では、InfraSim v2.0の**動的シミュレーション**を導入し、静的シミュレーションでは検出不可能だった問題を発見しました。1,695シナリオを実行した結果、2つの重要なWARNINGが浮上しました。

```
v2.8 で発見された問題:

1. Flash Crowd 15x + cache stampede
   severity: 4.3 (WARNING)
   原因: キャッシュ復旧直後のcold cache storm
         15xトラフィック × キャッシュミス100% → Aurora直撃
         38回のオートスケーリングでも追いつかず

2. Aurora 20x レイテンシカスケード
   severity: 6.8 (WARNING)
   原因: PgBouncer→Aurora間にサーキットブレーカーなし
         Aurora遅延 → PgBouncerタイムアウト → リトライ3x
         → コネクション 200*3=600 > pool_size 100 → プール枯渇
         → 32コンポーネントに連鎖

3. シミュレーションの現実性
   Pod起動遅延: 15秒（InfraSim設定値）
   実際のK8s HPA: 30-60秒
   → シミュレーションが楽観的すぎる
```

v2.8では「問題を発見した」段階で終わっていました。v2.9では、これらの問題に対して**4つのレジリエンス機構**をInfraSimエンジン（v2.1）に追加し、YAMLをv8にアップグレードして実際に解消します。

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
| **10** | **v2.9 -- レジリエンス強化（本記事）** | **InfraSim v2.1 / CB + Singleflight + Cache Warming / WARNING解消** |

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
v2.8: 動的シミュレーション           InfraSim v2.0で1,695シナリオ動的シミュレーション
  ↓
v2.9: レジリエンス強化II（本記事）   InfraSim v2.1 + YAML v8 でWARNING解消
```

---

## 2. InfraSim v2.1 -- 4つのレジリエンス機構

v2.8で発見された問題を解消するため、InfraSim v2.1では4つの新しいメカニズムを追加しました。それぞれが特定の障害パターンに対応しています。

```
問題 → 対策のマッピング:

  Aurora 20x レイテンシカスケード (severity 6.8)
    ├→ (1) Circuit Breaker: PgBouncer→Auroraの依存にCB追加
    └→ (2) Adaptive Retry: 固定3xリトライ → 指数バックオフ+ジッター

  Flash Crowd 15x + cache stampede (severity 4.3)
    ├→ (3) Cache Warming: Redis復旧後のウォーミング期間を導入
    └→ (4) Singleflight: 重複リクエストの集約で実効負荷を低減

  Pod起動遅延の現実性
    └→ (5) scale_up_delay_seconds: 15s → 30s
```

### 2.1 Circuit Breaker -- 依存エッジのサーキットブレーカー

#### なぜ必要か

v2.8のレイテンシカスケードでは、Aurora Primary が20x遅延を起こした際に、PgBouncerがタイムアウトまで待機し、リトライを3回繰り返し、コネクションプールを枯渇させていました。問題の本質は**「遅い依存に対してリクエストを送り続けた」**ことです。

サーキットブレーカーは、依存先が異常だと検知した時点でリクエスト送信を止め、カスケード伝播を遮断します。

#### 3状態ステートマシン

```
Circuit Breaker State Machine

    ┌────────────────────────────────────────────────────────┐
    │                                                        │
    │   ┌──────────┐    failure_count     ┌──────────┐      │
    │   │          │    >= threshold       │          │      │
    │   │  CLOSED  │─────────────────────→│   OPEN   │      │
    │   │ (正常)   │                       │ (遮断中) │      │
    │   │          │←─────────────────────│          │      │
    │   └──────────┘  success in           └────┬─────┘      │
    │        ↑        HALF_OPEN                 │            │
    │        │                                  │            │
    │        │        recovery_timeout          │            │
    │        │        (30s) elapsed             │            │
    │        │                                  ▼            │
    │        │                            ┌──────────┐      │
    │        │                            │          │      │
    │        └────────────────────────────│HALF_OPEN │      │
    │              target HEALTHY          │ (試行中) │      │
    │                                     │          │      │
    │                                     └────┬─────┘      │
    │                                          │            │
    │                    target still ──────────┘            │
    │                    unhealthy → back to OPEN            │
    │                                                        │
    └────────────────────────────────────────────────────────┘

CLOSED:
  - 通常運用。リクエストは依存先に送信される
  - 依存先がDOWN/OVERLOADED → failure_count++
  - failure_count >= failure_threshold → OPEN に遷移

OPEN:
  - 遮断中。依存先へのリクエストは即座にfail-fast
  - カスケード伝播がここで止まる
  - recovery_timeout 経過後 → HALF_OPEN に遷移

HALF_OPEN:
  - 試験的にリクエストを通す
  - 依存先がHEALTHY → CLOSED に戻る（正常復帰）
  - 依存先がまだ異常 → OPEN に再遷移
```

#### Pydanticモデル

```python
# src/infrasim/model/components.py

class CircuitBreakerConfig(BaseModel):
    """Circuit breaker configuration for a dependency edge."""

    enabled: bool = False
    failure_threshold: int = 5       # 連続失敗回数でOPENに遷移
    recovery_timeout_seconds: float = 60.0  # OPEN維持時間
    half_open_max_requests: int = 3  # HALF_OPENで許可するリクエスト数
    success_threshold: int = 2       # HALF_OPENからCLOSEDに戻る成功回数
```

`CircuitBreakerConfig` は `Dependency` モデル（依存エッジ）に配置されます。コンポーネント単体ではなく、**特定の依存関係（A→B）ごとに独立したCB**を持つ設計です。`Dependency` には `circuit_breaker` と `retry_strategy` の2つの新フィールドが追加されました。

#### CBがカスケードを遮断する仕組み

動的エンジン内では、各CBエッジごとに `_CircuitBreakerDynamicState`（state / failure_count / open_since_seconds）を保持し、毎タイムステップで `_evaluate_circuit_breakers()` を実行します。CBがOPEN状態のとき、`_run_cascade_at_step()` は**その依存エッジを通じた障害伝播をスキップ**します。

```python
# dynamic_engine.py — _run_cascade_at_step 内（CB遮断ロジック）

cb_blocked_targets: set[str] = set()
if cb_states:
    for (src, tgt), cb in cb_states.items():
        if cb.state == _CBState.OPEN:
            cb_blocked_targets.add(tgt)

# カスケード効果のうち、CBがblockしている依存先からの伝播を抑制
for effect in chain.effects:
    if effect.component_id != target_id and target_id in cb_blocked_targets:
        continue  # カスケード遮断!
```

これにより、Aurora Primary が遅延しても、PgBouncer→AuroraのCBがOPENになった時点で**それ以降の連鎖（PgBouncer→Envoy→hono-api→ALB）が止まります**。

---

### 2.2 Adaptive Retry -- 指数バックオフ＋ジッター

#### なぜ必要か

v2.8では、全コンポーネントが `retry_multiplier: 3.0` を使用していました。これは「タイムアウト時に3倍のコネクションが発生する」という固定的なモデルです。

実際のリトライは**指数バックオフ＋ジッター**で実装されるべきで、固定3x乗算はThundering Herd（雷鳴の群れ）問題を引き起こします。

```
固定リトライ (v2.8):
  リクエスト失敗
    → 即リトライ1回目
    → 即リトライ2回目
    → 即リトライ3回目
  = 元のコネクション数 * 3.0 が同時発生

Adaptive Retry (v2.9):
  リクエスト失敗
    → 100ms後にリトライ1回目
    → 200ms + jitter 後にリトライ2回目
    → 400ms + jitter 後にリトライ3回目
  = リトライが時間的に分散される
  = 実効コネクション乗数: 1 + max_retries * 0.3 ≒ 1.9x
```

#### Pydanticモデル

```python
# src/infrasim/model/components.py

class RetryStrategy(BaseModel):
    """Adaptive retry with exponential backoff + jitter."""

    enabled: bool = False
    max_retries: int = 3
    initial_delay_ms: float = 100.0      # 初回リトライ遅延
    max_delay_ms: float = 30000.0        # 最大リトライ遅延
    multiplier: float = 2.0              # delay = initial * multiplier^attempt
    jitter: bool = True                  # ランダムジッターの有無
    retry_budget_per_second: float = 0.0 # 0=無制限, >0=1秒あたりの最大リトライ数
```

#### カスケードエンジンでの適用

レイテンシカスケード計算時に、`RetryStrategy` が設定されたエッジでは固定 `retry_multiplier` の代わりに**Adaptive Retryの実効乗数**を使用します。実効コネクション数は `base_connections * (1 + max_retries * 0.3)` で計算されます。

**実効乗数の比較:**

| 方式 | 計算式 | max_retries=3 の場合 |
|------|--------|---------------------|
| 固定リトライ | `connections * retry_multiplier` | `200 * 3.0 = 600` |
| Adaptive Retry | `connections * (1 + max_retries * 0.3)` | `200 * 1.9 = 380` |

固定3xリトライでは600コネクション（> pool_size 100）でプール枯渇でしたが、Adaptive Retryでは380コネクションに抑制されます。pool_sizeが3000に拡張された状態（後述）では安全圏内です。

---

### 2.3 Cache Warming -- キャッシュ復旧後のウォーミング期間

#### なぜ必要か

v2.8の「Flash Crowd 15x + cache stampede」では、Redis Cluster全ノードが障害→復旧した直後に**キャッシュヒット率0%**の状態で15xトラフィックが殺到し、全リクエストがAuroraに直撃しました。

実際のキャッシュ復旧は瞬時にフルヒットに戻るわけではなく、**ウォーミング期間**が必要です。Cache Warmingはこの「コールドスタート」の期間をモデリングし、利用率計算に**ウォーミングペナルティ**を加えます。

```
Cache Warming Curve (linear, 120s warm-up)

ヒット率
  1.0 |                                    ──────────── (full hit)
      |                                 /
  0.8 |                              /
      |                           /
  0.6 |                        /
      |                     /
  0.4 |                  /
      |               /
  0.2 |            /
      |         /
  0.1 |── ── /                           (initial_hit_ratio = 0.1)
      |    /
  0.0 |
      └──────────────────────────────────────────────→ 時間(秒)
      0                60               120
         ↑ 復旧                          ↑ ウォーミング完了
         (DOWN→HEALTHY)


ウォーミングペナルティ (utilization乗数):

ペナルティ
  2.8 |── (t=0: penalty = 1.0 + (1.0-0.1)*2.0 = 2.8)
      |    \
  2.4 |     \
      |      \
  2.0 |       \
      |        \
  1.6 |         \
      |          \
  1.2 |           \
      |            \
  1.0 |             ─────────────────── (penalty = 1.0, no impact)
      └──────────────────────────────────────────────→ 時間(秒)
      0                60               120
```

#### Pydanticモデル

```python
# src/infrasim/model/components.py

class CacheWarmingConfig(BaseModel):
    """Cache warming behaviour after recovery from DOWN."""

    enabled: bool = False
    initial_hit_ratio: float = 0.0    # 復旧直後のヒット率 (0-1)
    warm_duration_seconds: int = 300  # フルヒットに到達するまでの時間
    warming_curve: str = "linear"     # linear or exponential
```

`CacheWarmingConfig` は `Component` モデルに直接配置されます（キャッシュタイプのコンポーネント用）。

#### 動的エンジンでの適用

フェイルオーバー回復時にCache Warmingが自動起動します。`_evaluate_failover()` で回復完了を検知すると `is_warming = True` に設定。以降、`_apply_traffic()` が毎ステップで以下の計算を行います。

```python
# warming_penalty = 1.0 + (1.0 - current_hit_ratio) * 2.0
# current_hit_ratio = initial + (1.0 - initial) * (elapsed / warm_duration)
```

**ペナルティの数値例（initial_hit_ratio=0.1, warm_duration=120s）:**

| 経過時間 | progress | current_hit_ratio | warming_penalty | 効果 |
|---------|----------|-------------------|-----------------|------|
| 0s | 0.0 | 0.10 | 2.80 | 利用率2.8倍 |
| 30s | 0.25 | 0.325 | 2.35 | 利用率2.35倍 |
| 60s | 0.50 | 0.55 | 1.90 | 利用率1.9倍 |
| 90s | 0.75 | 0.775 | 1.45 | 利用率1.45倍 |
| 120s | 1.00 | 1.00 | 1.00 | ペナルティなし |

このモデリングにより、「キャッシュ復旧 = 即座に全リクエストキャッシュヒット」という非現実的な前提を排除し、**コールドキャッシュ期間中のDB負荷急増を正しく評価**できます。

---

### 2.4 Singleflight / Request Coalescing -- 重複リクエストの集約

#### なぜ必要か

フラッシュクラウドやキャッシュスタンピードでは、同一キー（例: 同じツイートのデータ）に対する大量の並行リクエストが発生します。Singleflight（Go言語のsync/singleflight由来の概念）は、**同一キーに対する重複リクエストを1つにまとめ、結果を全リクエストに配布する**パターンです。

```
Singleflightなし:
  リクエストA (tweet_id=123) → DB問い合わせ → 結果
  リクエストB (tweet_id=123) → DB問い合わせ → 結果  ← 重複!
  リクエストC (tweet_id=123) → DB問い合わせ → 結果  ← 重複!
  → DBへの負荷: 3クエリ

Singleflightあり (coalesce_ratio=0.7):
  リクエストA (tweet_id=123) → DB問い合わせ → 結果 → A,B,Cに配布
  リクエストB (tweet_id=123) → coalesced (Aの結果を待つ)
  リクエストC (tweet_id=123) → coalesced (Aの結果を待つ)
  → DBへの負荷: 1クエリ（70%削減）
```

#### Pydanticモデル

```python
# src/infrasim/model/components.py

class SingleflightConfig(BaseModel):
    """Singleflight / request coalescing to deduplicate concurrent requests."""

    enabled: bool = False
    coalesce_ratio: float = 0.8  # 重複リクエストの集約率 (0-1)
```

`SingleflightConfig` は `Component` モデルに配置されます。hono-api（アプリケーション層）とpgbouncer（DB接続プーラー層）の両方に設定可能です。

#### エンジンでの適用

動的エンジンの `_apply_traffic()` で `effective_multiplier = multiplier * (1.0 - coalesce_ratio)` として実効倍率を低減します。カスケードエンジンの `simulate_latency_cascade()` でも `base_connections *= (1.0 - coalesce_ratio)` でコネクション数を削減します。

**実効倍率の比較:**

| コンポーネント | coalesce_ratio | 15xトラフィック時の実効倍率 |
|---------------|----------------|--------------------------|
| hono-api | 0.7 | `15 * (1 - 0.7) = 4.5x` |
| pgbouncer | 0.6 | `15 * (1 - 0.6) = 6.0x` |
| Singleflightなし | - | `15x` |

15xフラッシュクラウドが、hono-apiレベルで4.5xに、pgbouncerレベルで6.0xに低減されます。これにより、キャッシュ不在時のDB直撃負荷が大幅に軽減されます。

---

### 2.5 リアルな Pod 起動遅延 -- 30秒に拡大

v2.8では `scale_up_delay_seconds: 15` でしたが、実際のKubernetes HPAでは以下の遅延が発生します。

```
実際のKubernetes HPAスケールアップ遅延:

  Metrics collection:     15-30秒 (metrics-server polling interval)
  HPA decision:           0-15秒 (stabilization window)
  Pod scheduling:         1-5秒  (scheduler + node selection)
  Container pull + start: 10-30秒 (image pull + readiness probe)
  ──────────────────────────────────
  合計:                   30-60秒

InfraSim v2.0: scale_up_delay_seconds = 15秒 (楽観的)
InfraSim v2.1: scale_up_delay_seconds = 30秒 (より現実的)
```

この変更により、「スケールアップが間に合うか」の評価がより厳密になります。

---

## 3. YAML v8 の変更点

InfraSim v2.1の機能を活用するため、XCloneのインフラ定義YAMLをv7からv8にアップグレードしました。

### 3.1 PgBouncer: connection_pool_size拡大 + CB + Adaptive Retry

```yaml
# infra/infrasim-xclone.yaml (v8) — PgBouncer設定

- id: pgbouncer-1
  name: "PgBouncer (Connection Pooler) Pod 1"
  type: app_server
  replicas: 2
  capacity:
    max_connections: 5000
    connection_pool_size: 3000     # <-- v7: 2000 → v8: 3000 (1.5x拡大)
    timeout_seconds: 30
    retry_multiplier: 3.0
  singleflight:                    # <-- v8 NEW
    enabled: true
    coalesce_ratio: 0.6            #     60%の重複クエリを集約
  autoscaling:
    enabled: true
    min_replicas: 2
    max_replicas: 8
    scale_up_threshold: 60
    scale_down_threshold: 25
    scale_up_delay_seconds: 30     # <-- v7: 10 → v8: 30 (現実的Pod起動遅延)
    scale_up_step: 2
```

### 3.2 PgBouncer→Aurora: Circuit Breaker + Retry Strategy (依存エッジ)

```yaml
# infra/infrasim-xclone.yaml (v8) — PgBouncer→Aurora 依存設定

dependencies:
  - source_id: pgbouncer-1
    target_id: aurora-primary
    dependency_type: requires
    protocol: tcp
    port: 5432
    latency_ms: 1.0
    weight: 1.0
    circuit_breaker:               # <-- v8 NEW: CB追加
      enabled: true
      failure_threshold: 3         # 3回連続失敗でOPEN
      recovery_timeout_seconds: 30 # 30秒後にHALF_OPENで試行
      half_open_max_requests: 3
      success_threshold: 2
    retry_strategy:                # <-- v8 NEW: Adaptive Retry追加
      enabled: true
      max_retries: 3
      initial_delay_ms: 100
      max_delay_ms: 30000
      multiplier: 2.0              # 100ms → 200ms → 400ms
      jitter: true
      retry_budget_per_second: 50  # 1秒あたり最大50回のリトライ

  # aurora-replica-1, aurora-replica-2 にも同様のCB + Retry設定を適用
```

### 3.3 hono-api: Singleflight有効化

```yaml
# infra/infrasim-xclone.yaml (v8) — hono-api（変更箇所のみ抜粋）

- id: hono-api-1
  # ... 既存設定は省略 ...
  singleflight:                    # <-- v8 NEW
    enabled: true
    coalesce_ratio: 0.7            #     70%の重複リクエストを集約
  autoscaling:
    # ... 他の設定は省略 ...
    scale_up_delay_seconds: 30     # <-- v7: 15 → v8: 30
```

### 3.4 Redis Cluster: Cache Warming有効化

```yaml
# infra/infrasim-xclone.yaml (v8) — Redis Cluster（変更箇所のみ抜粋）

- id: redis-cluster
  # ... 既存設定は省略 ...
  cache_warming:                   # <-- v8 NEW
    enabled: true
    initial_hit_ratio: 0.1         # 復旧直後: ヒット率10%
    warm_duration_seconds: 120     # 120秒でフルヒットに到達
    warming_curve: "linear"        # 線形ウォーミング
```

### 3.5 v7→v8 変更点サマリー

| 項目 | v7 | v8 | 理由 |
|------|----|----|------|
| PgBouncer pool_size | 2,000 | **3,000** | リトライストーム耐性向上 |
| PgBouncer→Aurora CB | なし | **enabled (threshold=3, timeout=30s)** | カスケード遮断 |
| PgBouncer→Aurora Retry | 固定 3.0x | **Adaptive (exponential backoff + jitter)** | Thundering Herd防止 |
| hono-api singleflight | なし | **enabled (coalesce_ratio=0.7)** | 重複リクエスト70%削減 |
| pgbouncer singleflight | なし | **enabled (coalesce_ratio=0.6)** | 重複クエリ60%削減 |
| redis-cluster cache_warming | なし | **enabled (120s warm, 0.1 initial)** | コールドキャッシュ対策 |
| scale_up_delay_seconds | 15s (一部10s) | **30s** | 現実的Pod起動遅延 |

---

## 4. シミュレーション結果 -- v2.8 vs v2.9

### 4.1 全体結果

```
╔══════════════════════════════════════════════════════════════════╗
║  InfraSim v2.1 Simulation Report — XClone v2.9                  ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  ■ Static Simulation                                            ║
║    Total:     1,647                                              ║
║    CRITICAL:      0                                              ║
║    WARNING:       0                                              ║
║    PASSED:    1,647                                              ║
║                                                                  ║
║  ■ Dynamic Simulation                                           ║
║    Total:     1,695                                              ║
║    CRITICAL:      2  (total meltdown + LB partition)            ║
║    WARNING:       1  (rolling restart 4.0)                      ║
║    PASSED:    1,692                                              ║
║                                                                  ║
║  ■ 改善                                                         ║
║    動的WARNING: 2 → 1 (flash crowd stampede解消!)               ║
║    レイテンシカスケード: 6.8 → 6.6 (CB 1 trip)                  ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
```

### 4.2 9カスタムシナリオの詳細比較

| # | シナリオ | v2.8 Severity | v2.8 結果 | v2.9 Severity | v2.9 結果 | 変化 |
|---|---------|:------------:|:---------:|:------------:|:---------:|------|
| 1 | DDoS Volumetric 10x | 0.9 | PASSED | 0.9 | PASSED | -- |
| 2 | DDoS Slowloris 5x | 0.0 | PASSED | 0.0 | PASSED | -- |
| 3 | Flash Crowd 8x | 0.0 | PASSED | 0.0 | PASSED | -- |
| 4 | Viral event 15x + DB failure | 3.5 | PASSED | 3.5 | PASSED | -- |
| 5 | Diurnal 3x + cache failure | 0.9 | PASSED | 0.9 | PASSED | -- |
| 6 | Spike 5x + deployment | 0.3 | PASSED | 0.3 | PASSED | -- |
| 7 | DDoS 10x + network partition | 2.1 | PASSED | **1.7** | PASSED | **-0.4** |
| 8 | Wave 5x + memory exhaustion | 0.3 | PASSED | 0.3 | PASSED | -- |
| 9 | **Flash Crowd 15x + cache stampede** | **4.3** | **WARNING** | **3.8** | **PASSED** | **-0.5** |

シナリオ9（Flash Crowd 15x + cache stampede）が**severity 4.3 (WARNING) → 3.8 (PASSED)** に改善しました。4つの改善の複合効果です。

#### シナリオ9 改善のメカニズム

```
v2.8 (severity 4.3 — WARNING):
  全cache DOWN + 15x flash crowd
  → キャッシュミス100% → 全リクエストがAurora直撃
  → PgBouncer: 200conn * 3.0x retry = 600 > pool_size 2000? No, but
    15x traffic * 200 base = 3000 conn → pool枯渇
  → hono-api: 38回のスケーリングイベント（追いつかず）
  → severity 4.3

v2.9 (severity 3.8 — PASSED):
  全cache DOWN + 15x flash crowd

  (1) Singleflight on hono-api (coalesce 0.7):
      実効トラフィック: 15x * 0.3 = 4.5x

  (2) Singleflight on pgbouncer (coalesce 0.6):
      実効クエリ倍率: 4.5x * 0.4 = 1.8x

  (3) Cache Warming on redis-cluster:
      復旧後120秒でヒット率0.1→1.0
      ウォーミング中のDB負荷を段階的に低減

  (4) Adaptive Retry on pgbouncer→aurora:
      実効コネクション: base * (1 + 3*0.3) = base * 1.9x
      vs 旧: base * 3.0x

  (5) PgBouncer pool_size 3000:
      バースト耐性向上

  複合効果: severity 4.3 → 3.8 (WARNING帯を脱出!)
```

シナリオ7（DDoS 10x + network partition）も severity 2.1 → 1.7 に改善。CBがネットワーク分断コンポーネントへのカスケード伝播を早期遮断しています。

### 4.3 レイテンシカスケード結果

```
Aurora 20x レイテンシカスケード — v2.8 vs v2.9 比較:

v2.8:
  起点: aurora-primary (60,000ms)
  → pgbouncer: TIMEOUT → retry 3x → 600 conn > pool 2000
  → envoy-cb: cascade → retry → 1050 conn > pool 100
  → hono-api: cascade DOWN
  → 全32コンポーネント影響
  → CB trips: 0
  → severity: 6.8

v2.9:
  起点: aurora-primary (60,000ms)
  → pgbouncer: TIMEOUT detected
    → Circuit Breaker: failure_count=1,2,3 → OPEN!
    → cascade propagation BLOCKED at pgbouncer→aurora edge
  → pgbouncer自体はDEGRADED (CB tripped, not DOWN)
  → しかしenvoy-sidecar→pgbouncerにはCBなし
    → sidecar群がDOWNになるカスケードは依然発生
  → 32コンポーネント影響（sidecar経由のカスケードが残存）
  → CB trips: 1 (pgbouncer→aurora-primary)
  → severity: 6.6

  改善幅: 6.8 → 6.6 (-0.2)
```

CBが1箇所（pgbouncer→aurora-primary）でトリップし、severity が6.8→6.6に微改善しました。しかし、**envoy-sidecar→pgbouncer間にCBがないため、サイドカー群のカスケードDOWNは防げていません。** これはv2.10の課題です。

```
レイテンシカスケードの遮断ポイント:

  aurora-primary (60,000ms 遅延)
      │
      ▼
  pgbouncer-1~4
      │
      ├→ [pgbouncer→aurora] CB: OPEN! ← v2.9で追加
      │   └→ aurora方向への新規リクエストを遮断
      │   └→ pgbouncer自体はDEGRADED（DOWNではない）
      │
      ▼  しかし…
  envoy-sidecar-1~12
      │
      ├→ [sidecar→pgbouncer] CB: なし ← v2.10で追加予定
      │   └→ pgbouncerがDEGRADEDだと、sidecarにも伝播
      │   └→ sidecar群がDOWNに
      │
      ▼
  hono-api-1~12 → ALB → ユーザー影響

  v2.9で遮断: pgbouncer→aurora（1層目）
  v2.10で遮断: sidecar→pgbouncer（2層目）
```

---

## 5. 多層防御と各機構の貢献度

4つの機構は**異なるレイヤーで異なる問題に対処**する多層防御（Defense in Depth）を構成しています。

```
多層防御アーキテクチャ:

Layer 4: Application (hono-api)
  └→ Singleflight (70%): 下流への負荷そのものを減らす

Layer 3: Connection Pooler (pgbouncer)
  └→ Singleflight (60%) + Circuit Breaker + Adaptive Retry
      → DB層への負荷を制御し、カスケードを遮断

Layer 2: Cache (redis-cluster)
  └→ Cache Warming: 復旧直後のDB直撃を防止

Layer 1: Database (aurora)
  └→ pool_size拡大: リトライストーム時の最後の砦
```

```
Flash Crowd 15x + cache stampede での負荷低減チェーン:

  元の負荷:          15.0x
    ↓ Singleflight (hono-api, 0.7):     15.0 * 0.3 = 4.5x
    ↓ Singleflight (pgbouncer, 0.6):     4.5 * 0.4 = 1.8x
    ↓ Cache Warming (penalty 2.8→1.0):   最大5.04x → 最終1.8x
    ↓ Adaptive Retry (1.9x vs 3.0x):     さらに低減
  → severity 4.3 → 3.8
```

いずれも**追加インフラコストはゼロ**。実インフラでは Envoy CB設定 / SDK retry設定 / Redis pre-loading script / Go singleflight ライブラリで実現できます。

---

## 6. 残る課題と次のステップ（v2.10へ）

### 6.1 レイテンシカスケード severity 6.6 -- sidecar層のCB不在

```
現状 (v2.9):
  pgbouncer→aurora: CB あり → severity 6.8 → 6.6 (-0.2)
  sidecar→pgbouncer: CB なし → sidecar群が依然DOWNに

対策 (v2.10):
  sidecar→pgbouncer にも CB を追加
  → sidecar層でのカスケード遮断
  → 影響コンポーネント数を32から大幅に削減予定

期待される改善:
  severity 6.6 → 4.0未満 (PASSED)
  影響コンポーネント: 32 → 5-8程度
```

### 6.2 Rolling restart failure severity 4.0 -- PDB未設定

```
現状 (v2.9):
  Rolling restart シナリオ: severity 4.0 (WARNING)
  原因: 同時に過剰なPodがterminateされ、一時的に処理能力不足

対策 (v2.10):
  PodDisruptionBudget (PDB):
    maxUnavailable: 1  (同時に1 Podまでしかterminateしない)
  または:
    minAvailable: 80%  (常に80%のPodが稼働していることを保証)

  InfraSimでのモデリング:
    PDBConfig を Component に追加
    Rolling restart時の同時停止数を制限
```

### 6.3 v2.10 ロードマップ

```
v2.10 予定:
  ┌─────────────────────────────────────────────┐
  │ (1) sidecar→pgbouncer CB追加               │
  │     → レイテンシカスケード severity < 4.0   │
  │                                             │
  │ (2) PDB (PodDisruptionBudget) モデリング    │
  │     → Rolling restart severity < 4.0        │
  │                                             │
  │ (3) 動的シミュレーション全PASSED目標        │
  │     → CRITICAL 2 (理論的最悪のみ)          │
  │     → WARNING 0                             │
  │     → PASSED 1,693+                         │
  └─────────────────────────────────────────────┘
```

---

## 7. まとめ

### 達成したこと

InfraSim v2.1で4つのレジリエンス機構を追加し、v2.8で発見された**Flash Crowd 15x + cache stampede のWARNINGを解消**しました。

```
v2.8 → v2.9 の改善サマリー:

  InfraSim:
    v2.0 → v2.1 (4つの新機構)
    + CircuitBreakerConfig (依存エッジ)
    + RetryStrategy (Adaptive Retry)
    + CacheWarmingConfig (キャッシュ復旧)
    + SingleflightConfig (リクエスト集約)

  YAML:
    v7 → v8 (6項目の変更)

  結果:
    Flash Crowd 15x + cache stampede:
      severity 4.3 (WARNING) → 3.8 (PASSED)  ✅

    Aurora 20x latency cascade:
      severity 6.8 → 6.6 (CB 1 trip)         △ (改善中)

    DDoS 10x + network partition:
      severity 2.1 → 1.7                      ✅

  動的シミュレーション:
    WARNING: 2 → 1 (rolling restart のみ残存)
    PASSED: 1,691 → 1,692
```

### v2.10へ向けて

```
v2.9:
  動的: CRITICAL 2 / WARNING 1 / PASSED 1,692
  レイテンシカスケード: 6.6

v2.10 (目標):
  動的: CRITICAL 2 / WARNING 0 / PASSED 1,693+
  レイテンシカスケード: < 4.0

  残りのWARNINGを解消し、
  動的シミュレーションでも全PASSED を達成する。
```

> **更新**: [v2.10記事](https://qiita.com/ymaeda_it/items/)で目標を達成しました。全12サイドカー→PgBouncerエッジにCBを追加し、**3,351シナリオ完全PASSED**（CRITICAL 0, WARNING 0）を実現。

---

**リポジトリ**:
- InfraSim: [github.com/ymaeda-it/infrasim](https://github.com/ymaeda-it/infrasim)
- XClone v2: [github.com/ymaeda-it/xclone-v2](https://github.com/ymaeda-it/xclone-v2)
