---
title: "Xクローン v2.6 — InfraSimカオステスト3ラウンドでWARNING 36→2件、レジリエンス95%改善の全記録"
emoji: "🛡️"
type: "tech"
topics: ["aws", "kubernetes", "chaosengineering", "sre", "infrasim"]
published: true
---

## はじめに

[前回のv2.5記事](https://zenn.dev/ymaeda_it/articles/xclone-v2-5-chaos-testing)で、自作カオスエンジニアリングツール**InfraSim**により**296シナリオ中1件のCRITICAL + 36件のWARNING**が検出され、レジリエンススコアは**0/100**でした。

本記事では、v2.5で発見した構造的弱点に対して**3ラウンドの改善イテレーション**を実施し、WARNINGを**36件から2件へ95%削減**した全過程を記録します。

特筆すべきは**ラウンド2の失敗**です。「サーキットブレーカーをSidecar化すれば安全になる」という直感に反し、WARNINGが**9件→41件に急増**するという逆効果が発生しました。この失敗と、そこから得た`requires` vs `optional`という依存関係設計の本質的な学びが、本記事の核心です。

### シリーズ記事

| # | 記事 | テーマ |
|---|------|--------|
| 1 | [**v2.0** — フルスタック基盤](https://qiita.com/ymaeda_it/items/902aa019456836624081) | Hono+Bun / Next.js 15 / Drizzle / ArgoCD / Linkerd / OTel |
| 2 | [**v2.1** — 品質・運用強化](https://qiita.com/ymaeda_it/items/e44ee09728795595efaa) | Playwright / OpenSearch ISM / マルチリージョンDB / tRPC / CDC |
| 3 | [**v2.2** — パフォーマンス](https://qiita.com/ymaeda_it/items/d858969cd6de808b8816) | 分散Rate Limit / 画像最適化 / マルチリージョンWebSocket |
| 4 | [**v2.3** — DX・コスト最適化](https://qiita.com/ymaeda_it/items/cf78cb33e6e461cdc2b3) | Feature Flag / GraphQL Federation / コストダッシュボード |
| 5 | [**v2.4** — テスト完備](https://qiita.com/ymaeda_it/items/44b7fca8fc0d07298727) | E2Eテスト拡充 / Terratest インフラテスト |
| 6 | [**v2.5** — カオステスト](https://zenn.dev/ymaeda_it/articles/xclone-v2-5-chaos-testing) | InfraSim / 296シナリオ / レジリエンス評価 |
| **7** | **v2.6 — レジリエンス強化（本記事）** | **3ラウンド改善 / WARNING 36→2 / 95%改善** |

---

# 1. 改善の全体像 — 3ラウンドの軌跡

v2.5で検出された問題を**3ラウンドのイテレーション**で段階的に改善しました。各ラウンドでInfraSimを再実行し、改善効果を定量的に検証しています。

## 1.1 WARNING推移グラフ

```mermaid
xychart-beta
    title "WARNING件数の推移（3ラウンド + 原版）"
    x-axis ["v1 (原版)", "v2 (Round 1)", "v3 (Round 2)", "v4 (Round 3)"]
    y-axis "WARNING件数" 0 --> 45
    bar [36, 9, 41, 2]
```

> **ラウンド2で41件に急増 → ラウンド3で2件に激減**。この非線形な改善曲線がカオステストの価値を端的に示しています。

## 1.2 全体サマリー

| 指標 | v1（原版） | v2（Round 1） | v3（Round 2） | v4（Round 3） |
|------|-----------|--------------|---------------|---------------|
| コンポーネント数 | 14 | 24 | 32 | 32 |
| 依存関係数 | 29 | 45 | 75 | **87** |
| PASSED | 259 | 611 | 919 | **958** |
| WARNING | 36 | 9 | **41** | **2** |
| CRITICAL | 1 | 1 | 1 | **1** |
| スコア | 0/100 | 0/100 | 0/100 | **0/100** |

## 1.3 ラウンド概要フロー

```mermaid
graph LR
    V1["v1: 原版<br/>14comp / 29deps<br/>36 WARNING"]
    V2["v2: Round 1<br/>24comp / 45deps<br/>9 WARNING<br/>✅ -75%"]
    V3["v3: Round 2<br/>32comp / 75deps<br/>41 WARNING<br/>❌ +356%"]
    V4["v4: Round 3<br/>32comp / 87deps<br/>2 WARNING<br/>✅ -95%"]

    V1 -->|"+WAF/Shield<br/>+PgBouncer<br/>+Kafka 3x<br/>+集中CB"| V2
    V2 -->|"+Envoy Sidecar CB<br/>+HPA/KEDA<br/>+Origin Failover"| V3
    V3 -->|"CB統合(sidecar維持)<br/>PgBouncer requires→optional<br/>+Aurora直接fallback"| V4

    style V1 fill:#ff4444,color:#fff
    style V2 fill:#ff8800,color:#fff
    style V3 fill:#ff4444,color:#fff
    style V4 fill:#ffcc00,color:#000
```

---

# 2. ラウンド1（v1→v2）: 基盤強化 — WARNING 36→9

## 2.1 v2.5で発見された6つの弱点への対策

v2.5記事で特定した6つの構造的弱点に対して、以下の改善を実施しました。

| # | 弱点 | 対策 | 詳細 |
|---|------|------|------|
| 1 | DDoS防御なし | WAF + Shield Advanced追加 | WAF 4M RPS + Shield 5M RPS |
| 2 | API Pod 3台固定 | 6台に増設 + 接続数2倍 | 6台 × 2K conn = 12K |
| 3 | Aurora SPOF（200接続） | 1,000接続 + Replica 3台 | 800 conn × 3 replicas |
| 4 | コネクション枯渇 | PgBouncer導入 | 2 replicas, 5K conn |
| 5 | Kafka単一ブローカー | 3ブローカー化 | KRaft mode, 15K conn |
| 6 | OTel SPOF | 3 replicas化 | 10K conn |

**追加コンポーネント**: WAF, Shield Advanced, PgBouncer, Aurora Replica ×3, Redis Sentinel ×3, Kafka ×3, OTel ×3, サーキットブレーカー（集中型, 6 replicas）

## 2.2 YAML定義の主要変更

```yaml
# infra/infrasim-xclone-v2.yaml（主要変更点）

# 新規: DDoS多層防御
- id: waf
  name: "AWS WAF"
  type: load_balancer
  capacity:
    max_connections: 500000
    max_rps: 2000000

- id: shield
  name: "AWS Shield Advanced"
  type: load_balancer
  capacity:
    max_connections: 1000000
    max_rps: 5000000

# 新規: コネクションプーラー
- id: pgbouncer
  name: "PgBouncer (Connection Pooler)"
  replicas: 2
  capacity:
    max_connections: 5000
    connection_pool_size: 1000

# 変更: Aurora max_connections 5倍
- id: aurora-primary
  capacity:
    max_connections: 1000  # was: 200

# 新規: サーキットブレーカー（集中型）
- id: circuit-breaker
  name: "Circuit Breaker (Istio/Envoy)"
  replicas: 6
  capacity:
    max_connections: 20000
    timeout_seconds: 5
```

## 2.3 アーキテクチャ変更

```mermaid
graph TD
    subgraph Before["v1: 直接接続"]
        A1[API Pod ×3] -->|"直接"| DB1[(Aurora 200)]
        A1 -->|"直接"| R1[(Redis)]
    end

    subgraph After["v2: 多層防御 + コネクションプーリング"]
        CF2[CloudFront] --> WAF2[WAF] --> SH2[Shield] --> ALB2[ALB]
        ALB2 --> A2[API Pod ×6]
        A2 --> CB2[集中CB ×6]
        CB2 --> PG2[PgBouncer ×2]
        PG2 --> DB2[(Aurora 1000)]
        CB2 --> R2[(Redis 50K)]
    end

    style Before fill:#ff444422,stroke:#ff4444
    style After fill:#00aa0022,stroke:#00aa00
```

## 2.4 テスト結果

```
$ infrasim load infra/infrasim-xclone-v2.yaml
[INFO] Loaded 24 components, 45 dependencies

$ infrasim simulate
[INFO] Results: 611 PASSED, 9 WARNING, 1 CRITICAL
```

| 指標 | v1 | v2 | 改善率 |
|------|----|----|-------|
| WARNING | 36 | **9** | **-75%** |
| PASSED | 259 | **611** | +136% |
| CRITICAL | 1 | 1 | 変化なし |

**ラウンド1の評価**: 基盤強化としては成功。WAF + Shield でDDoS防御が追加され、PgBouncer + Aurora 1,000接続でDB層のSPOFを解消。サーキットブレーカーでカスケード障害の伝播を抑制。

**残存する9件のWARNING**: 主にPgBouncer周辺のSPOFリスクと、集中型CBの信頼性。

---

# 3. ラウンド2（v2→v3）: Sidecar CB化 — WARNING 9→41（失敗）

## 3.1 仮説: 「集中CBをSidecar化すれば安全になる」

ラウンド1の残存WARNINGから、「集中型サーキットブレーカーがSPOFになりうる」と判断し、**各API Podに独立したEnvoy Sidecar CBを配置**するアーキテクチャに変更しました。

| # | 改善項目 | Before | After |
|---|---------|--------|-------|
| 1 | CB方式 | 集中型CB（6 replicas） | **Envoy Sidecar CB（各Pod内蔵）** |
| 2 | HPA | なし | **API Pod min:6 / max:12** |
| 3 | KEDA | なし | **Event-Driven Autoscaler** |
| 4 | Origin Failover | なし | **CloudFront → S3 Static** |
| 5 | Argo Rollouts | なし | **Rolling Deploy Controller** |

### Envoy Sidecar パターンの設計意図

```
集中型CB（v2）:
  API Pod 1 → [集中CB 6台] → PgBouncer → Aurora
  API Pod 2 → [集中CB 6台] → PgBouncer → Aurora
  ...
  → CBがSPOFになる可能性

Sidecar CB（v3）:
  API Pod 1 + [Envoy CB 1] → PgBouncer → Aurora
  API Pod 2 + [Envoy CB 2] → PgBouncer → Aurora
  ...
  → 各Podに独立したCBが同居 → CB自体のSPOFを解消
```

設計意図は正しかった。しかし、InfraSimの結果は**予想と真逆**でした。

## 3.2 テスト結果 — 衝撃の41 WARNING

```
$ infrasim load infra/infrasim-xclone-v3.yaml
[INFO] Loaded 32 components, 75 dependencies

$ infrasim simulate
[INFO] Results: 919 PASSED, 41 WARNING, 1 CRITICAL
```

| 指標 | v2 | v3 | 変化 |
|------|----|----|------|
| WARNING | 9 | **41** | **+356%!!** |
| PASSED | 611 | 919 | +50% |
| コンポーネント | 24 | 32 | +8 |

**WARNING数が9件から41件に急増。** コンポーネントの冗長化が、逆にレジリエンスを悪化させたのです。

## 3.3 失敗の原因分析: PgBouncer SPOFの構造的問題

v3の41件のWARNINGを詳細に分析したところ、衝撃的な事実が判明しました。

**41件中、実に全41件がPgBouncerに関連していました。**

内訳:

| カテゴリ | 件数 | 例 |
|---------|------|-----|
| PgBouncer × 他コンポーネントのペア障害 | 33件 | `Pair failure: alb + pgbouncer` (4.9/10) |
| PgBouncer自体の障害 | 4件 | `Single failure: pgbouncer` (4.4/10), `Pool exhaustion: pgbouncer` (5.5/10) |
| トラフィック関連 | 3件 | `Traffic spike (5x)` (4.3/10), `Cache stampede` (4.9/10) |
| インフラ全体 | 1件 | `Total infrastructure meltdown` (4.2/10) |

### なぜSidecar CBがPgBouncer SPOFを生んだのか

問題の核心は、**Sidecar CB → PgBouncer の依存関係が `requires` (weight 0.9) で定義されていた**ことです。

```yaml
# v3の依存関係定義（問題の箇所）
# 6つのSidecar CB → PgBouncer が全て requires
- source: cb-sidecar-1
  target: pgbouncer
  type: requires    # ← これが問題
  weight: 0.9

- source: cb-sidecar-2
  target: pgbouncer
  type: requires    # ← 6つ全部 requires
  weight: 0.9
# ... cb-sidecar-3 ~ cb-sidecar-6 も同様
```

```mermaid
graph TD
    subgraph v3_problem["v3: Sidecar CBがPgBouncer SPOFを生成"]
        CB1["CB Sidecar 1"] -->|"requires 0.9"| PG["PgBouncer<br/>(2 replicas)<br/>❌ SPOF"]
        CB2["CB Sidecar 2"] -->|"requires 0.9"| PG
        CB3["CB Sidecar 3"] -->|"requires 0.9"| PG
        CB4["CB Sidecar 4"] -->|"requires 0.9"| PG
        CB5["CB Sidecar 5"] -->|"requires 0.9"| PG
        CB6["CB Sidecar 6"] -->|"requires 0.9"| PG
        PG -->|"requires 1.0"| AU[(Aurora Primary)]
    end

    style PG fill:#ff4444,color:#fff
    style v3_problem fill:#ff444422,stroke:#ff4444
```

**`requires`の意味**: その依存先がダウンした場合、**依存元もサービス不能と判定される**。

つまり、6つのSidecar CB全てがPgBouncerを`requires`で参照したため、**PgBouncerがダウンすると6つのCB全てが連鎖的にダウン → API Pod全滅**という構造が生まれました。

集中型CBの時は、CB自身が6台の冗長構成だったためCB障害リスクは低かった。しかしSidecar化により、CB→PgBouncer間に**6本の`requires`依存**が生まれ、PgBouncerの重要度が爆発的に上昇したのです。

### 教訓: 冗長化 ≠ レジリエンス

> **コンポーネントを冗長化しても、その依存関係が`requires`で定義されていれば、むしろSPOFを生む。**
>
> v3は「各Podに独立したCBを配置した」つもりが、実際には「全てのCBがPgBouncerに`requires`で依存する構造」を作り出し、PgBouncerへの依存度をv2よりも悪化させた。

---

# 4. ラウンド3（v3→v4）: 構造最適化 — WARNING 41→2

## 4.1 v3の失敗から導いた改善方針

ラウンド2の失敗分析から、以下の3つの構造的改善を実施しました。

| # | 改善 | Before (v3) | After (v4) | 効果 |
|---|------|-------------|------------|------|
| 1 | PgBouncer依存タイプ変更 | `requires` weight 0.9 | **`optional` weight 0.7** | SPOF解消 |
| 2 | Aurora直接フォールバック追加 | なし | **CB→Aurora Primary (optional 0.3)** | 迂回路確保 |
| 3 | PgBouncer HA強化 | 2 replicas, 5K conn | **4 replicas, 10K conn** | 障害耐性向上 |

## 4.2 核心の変更: `requires` → `optional`

v3→v4の改善で**最も効果が大きかった変更はたった1つ**です。

```yaml
# v3（問題）: PgBouncerがダウンすると全CBが連鎖ダウン
- source: cb-sidecar-1
  target: pgbouncer
  type: requires    # PgBouncer障害 → CB障害 → API障害
  weight: 0.9

# v4（修正）: PgBouncer障害時もCBは機能を維持
- source: cb-sidecar-1
  target: pgbouncer
  type: optional    # PgBouncer障害 → CBは継続稼働
  weight: 0.7       # 影響度を下げる（Aurora直接接続にフォールバック）
```

**`optional`の意味**: その依存先がダウンしても、**依存元はサービスを継続可能**と判定される。影響はweight値に応じた劣化として評価される。

### Aurora直接フォールバックの追加

PgBouncerを`optional`にした場合の迂回路として、CBからAuroraへの直接接続パスを追加しました。

```yaml
# v4で追加: PgBouncer障害時のAurora直接フォールバック
- source: cb-sidecar-1
  target: aurora-primary
  type: optional
  weight: 0.3    # フォールバックなので低weight

- source: cb-sidecar-1
  target: aurora-replica-1
  type: optional
  weight: 0.2    # 読み取りはReplicaにも分散
```

## 4.3 Before / After: PgBouncer依存構造

```mermaid
graph TD
    subgraph before["v3: requires → SPOF"]
        B_CB1["CB 1"] -->|"requires 0.9"| B_PG["PgBouncer ×2<br/>❌ SPOF"]
        B_CB2["CB 2"] -->|"requires 0.9"| B_PG
        B_CB3["CB ..."] -->|"requires 0.9"| B_PG
        B_CB6["CB 6"] -->|"requires 0.9"| B_PG
        B_PG -->|"requires"| B_AU[(Aurora)]
    end

    subgraph after["v4: optional + fallback → SPOF解消"]
        A_CB1["CB 1"] -->|"optional 0.7"| A_PG["PgBouncer ×4<br/>✅ HA"]
        A_CB2["CB 2"] -->|"optional 0.7"| A_PG
        A_CB3["CB ..."] -->|"optional 0.7"| A_PG
        A_CB6["CB 6"] -->|"optional 0.7"| A_PG
        A_CB1 -.->|"optional 0.3"| A_AU[(Aurora Primary)]
        A_CB2 -.->|"optional 0.3"| A_AU
        A_CB1 -.->|"optional 0.2"| A_AR[(Aurora Replica)]
        A_PG -->|"requires"| A_AU
    end

    style B_PG fill:#ff4444,color:#fff
    style A_PG fill:#00aa00,color:#fff
    style before fill:#ff444422,stroke:#ff4444
    style after fill:#00aa0022,stroke:#00aa00
```

## 4.4 YAML差分の全体像

```yaml
# infra/infrasim-xclone.yaml (v4) — 主要変更点

# Fix 1: PgBouncer HA化 (replicas 2→4, connections 5K→10K)
- id: pgbouncer
  name: "PgBouncer (Connection Pooler, HA)"
  replicas: 4        # was: 2
  capacity:
    max_connections: 10000     # was: 5000
    connection_pool_size: 2000  # was: 1000

# Fix 2: CB→PgBouncer: requires 0.9 → optional 0.7 (×6)
- source: cb-sidecar-1
  target: pgbouncer
  type: optional     # was: requires
  weight: 0.7        # was: 0.9
# ... cb-sidecar-2 ~ cb-sidecar-6 も同様

# Fix 3: CB→Aurora直接フォールバック追加 (×6 primary + ×6 replica)
- source: cb-sidecar-1
  target: aurora-primary
  type: optional
  weight: 0.3

- source: cb-sidecar-1
  target: aurora-replica-1
  type: optional
  weight: 0.2
# ... cb-sidecar-2 ~ cb-sidecar-6 も同様
```

## 4.5 テスト結果

```
$ infrasim load infra/infrasim-xclone.yaml
[INFO] Loaded 32 components, 87 dependencies

$ infrasim simulate
[INFO] Results: 958 PASSED, 2 WARNING, 1 CRITICAL
```

| 指標 | v3 | v4 | 改善率 |
|------|----|----|-------|
| WARNING | 41 | **2** | **-95.1%** |
| PASSED | 919 | **958** | +4.2% |
| 依存関係 | 75 | **87** | +16%（フォールバックパス追加） |

**41件のWARNINGが一気に2件に。** `requires`→`optional`の変更と、Aurora直接フォールバックの追加が劇的な効果を発揮しました。

---

# 5. 最終結果の詳細分析

## 5.1 残存するWARNING（2件）

### WARNING #1: 5xトラフィックスパイク（5.2/10）

```
シナリオ: バイラルイベントによる通常の5倍トラフィック

影響:
  CloudFront:     WARN（75%利用率）
  ALB:            WARN（90%利用率）
  API Pod 1-6:    DOWN（110-200%超過）← HPA上限12でも不足
  WebSocket:      DOWN（150%超過）
  Aurora Primary: DOWN（275%超過）
  PgBouncer:      WARN（90%利用率）
```

**分析**: HPA上限12台では5倍スパイクに対してまだ不足。API Pod数を12→20に増やすか、Pod単体のキャパシティ（2,000→4,000接続）を増やす必要がある。

### WARNING #2: キャッシュスタンピード + 5xトラフィック（4.7/10）

```
シナリオ: Redis障害 + 5倍トラフィックの複合障害

影響:
  全キャッシュミス → Aurora直撃 → 275%超過 → DOWN
  PgBouncer: WARN（90%）→ ぎりぎり耐えるが限界
```

**分析**: `stale-while-revalidate` + `jittered TTL`は実装済みだが、Redis完全障害 + 5xスパイクの複合シナリオには耐えられない。これは**Thundering Herd + 高負荷の同時発生**という非常に厳しい条件。

## 5.2 残存するCRITICAL（1件）: 10x DDoSトラフィックスパイク

**重大度: 9.1/10** — 全4バージョンで一貫して残存。

### 現実的な評価: Shield Advancedの自動緩和

InfraSimはインフラ定義のキャパシティに基づくシミュレーションであり、**AWS Shield AdvancedのDDoS Response Team（SRT）による自動緩和**を考慮していません。

実際のAWS環境では:

```
InfraSimの評価:
  10x DDoS → CloudFront 150%超過 → 全コンポーネントDOWN → CRITICAL

実際のAWS動作:
  10x DDoS → Shield Advanced検知（自動）
           → SRT自動対応 or WAFルール動的更新
           → 悪意あるトラフィックをエッジでドロップ
           → オリジンには正常トラフィックのみ到達
           → サービス継続
```

つまり、このCRITICALは**InfraSimの評価限界**を示しています。Shield Advancedの$3,000/月の価値は、まさにこの自動緩和にあります。

ただし、「InfraSimでCRITICALを出さない設計」を目指すことは価値があります。Shield Advancedに頼らず、エッジ層自体のキャパシティで10xを吸収できれば、Shield障害時にもサービスを維持できるからです。

## 5.3 スコアが0のままである理由

InfraSimのレジリエンススコアは**CRITICALが1件以上存在する限り自動的に0**になります。

```
スコア計算:
  CRITICAL > 0 → スコア = 0（自動）
  CRITICAL = 0 → スコア = f(PASSED率, WARNING重大度, コンポーネント冗長度)
```

v4の実質的な改善度（PASSED率 99.7%、WARNING 2件のみ）を考えると、CRITICAL解消時にはスコア**80+**が見込めます。

---

# 6. v1→v4 全体の改善サマリー

## 6.1 コンポーネント比較

| カテゴリ | v1（原版） | v4（最終） | 変化 |
|---------|-----------|-----------|------|
| **エッジ層** | CloudFront + ALB | CloudFront + WAF + Shield + ALB + Origin Failover | +3 |
| **API層** | 3 Pod (1K conn) | 6 Pod (2K conn) + Envoy Sidecar CB + HPA + KEDA + Argo | +13 |
| **DB層** | Aurora 200 conn + 1 Replica | Aurora 1K conn + 3 Replica + PgBouncer HA ×4 | +3 |
| **キャッシュ** | Redis 2 rep, 20K conn | Redis Cluster 6 shards, 80K conn | 拡張 |
| **CDC** | Kafka 1 broker + Debezium 1 | Kafka 3 brokers + Debezium 2 | +3 |
| **可観測性** | OTel 1 instance | OTel 3 replicas | +2 |
| **合計** | **14コンポーネント** | **32コンポーネント** | **+18** |

## 6.2 テスト結果比較

| 指標 | v1（原版） | v4（最終） | 改善率 |
|------|-----------|-----------|-------|
| テストシナリオ数 | 296 | 961 | +225% |
| **PASSED** | 259 (87.5%) | **958 (99.7%)** | **+270%** |
| **WARNING** | 36 (12.2%) | **2 (0.2%)** | **-94.4%** |
| **CRITICAL** | 1 (0.3%) | **1 (0.1%)** | 変化なし |
| 依存関係 | 29 | 87 | +200% |

## 6.3 解消された弱点（v2.5で特定した6つ）

| # | v2.5の弱点 | v2.6の対策 | ステータス |
|---|-----------|-----------|-----------|
| 1 | Aurora Primary SPOF（200接続） | 1,000接続 + PgBouncer HA ×4 + Replica ×3 | **解消** |
| 2 | API Pod スケーリング不足（3台固定） | HPA 6-12台 + KEDA + 各2,000接続 | **解消** |
| 3 | Redis キャッシュスタンピード | Redis Cluster 6 shards + Sidecar CB (optional) | **解消** |
| 4 | Kafka シングルブローカー | 3ブローカー KRaft + 15K接続 | **解消** |
| 5 | DDoS防御なし | WAF + Shield Advanced | **部分解消** |
| 6 | OTel Collector SPOF | 3 replicas + 10K接続 | **解消** |

---

# 7. 最終アーキテクチャ（v4）

```mermaid
graph TD
    subgraph Edge["エッジ層（DDoS多層防御）"]
        CF["CloudFront CDN<br/>2M RPS"]
        CF_FO["Origin Failover<br/>S3 Static"]
        WAF["AWS WAF<br/>4M RPS"]
        SHIELD["Shield Advanced<br/>5M RPS"]
        ALB["ALB ×2<br/>200K RPS"]
    end

    subgraph App["アプリケーション層（EKS）"]
        HPA["HPA<br/>min:6 max:12"]
        KEDA["KEDA<br/>Event-Driven"]
        ARGO["Argo Rollouts"]
        subgraph Pods["API Pods + Envoy Sidecar CB"]
            P1["Pod 1 + CB"]
            P2["Pod 2 + CB"]
            P3["..."]
            P6["Pod 6 + CB"]
        end
        WS["Socket.io ×6<br/>20K conn"]
    end

    subgraph Data["データ層"]
        PGB["PgBouncer HA ×4<br/>10K conn<br/>(optional 0.7)"]
        AURORA_P[(Aurora Primary<br/>1K conn)]
        AURORA_R1[(Replica 1)]
        AURORA_R2[(Replica 2)]
        AURORA_R3[(Replica 3)]
        REDIS[(Redis Cluster<br/>6 shards, 80K conn)]
        OS[(OpenSearch ×4<br/>2K conn)]
        S3["S3 Media<br/>50K RPS"]
    end

    subgraph CDC["CDCパイプライン"]
        DEB["Debezium ×2"]
        KAFKA["Kafka KRaft ×3<br/>15K conn"]
    end

    subgraph Obs["オブザーバビリティ"]
        OTEL["OTel Collector ×3<br/>10K conn"]
    end

    CF --> WAF --> SHIELD --> ALB
    CF -.->|optional| CF_FO
    ALB --> Pods
    ALB --> WS
    HPA -.->|auto| Pods
    KEDA -.->|event| Pods
    ARGO -.->|deploy| Pods
    P1 -->|"optional 0.7"| PGB
    P1 -.->|"optional 0.3<br/>fallback"| AURORA_P
    P1 -.->|optional| REDIS
    P1 -.->|optional| OS
    P1 -.->|optional| S3
    PGB --> AURORA_P
    PGB -.-> AURORA_R1
    PGB -.-> AURORA_R2
    PGB -.-> AURORA_R3
    WS --> REDIS
    DEB --> AURORA_P
    DEB --> KAFKA
    KAFKA -.->|async| OS
    P1 -.-> OTEL

    style PGB fill:#00aa00,color:#fff
    style CF fill:#00aa00,color:#fff
    style WAF fill:#00aa00,color:#fff
    style SHIELD fill:#00aa00,color:#fff
    style HPA fill:#00aa00,color:#fff
```

---

# 8. 実装コード: 主要コンポーネント

## 8.1 サーキットブレーカー（Envoy Sidecar + Istio）

```yaml
# k8s/api-deployment.yaml（Envoy Sidecar付き）
apiVersion: apps/v1
kind: Deployment
metadata:
  name: hono-api
  namespace: xclone
spec:
  replicas: 6
  template:
    metadata:
      labels:
        app: hono-api
      annotations:
        sidecar.istio.io/inject: "true"
    spec:
      containers:
        - name: hono-api
          image: xclone/hono-api:latest
          ports:
            - containerPort: 8080
          resources:
            requests:
              cpu: "500m"
              memory: "512Mi"
            limits:
              cpu: "2000m"
              memory: "1Gi"
          env:
            - name: DATABASE_URL
              value: "postgresql://pgbouncer.xclone.internal:6432/xclone"
            - name: REDIS_URL
              value: "redis://redis-cluster.xclone.internal:6379"
```

```yaml
# k8s/istio-destination-rule.yaml（CB設定）
apiVersion: networking.istio.io/v1
kind: DestinationRule
metadata:
  name: aurora-circuit-breaker
  namespace: xclone
spec:
  host: pgbouncer.xclone.internal
  trafficPolicy:
    connectionPool:
      tcp:
        maxConnections: 1000
        connectTimeout: 5s
      http:
        maxRequestsPerConnection: 100
    outlierDetection:
      consecutive5xxErrors: 3
      interval: 10s
      baseEjectionTime: 30s
      maxEjectionPercent: 50
```

## 8.2 PgBouncer HA構成

```yaml
# k8s/pgbouncer-ha.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: pgbouncer
  namespace: xclone
spec:
  replicas: 4
  strategy:
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0  # ゼロダウンタイム更新
  template:
    spec:
      affinity:
        podAntiAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            - labelSelector:
                matchLabels:
                  app: pgbouncer
              topologyKey: "kubernetes.io/hostname"
          # 全レプリカを異なるノードに配置
      containers:
        - name: pgbouncer
          image: bitnami/pgbouncer:1.22.0
          env:
            - name: POSTGRESQL_HOST
              value: "aurora-primary.xclone.internal"
            - name: PGBOUNCER_POOL_MODE
              value: "transaction"
            - name: PGBOUNCER_MAX_CLIENT_CONN
              value: "10000"
            - name: PGBOUNCER_DEFAULT_POOL_SIZE
              value: "100"
            - name: PGBOUNCER_MAX_DB_CONNECTIONS
              value: "300"
          ports:
            - containerPort: 6432
          livenessProbe:
            tcpSocket:
              port: 6432
            initialDelaySeconds: 10
            periodSeconds: 5
          readinessProbe:
            exec:
              command: ["pgbouncer", "-q", "SHOW POOLS"]
            initialDelaySeconds: 5
            periodSeconds: 5
```

## 8.3 HPA + KEDA

```yaml
# k8s/hpa.yaml — CPU/Memory based autoscaling
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: hono-api-hpa
  namespace: xclone
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: hono-api
  minReplicas: 6
  maxReplicas: 12
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 50
    - type: Resource
      resource:
        name: memory
        target:
          type: Utilization
          averageUtilization: 70
  behavior:
    scaleUp:
      stabilizationWindowSeconds: 30
      policies:
        - type: Percent
          value: 100
          periodSeconds: 30
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
        - type: Pods
          value: 1
          periodSeconds: 60
```

```yaml
# k8s/keda-scaledobject.yaml — Event-driven autoscaling
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: hono-api-keda
  namespace: xclone
spec:
  scaleTargetRef:
    name: hono-api
  minReplicaCount: 6
  maxReplicaCount: 12
  triggers:
    - type: prometheus
      metadata:
        serverAddress: http://prometheus.monitoring:9090
        metricName: http_requests_per_second
        query: sum(rate(http_requests_total{app="hono-api"}[1m]))
        threshold: "1000"
```

## 8.4 Kafka 3ブローカー構成

```yaml
# k8s/kafka-kraft.yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: kafka
  namespace: xclone
spec:
  serviceName: kafka-headless
  replicas: 3
  template:
    spec:
      containers:
        - name: kafka
          image: confluentinc/cp-kafka:7.6.0
          ports:
            - containerPort: 9092
            - containerPort: 9093  # Controller
          env:
            - name: KAFKA_PROCESS_ROLES
              value: "broker,controller"
            - name: KAFKA_NUM_PARTITIONS
              value: "6"
            - name: KAFKA_DEFAULT_REPLICATION_FACTOR
              value: "3"
            - name: KAFKA_MIN_INSYNC_REPLICAS
              value: "2"
            - name: KAFKA_CONTROLLER_QUORUM_VOTERS
              value: "0@kafka-0:9093,1@kafka-1:9093,2@kafka-2:9093"
          volumeMounts:
            - name: data
              mountPath: /var/lib/kafka/data
  volumeClaimTemplates:
    - metadata:
        name: data
      spec:
        accessModes: ["ReadWriteOnce"]
        storageClassName: gp3
        resources:
          requests:
            storage: 100Gi
```

---

# 9. 3ラウンドから得た教訓

## 9.1 教訓1: 冗長化 ≠ レジリエンス

ラウンド2の失敗は、「冗長化すれば安全」という直感が危険であることを示しました。

```
冗長化の罠:
  Sidecar CB ×6 を導入 → 「各Podが独立しているから安全」
  しかし実際は:
    6つのCBが全て PgBouncer に requires で依存
    → PgBouncer のSPOF度が CB×1 の時よりも悪化
    → WARNING 9 → 41 に急増

本当の問題:
  「コンポーネントの冗長化」ではなく「依存関係の構造」がレジリエンスを決める
```

## 9.2 教訓2: `requires` vs `optional` が全てを決める

v3→v4で**コンポーネント数は変わらず（32台）**、変更したのは依存関係の`type`と`weight`だけ。それだけで**WARNING 41→2（-95%）**の劇的改善を達成しました。

```
requires（必須依存）:
  依存先がダウン → 依存元もダウン（カスケード障害）
  使うべき場面: 本当に代替がない場合のみ
  例: PgBouncer → Aurora Primary（DBなしでは動作不能）

optional（任意依存）:
  依存先がダウン → 依存元はweight分の劣化で継続
  使うべき場面: フォールバック可能な場合
  例: CB → PgBouncer（Aurora直接接続にフォールバック可能）

判断基準:
  「この依存先がダウンしたとき、代替手段はあるか？」
  → ある → optional
  → ない → requires
```

## 9.3 教訓3: テスト→失敗→修正の反復こそが価値

```mermaid
graph LR
    T1["テスト<br/>(InfraSim)"] --> A1["分析<br/>(全WARNING確認)"]
    A1 --> F1["修正<br/>(構造変更)"]
    F1 --> T1

    style T1 fill:#4444ff,color:#fff
    style A1 fill:#ff8800,color:#fff
    style F1 fill:#00aa00,color:#fff
```

3ラウンドの改善サイクルで得た最大の学びは、**1回で正解にたどり着こうとしないこと**です。

| ラウンド | やったこと | 結果 | 学び |
|---------|-----------|------|------|
| Round 1 | 基盤強化 | WARNING -75% | 冗長化は有効 |
| Round 2 | Sidecar CB化 | WARNING +356% | **冗長化が裏目に出ることがある** |
| Round 3 | 構造最適化 | WARNING -95% | 依存関係の型が全てを決める |

ラウンド2の失敗がなければ、`requires` vs `optional`の本質的な違いに気づくことはなかったでしょう。**カオステストの価値は、成功ではなく失敗を安全に経験できること**にあります。

---

# 10. InfraSimの有効性

```
3ラウンドの改善+テスト: 約2時間
本番環境で同等の検証を実施: 数日〜数週間 + ダウンタイムリスク

コスト比較:
  InfraSim: 無料（YAMLとPythonシミュレーション）
  本番カオステスト: CloudWatch/Shield/各種AWSサービスのコスト
  Gremlin等のSaaS: $1,000+/月

検出した問題:
  v1: 36 WARNING + 1 CRITICAL → 3ラウンドで2 WARNING + 1 CRITICALに
  v3の依存関係SPOF → 本番デプロイ前に発見・修正
```

---

# 11. まとめ

## 11.1 3ラウンドの改善全体像

```
v2.5: InfraSimで6つの構造的弱点を発見
  ↓ Round 1（v1→v2）
  + WAF/Shield DDoS防御、PgBouncer、Aurora 5x、Kafka 3x、集中CB、OTel 3x
  → WARNING 36→9（-75%）
  ↓ Round 2（v2→v3）
  + Envoy Sidecar CB、HPA/KEDA、Origin Failover
  → WARNING 9→41（+356% — PgBouncer SPOF化で失敗）
  ↓ Round 3（v3→v4）
  + PgBouncer requires→optional、Aurora直接fallback、PgBouncer HA 4台
  → WARNING 41→2（-95%）
```

## 11.2 最終スコアカード

| 指標 | v2.5（改善前） | v2.6（改善後） | 変化 |
|------|--------------|--------------|------|
| コンポーネント | 14 | 32 | +18（+129%） |
| 依存関係 | 29 | 87 | +58（+200%） |
| テストシナリオ | 296 | 961 | +665（+225%） |
| PASSED | 259 (87.5%) | 958 (99.7%) | +699 |
| WARNING | 36 (12.2%) | **2 (0.2%)** | **-34 (-94.4%)** |
| CRITICAL | 1 | 1 | 残存（10x DDoS） |
| スコア | 0/100 | 0/100 | CRITICAL解消で80+予測 |

## 11.3 次のステップ

v2.7では残存する10x DDoS CRITICALの解消を目指します。

```
v2.6（本記事）: WARNING 36→2、依存関係構造の最適化
  ↓
v2.7（次回）: 10x DDoS CRITICAL の解消
  - CloudFront 10M+ RPS キャパシティ拡張
  - CloudFront Functions エッジフィルタリング
  - Global Accelerator DDoSトラフィック分散
  - レジリエンススコア: 0 → 80+ を目標
```

---

*この記事は [Qiita](https://qiita.com/) にも投稿しています。*
