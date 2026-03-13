---
title: "InfraSim v4.6 — 依存関係トポロジーを考慮した可用性計算"
emoji: "🔗"
type: "tech"
topics: ["InfraSim", "infrastructure", "simulation", "SRE"]
published: false
---

## はじめに

前回の[v2.17記事](https://zenn.dev/ymaeda/articles/xclone-v2-17-downtime-precision-traffic)では、**InfraSim v4.5**でダウンタイム精度向上（fault-overlap計算）とトラフィックモデル修正（base_multiplier導入）を実施しました。

v4.5までのInfraSimは各コンポーネントの健全性を**独立に**評価していました。PostgreSQLがDOWNでもApp Serverは「自分自身は正常」として扱われ、可用性は実態より高く算出されていたのです。

v4.6はInfraSimの最も根本的な改善です。**依存関係グラフ（トポロジー）を考慮した可用性計算**を導入し、PostgreSQL障害がApp Server→Load Balancerへと連鎖的に伝播する現実のインフラ挙動をシミュレーションに反映できるようにしました。

### シリーズ記事

| # | 記事 | テーマ |
|---|------|--------|
| 16 | [**v2.15** -- 利用率計算統一 & 5バグ修正](https://zenn.dev/ymaeda/articles/xclone-v2-15-utilization-consistency) | InfraSim v4.3 / max統一 / 加重ダウンタイム / RNG汚染修正 |
| 17 | [**v2.16** -- MTTR感度分析 & リスクベースError Budget](https://zenn.dev/ymaeda/articles/xclone-v2-16-mttr-sensitivity-burnrate) | InfraSim v4.4 / MTBFキャップ / burn rate推定 / CLI強化 |
| 18 | [**v2.17** -- ダウンタイム精度向上 & トラフィックモデル修正](https://zenn.dev/ymaeda/articles/xclone-v2-17-downtime-precision-traffic) | InfraSim v4.5 / fault-overlap / MTBFキャップ緩和 / base_multiplier |
| **19** | **v2.18 -- 依存関係トポロジーを考慮した可用性計算（本記事）** | **InfraSim v4.6 / 固定点反復 / 依存伝播 / ローリングアップデート** |

### InfraSimバージョンの進化（抜粋）

```
v4.3 (v2.15): 利用率計算統一 & バグ修正
v4.4 (v2.16): MTTR感度分析 & リスクベースError Budget
v4.5 (v2.17): ダウンタイム精度向上 & トラフィックモデル修正

v4.6 (v2.18, 本記事): 依存関係トポロジーを考慮した可用性計算  <-- NEW
  ├ 依存伝播アルゴリズム: 固定点反復で依存先の障害を依存元に伝播
  ├ 3タイプの依存関係: requires / optional / async
  ├ ローリングアップデート: replicas > 1 のメンテナンス → DEGRADED
  └ カスケード爆発の防止: 計画的メンテナンス時の誤カスケードを抑制
```

## 問題: 独立計算の限界

v4.5までの可用性計算は `availability = (total - down) / total * 100` というシンプルなものでした。6コンポーネントのインフラでPostgreSQLがDOWNの場合、`(6 - 1) / 6 = 83.3%`。一見正しく見えますが、**現実のインフラでは83.3%にはなりません**。

### 現実のカスケード

```
依存関係グラフ:

nginx ──requires──→ app-1 ──requires──→ postgres
  │                   ├──optional──→ redis
  │                   └──async────→ rabbitmq
  │
  └──requires──→ app-2 ──requires──→ postgres
                   ├──optional──→ redis
                   └──async────→ rabbitmq
```

PostgreSQLがDOWN → app-1もapp-2も**データベースにアクセスできない** → nginxは**ルーティング先が全滅** → 実質的に4コンポーネントがDOWNです。

```
現実: availability = (6 - 4) / 6 * 100 = 33.3%
v4.5: availability = (6 - 1) / 6 * 100 = 83.3%  ← 2.5倍の過大評価
```

共有バックエンド（DB）がSPOFとして持つ**トポロジー上のリスク**が、数値に一切反映されていませんでした。

### 依存関係の3タイプ

| タイプ | 意味 | 伝播ルール | 例 |
|--------|------|-----------|-----|
| `requires` | 必須依存 | 全requires先DOWN → 依存元もDOWN | app → postgres |
| `optional` | 任意依存 | DOWN → 依存元はDEGRADED | app → redis |
| `async` | 非同期依存 | 伝播なし | app → rabbitmq |

## 設計: 固定点反復による依存伝播アルゴリズム

### 入力・出力・伝播ルール

- **入力**: 各コンポーネントの実際のヘルスステータス + 依存グラフ
- **出力**: 各コンポーネントの実効的なヘルスステータス（**計算上のビュー**。実状態は変更しない）

```
伝播ルール:
1. requires先が全てDOWN    → 依存元もDOWN
2. requires先の一部DOWN    → 依存元はDEGRADED
3. requires先がOVERLOADED  → 依存元はDEGRADED
4. optional先がDOWN        → 依存元はDEGRADED
5. async先がDOWN           → 伝播なし
6. 既にDOWNのコンポーネント → スキップ（それ以上悪化しない）
```

### 固定点反復

依存関係にはチェーン（A→B→C）があるため、1回のスキャンでは全ての伝播を捕捉できません。

```
初回スキャン:
  postgres: DOWN（実障害）
  app-1: requires先(postgres)がDOWN → DOWNに変更 ✓
  nginx: requires先(app-1, app-2)を確認 → 処理順序により未更新の可能性

2回目スキャン:
  nginx: requires先(app-1=DOWN, app-2=DOWN)が全DOWN → DOWNに変更 ✓
  変化なし → 固定点到達 → 終了
```

### コード: `_propagate_dependencies`

```python
def _propagate_dependencies(self, comp_states):
    effective = {
        cid: state.current_health for cid, state in comp_states.items()
    }
    dep_edges = self.graph.all_dependency_edges()

    # Fixed-point iteration (max N+1 rounds for cycle protection)
    for _ in range(len(comp_states) + 1):
        changed = False
        for comp_id in comp_states:
            if effective[comp_id] == HealthStatus.DOWN:
                continue

            requires_targets = []
            has_optional_down = False
            for dep in dep_edges:
                if dep.source_id != comp_id:
                    continue
                target_health = effective.get(dep.target_id)
                if target_health is None:
                    continue
                if dep.dependency_type == "requires":
                    requires_targets.append(target_health)
                elif dep.dependency_type == "optional":
                    if target_health == HealthStatus.DOWN:
                        has_optional_down = True
                # async: no propagation

            if requires_targets:
                all_down = all(h == HealthStatus.DOWN for h in requires_targets)
                any_down = any(h == HealthStatus.DOWN for h in requires_targets)
                if all_down:
                    effective[comp_id] = HealthStatus.DOWN
                    changed = True
                elif any_down and effective[comp_id] == HealthStatus.HEALTHY:
                    effective[comp_id] = HealthStatus.DEGRADED
                    changed = True

            if has_optional_down and effective[comp_id] == HealthStatus.HEALTHY:
                effective[comp_id] = HealthStatus.DEGRADED
                changed = True

        if not changed:
            break
    return effective
```

設計のポイント:
- **`effective`は複製**: 実コンポーネント状態を変更しない（復旧時に即座に回復）
- **DOWN判定はスキップ**: 既にDOWNなら悪化しようがない
- **`changed`フラグ**: 変化がなければ固定点に到達しループを抜ける
- **サイクル保護**: `len(comp_states) + 1`が上限。循環依存でも無限ループしない

### 伝播結果の例

**PostgreSQLがDOWNの場合:**

| コンポーネント | 実際 | 伝播後 | 理由 |
|--------------|------|--------|------|
| postgres | DOWN | DOWN | 実障害 |
| redis | HEALTHY | HEALTHY | 影響なし |
| rabbitmq | HEALTHY | HEALTHY | 影響なし |
| app-1 | HEALTHY | **DOWN** | requires先(postgres)が全DOWN |
| app-2 | HEALTHY | **DOWN** | requires先(postgres)が全DOWN |
| nginx | HEALTHY | **DOWN** | requires先(app-1, app-2)が全DOWN |

可用性: `(6 - 4) / 6 = 33.3%`

**RedisがDOWNの場合:**

| コンポーネント | 実際 | 伝播後 | 理由 |
|--------------|------|--------|------|
| redis | DOWN | DOWN | 実障害 |
| app-1 | HEALTHY | **DEGRADED** | optional先(redis)がDOWN |
| app-2 | HEALTHY | **DEGRADED** | optional先(redis)がDOWN |
| nginx | HEALTHY | HEALTHY | requires先はDOWNでない |

可用性: `(6 - 1) / 6 = 83.3%` -- DEGRADEDはサービス稼働中のため可用性100%扱い。

**app-1のみDOWNの場合:**

| コンポーネント | 実際 | 伝播後 | 理由 |
|--------------|------|--------|------|
| app-1 | DOWN | DOWN | 実障害 |
| nginx | HEALTHY | **DEGRADED** | requires先の一部がDOWN |

可用性: `(6 - 1) / 6 = 83.3%` -- app-2経由でnginxはまだルーティング可能。

## 問題2: メンテナンス時のカスケード爆発

### 想定外の副作用

依存伝播を導入して最初にテストを実行したとき、**全what-ifシナリオがSLO未達**になりました。

v4.5ではメンテナンス中のコンポーネントは一律`DOWN`扱いでした。依存伝播がない時代はこれでも「1件のDOWN」でしたが、v4.6では:

```
postgres メンテナンス → DOWN
  → app-1, app-2: requires先が全DOWN → DOWN
  → nginx: requires先が全DOWN → DOWN
  → 可用性: 33.3%  ← メンテナンスのたびに発生
```

### 解法: ローリングアップデートの判定

現実のインフラでは、PostgreSQL（2レプリカ）のメンテナンスは**ローリングアップデート**で実施します。replica-1がリクエストを処理しつつreplica-2をメンテナンスし、完了後に交代。**サービス中断なし**です。

```python
if is_faulted:
    # Maintenance/deploy on multi-replica -> DEGRADED (rolling update)
    is_only_planned = all(
        ev.event_type in (
            OpsEventType.MAINTENANCE,
            OpsEventType.DEPLOY,
            OpsEventType.CERT_RENEWAL,
        )
        for ev in all_events_so_far
        if ev.target_component_id == comp_id
        and ev.time_seconds <= t < ev.time_seconds + ev.duration_seconds
    )
    if is_only_planned and comp.replicas > 1:
        state.current_health = HealthStatus.DEGRADED
        state.current_utilization = state.base_utilization * 1.5
    else:
        state.current_health = HealthStatus.DOWN
        state.current_utilization = 0.0
```

### 判定マトリクス

| イベントタイプ | replicas | 結果 | 理由 |
|--------------|----------|------|------|
| MAINTENANCE | 1 | DOWN | ローリング不可 |
| MAINTENANCE | 2+ | **DEGRADED** | ローリングアップデート |
| DEPLOY | 2+ | **DEGRADED** | ローリングデプロイ |
| FAILURE | 2+ | DOWN | 予期せぬ障害はDOWN扱い |
| MAINTENANCE + FAILURE | 2+ | DOWN | 計画的でないイベント混在 |

## 修正後の分析結果

### 依存伝播テスト

| 障害対象 | v4.5 可用性 | v4.6 可用性 | 伝播されたDOWN | 説明 |
|---------|------------|------------|---------------|------|
| postgres | 83.3% | **33.3%** | app-1, app-2, nginx | DB障害が全上流に伝播 |
| redis | 83.3% | 83.3% | なし（DEGRADEDのみ） | optional依存はDOWN伝播しない |
| app-1 | 83.3% | 83.3% | なし（nginxがDEGRADED） | app-2が生存でnginxは部分稼働 |
| rabbitmq | 83.3% | 83.3% | なし | async依存は伝播なし |
| nginx | 83.3% | 83.3% | なし | 最上流のため逆方向伝播なし |

PostgreSQLの障害だけが**劇的に異なる数値**を返します。「共有バックエンド（DB）はSPOFリスクが極めて高い」という現実の知見と一致します。

### What-if breakpoints

| パラメータ | 値 | v4.5 avg可用性 | v4.6 avg可用性 | SLO判定 |
|-----------|-----|--------------|--------------|---------|
| mttr_factor | 0.5x | 99.75% | 99.72% | PASS |
| mttr_factor | 1.0x | 99.25% | 99.20% | PASS |
| mttr_factor | 2.0x | 98.51% | 97.84% | PASS |
| mttr_factor | 4.0x | 97.52% | 95.68% | PASS |
| mttr_factor | 8.0x | 96.03% | 91.36% | PASS |
| maint_duration_factor | 0.5x | 99.30% | 99.28% | PASS |
| maint_duration_factor | 1.0x | 99.25% | 99.20% | PASS |
| maint_duration_factor | 2.0x | 99.15% | 99.08% | PASS |
| maint_duration_factor | 3.0x | 99.05% | 98.96% | PASS |
| maint_duration_factor | 5.0x | 98.85% | 98.72% | PASS |

注目すべき点:
1. **mttr_factor**: v4.6はv4.5より低い可用性を返す（依存伝播で影響範囲が拡大）。8.0xで約4.7ポイントの差
2. **maint_duration_factor**: v4.6でも**全PASS**。ローリングアップデート判定によりカスケードDOWNを防止

### Error Budget

```
v4.6 baseline (mttr_factor=1.0):
  avg_availability: 99.20%
  error_budget_remaining: 2.4%
  days_until_exhaustion: 284.6日
```

v4.5（99.25%）からやや低下していますが、依存伝播により障害の影響範囲が正しく計上された**より現実的な数値**です。

## 実運用への教訓

### 1. 単純な「コンポーネント数ベース」の可用性は危険

`availability = (total - down) / total` は全コンポーネントが独立している場合にのみ正しいです。PostgreSQLの例では実質的な影響は1件ではなく4件。単純計算の83.3%がトポロジー考慮で33.3%に。SREチームが可用性レポートで単純平均を使っている場合、**本当のリスクが隠蔽**されている可能性があります。

### 2. SREチームは依存関係を可視化すべき

依存関係グラフが定義されていなければ伝播計算は不可能です。多くの組織ではこの情報が暗黙知として個人の頭の中にしかありません。`requires`/`optional`/`async`の分類を明示的に定義し、定期的にレビューすることを推奨します。

### 3. 共有バックエンド（DB）はSPOFリスクが高い

PostgreSQLの障害が**システム全体の66.7%を停止**させます。対策の優先順位:

1. **DBレプリケーション + 自動フェイルオーバー**: 最も効果的
2. **Read Replica分離**: 読み取りクエリの分散
3. **サーキットブレーカー**: 障害の即座検知とフォールバック
4. **非同期パターンの活用**: 可能な処理をasync依存に移行

### 4. ローリングアップデートはデフォルトであるべき

replicas > 1のコンポーネントで一括停止メンテナンスを行うのは冗長性を無駄にしています。InfraSimのv4.6では、replicas > 1 + 計画イベント → DEGRADEDとして自動判定し、what-if分析で現実的な評価が可能です。

## v4.1〜v4.6の進化サマリー

| バージョン | 主要修正 | 代表的な可用性 | 主な影響 |
|-----------|---------|--------------|---------|
| v4.1 | マルチWhat-if導入 | 99.50% | What-if分析の基盤構築 |
| v4.2 | OVERLOADED状態の80%重み | 98.00% | 過負荷の影響を可用性に反映 |
| v4.3 | max()統一・加重ダウンタイム | 99.50% | 計算方式の一貫性確保 |
| v4.4 | MTBFキャップ(56h)・リスクベースburn rate | 98.70% | MTTR感度分析・Error Budget推定 |
| v4.5 | fault-overlap・キャップ緩和(168h)・base_multiplier | 99.25% | 精度の洗練・モデルの正確性 |
| **v4.6** | **依存伝播・ローリングアップデート判定** | **99.20%** | **トポロジーを考慮した現実的な可用性** |

- **v4.1〜v4.3**: 基盤の正確性向上（計算方式の統一・RNG汚染防止）
- **v4.3〜v4.4**: 分析機能の実用化（MTTR感度・burn rate推定）
- **v4.4〜v4.5**: 精度の洗練（過大評価の排除・モデルの正確性向上）
- **v4.5〜v4.6**: **構造的な正確性**（依存関係トポロジーの反映）

v4.6の可用性（99.20%）はv4.5（99.25%）より低いですが、これは精度の低下ではなく**精度の向上**です。

## まとめ

### v4.6で導入した2件の改善

| # | 改善内容 | 影響 |
|---|---------|------|
| 1 | 依存伝播アルゴリズム（固定点反復） | 依存先の障害が依存元に伝播。postgres DOWN → 33.3%（v4.5: 83.3%） |
| 2 | ローリングアップデート判定 | replicas > 1 の計画メンテナンス → DEGRADED（カスケード爆発を防止） |

### 技術的な設計判断

| 判断 | 理由 |
|------|------|
| effectiveマップを使い実状態を変更しない | 復旧時に依存元が即座に回復する自然な挙動を保証 |
| 固定点反復の上限を`N+1`に設定 | 循環依存でも必ず停止。DAGでは最大N回で収束 |
| DEGRADEDは可用性100%として扱う | 性能低下はSLI違反だがサービス自体は稼働中 |
| 計画イベントのみDEGRADED | ランダム障害はローリングの前提が成り立たない |

6バージョン・累計22件の改善を重ね、InfraSimのシミュレーション結果は**定量的かつ構造的な信頼性**を持つようになりました。v4.6は「可用性の数値が**何を意味するか**」を根本的に変えた改善です。

### 今後の展望

- **部分的requires依存**: `requires`先が複数ある場合に「N個中M個以上がUPならOK」というクォーラムベースの判定
- **依存重み付き伝播**: `weight`フィールドを伝播計算に反映し、重要度に応じた段階的な影響評価
- **トポロジーベースのリスクスコアリング**: 依存グラフの構造（fan-out、深さ、SPOFの位置）からリスクスコアを自動算出
