---
title: "InfraSim v1.0 — OSSカオスエンジニアリングツールを商用化した全プロセス"
emoji: "🏗️"
type: "tech"
topics: ["infrasim", "sre", "devops", "chaosengineering", "oss"]
published: true
---

## はじめに

InfraSim は「本番環境に一切触れずに、インフラの可用性限界を数学的に証明する」カオスエンジニアリングプラットフォームです。

https://github.com/mattyopon/infrasim

従来のカオスエンジニアリングツール（Gremlin, Steadybit, AWS FIS）は実際のインフラに障害を注入する「フォルトインジェクション」方式を採用しています。InfraSim はまったく異なるアプローチで、依存関係グラフを純粋な数学的シミュレーションとしてメモリ上にモデル化し、150以上の障害シナリオを自動生成・実行します。

v5.14 までの開発でコア機能（5つのシミュレーションエンジン、3層可用性限界モデル、30カテゴリのカオスシナリオ）を磨き上げてきましたが、今回 **v1.0 として商用化に向けた基盤整備** を行いました。

この記事では、OSSツールを「売れる製品」にするために何が必要だったかを、具体的なコードと設計判断とともに紹介します。

## InfraSim が解決する課題

### 既存ツールとの比較

| | **Gremlin** | **Steadybit** | **AWS FIS** | **InfraSim** |
|---|---|---|---|---|
| **アプローチ** | 障害注入 | 障害注入 | 障害注入 | 数学的シミュレーション |
| **本番リスク** | 中〜高 | 中 | 中 | **ゼロ** |
| **セットアップ** | ホスト毎にエージェント | ホスト毎にエージェント | AWSのみ | **pip install のみ** |
| **シナリオ数** | 手動設定 | 手動設定 | AWSサービスのみ | **150+自動生成** |
| **可用性証明** | なし | なし | なし | **3層限界モデル** |
| **コスト** | $$$$ | $$$ | $$ (AWS-only) | **無料 / OSS** |
| **依存関係グラフ** | なし | 限定的 | なし | **NetworkX完全グラフ** |
| **Terraform連携** | なし | なし | ネイティブ | **tfstate + plan分析** |
| **セキュリティフィード** | なし | なし | なし | **CVE自動シナリオ生成** |

### ゼロリスクアプローチの優位性

最大の差別化ポイントは **「本番環境に一切触れない」** ことです。

Gremlin は実サーバーにエージェントを配置して実際に CPU を 100% にしたりプロセスを Kill したりします。これは強力ですが、「カオスエンジニアリングをやりたいが、本番に障害を入れる勇気がない」というチームには導入障壁が高すぎます。

InfraSim は NetworkX の有向グラフとして依存関係をモデル化し、メモリ上で障害伝搬をシミュレートします。実行結果は決定的（同じ入力なら同じ出力）で、何度でも安全に再現できます。

### 3層可用性限界モデル（独自の売り）

InfraSim 独自の理論モデルです。従来のカオスツールが「何が壊れるか？」に答えるのに対し、InfraSim は **「あなたのアーキテクチャが物理的に達成できる最大可用性はいくつか？」** に答えます。

```
                    ┌─────────────────────────────────────────┐
                    │                                         │
  Layer 3 ──────── │  理論限界          6.65 nines            │ ── 上限（到達不可）
                    │  (完全冗長性 + 瞬時フェイルオーバー)     │
                    │                                         │
  Layer 2 ──────── │  ハードウェア限界   5.91 nines            │ ── 物理的上限
                    │  (MTBF × 冗長係数)                       │
                    │                                         │
  Layer 1 ──────── │  ソフトウェア限界   4.00 nines            │ ── 実用上限
                    │  (デプロイ失敗 + 設定ドリフト + ヒューマンエラー) │
                    │                                         │
                    └─────────────────────────────────────────┘
```

**なぜこれが重要か：** SLO 目標が 99.99% でも Layer 1 の限界が 99.95% なら、どれだけエンジニアリング努力を重ねてもアーキテクチャ変更なしにはギャップを埋められません。InfraSim は **数ヶ月の無駄な努力の前に** それを教えてくれます。

## 商用化で追加した機能（Phase 1-3）

### Phase 1: OSSパッケージング

OSSとして「5分で試せる」状態にすることが最優先でした。

#### Docker + docker-compose（3プロファイル）

```yaml
# docker-compose.yml
services:
  web:
    build: .
    ports:
      - "8000:8000"

  demo:
    build: .
    profiles: ["demo"]
    command: infrasim demo --web --host 0.0.0.0

  cli:
    build: .
    profiles: ["cli"]
    entrypoint: ["infrasim"]
```

3つのプロファイルで用途別に起動できます。

```bash
# Web ダッシュボード
docker compose up web

# デモモード（サンプルインフラ付き）
docker compose --profile demo up demo

# CLI モード
docker compose --profile cli run cli simulate
```

#### GitHub Actions CI/CD（Python 3.11-3.13マトリクス）

```yaml
strategy:
  matrix:
    python-version: ["3.11", "3.12", "3.13"]
```

3バージョンのマトリクスビルドに加え、Docker イメージのビルドテストも CI に含めています。カバレッジレポートは `pytest-cov` + Codecov で自動計測します。

#### GitHub Action（再利用可能）

InfraSim を他のリポジトリの CI に組み込めるように、GitHub Action として公開しました。

```yaml
# 他のリポジトリの .github/workflows/ で利用
- uses: mattyopon/infrasim@main
  with:
    yaml-file: infra.yaml
    comment-on-pr: true
```

これにより、PR のたびに InfraSim がインフラ定義ファイルをスキャンし、Resilience Score と Critical 数を PR コメントに出力します。

### Phase 2: SaaS基盤

#### SQLAlchemy + SQLite 永続化

```python
# database.py — SQLAlchemy 2.0 async style
class TeamRow(Base):
    __tablename__ = "teams"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))

class UserRow(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    api_key_hash: Mapped[str] = mapped_column(String(64), unique=True)
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"))
```

マルチテナント対応として `Team` → `User` → `Project` → `SimulationResult` の階層構造を設計しました。SQLite を選んだのは「pip install だけで動く」を維持するためです。将来 PostgreSQL に切り替えても、SQLAlchemy の抽象化レイヤーがあるのでコード変更は接続文字列のみです。

#### APIキー認証（SHA-256、後方互換）

```python
def hash_api_key(api_key: str) -> str:
    """SHA-256 ハッシュで保存。平文は DB に残さない。"""
    return hashlib.sha256(api_key.encode()).hexdigest()
```

重要な設計判断として、**ユーザーが1人もいない場合は認証をスキップ** する後方互換モードを実装しました。これにより、既存の OSS ユーザーが突然認証エラーで動かなくなることを防いでいます。

```python
async def get_current_user(request, credentials):
    # Public endpoints は常にスルー
    if _is_public(request.url.path):
        return None
    # ユーザーが0人 = 後方互換モード（認証なし）
    # ユーザーが1人以上 = 認証必須
```

#### CSV/JSON/PDF/Markdown エクスポート

シミュレーション結果を5つの形式でエクスポートできるようにしました。

```python
# export.py
def export_csv(report: SimulationReport, path: Path) -> None:
    rows = _report_rows(report)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

def export_json(report: SimulationReport, path: Path) -> None:
    rows = _report_rows(report)
    with open(path, "w") as f:
        json.dump(rows, f, indent=2)
```

| 形式 | ユースケース |
|------|-------------|
| HTML | Web ダッシュボードでのインタラクティブ表示 |
| CSV | Excel / Google Sheets での分析 |
| JSON | API連携、他ツールへのパイプライン |
| PDF | 経営層への報告書 |
| Markdown | GitHub Issue / Wiki への貼り付け |

### Phase 3: AI + エンタープライズ

#### AI分析エンジン（SPOF検出、カスケード分析、改善提案）

```python
@dataclass
class AIRecommendation:
    component_id: str
    category: str       # "spof", "capacity", "cascade", "config", "cost"
    severity: str       # "critical", "high", "medium", "low"
    title: str
    description: str
    remediation: str
    estimated_impact: str  # e.g., "4.2 -> 5.1 nines"
    effort: str            # "low", "medium", "high"
```

AI 分析エンジンは、シミュレーション結果を解析して以下を自動生成します。

- **SPOF（単一障害点）検出**: 冗長性のないコンポーネントを特定
- **カスケード分析**: 障害伝搬パスの中で最も影響が大きいパスを特定
- **改善提案**: 具体的な修正アクション（「Redis をレプリカ構成にすることで 3.5 → 4.0 nines に改善」等）と、その実装コスト（low/medium/high）を提示

#### DORA準拠レポート生成

金融機関向けに DORA（Digital Operational Resilience Act）に準拠したコンプライアンスレポートを HTML で自動生成します。

```python
# compliance.py
"""DORA requires:
1. ICT risk management
2. Incident reporting
3. Resilience testing
4. Third-party risk management
5. Information sharing
"""
```

InfraSim のシミュレーション結果を DORA の5つの要件にマッピングし、各要件に対する充足度を可視化します。

#### プラグインシステム（カスタムシナリオ追加）

```python
class ScenarioPlugin(Protocol):
    """カスタムシナリオプラグインのインターフェース"""
    name: str
    description: str
    def generate_scenarios(self, graph, component_ids, components) -> list: ...

class AnalyzerPlugin(Protocol):
    """カスタム分析プラグインのインターフェース"""
    name: str
    def analyze(self, graph, report) -> dict: ...
```

`Protocol` ベースの設計により、型チェックが効きつつも継承を強制しません。プラグインはディレクトリに `.py` ファイルを置くだけで動的にロードされます。

```python
class PluginRegistry:
    @classmethod
    def load_plugins_from_dir(cls, plugin_dir: Path):
        for py_file in sorted(plugin_dir.glob("*.py")):
            spec = importlib.util.spec_from_file_location(py_file.stem, py_file)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            if hasattr(module, "register"):
                module.register(cls)
```

## その他の改善項目

### テストカバレッジ 52% → 77%（テスト数 89 → 482）

テスト数を5倍以上に増やしました。特に強化したのは以下の領域です。

| モジュール | テスト数 | カバー範囲 |
|-----------|---------|-----------|
| カスケードエンジン | 14 | 障害伝搬、重大度スコアリング、複合障害 |
| ダイナミックエンジン | 14 | CLI出力、重大度分類、境界値 |
| Opsエンジン | 9 | SLO追跡、トラフィックパターン、デプロイ |
| キャパシティエンジン | 8 | 予測、ライトサイジング、SLO目標 |
| AI分析 | 複数 | SPOF検出、推奨事項生成 |
| 認証 | 複数 | APIキー、OAuth、後方互換 |
| エクスポート | 複数 | CSV/JSON/PDF 出力検証 |
| プラグイン | 複数 | ロード/登録/実行 |
| **合計** | **482** | **全パス** |

### CLI分割（モノリシック → 7モジュール）

元々 758行あった `cli.py` を7つのモジュールに分割しました。

```
src/infrasim/cli/
├── __init__.py
├── main.py        # コアコマンド（scan, simulate, demo, serve, load, show, report）
├── analyze.py     # analyze, dora-report
├── discovery.py   # tf-import, tf-plan
├── feeds.py       # feed-update, feed-list, feed-sources, feed-clear
├── ops.py         # ops-sim, whatif, capacity
└── simulate.py    # dynamic
```

### CORS + レート制限 + 構造化エラー

```python
# server.py
class RateLimiter:
    """スライディングウィンドウ方式のインメモリレート制限"""
    def __init__(self, max_requests: int = 60, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window = window_seconds

    def is_allowed(self, client_id: str) -> bool:
        now = time.time()
        self.requests[client_id] = [
            t for t in self.requests[client_id] if now - t < self.window
        ]
        return len(self.requests[client_id]) < self.max_requests
```

### Webhook通知（Slack / PagerDuty / Generic）

```python
async def send_slack_notification(webhook_url: str, report_summary: dict) -> bool:
    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": "InfraSim Simulation Report"}},
        {"type": "section", "text": {"type": "mrkdwn", "text":
            f"*Resilience Score:* {report_summary.get('resilience_score')}/100\n"
            f"*Critical:* {report_summary.get('critical_count', 0)}"
        }},
    ]
```

シミュレーション結果を Slack / PagerDuty に自動通知する Webhook 連携です。PagerDuty は Critical レベルの障害検出時のみイベントを発火します。

### SSO（OAuth2 GitHub/Google）

```python
# oauth.py
GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"

@dataclass
class OAuthConfig:
    provider: str  # "github" or "google"
    client_id: str
    client_secret: str
    redirect_uri: str

    @classmethod
    def from_env(cls, provider: str) -> Optional["OAuthConfig"]:
        prefix = f"INFRASIM_OAUTH_{provider.upper()}"
        client_id = os.getenv(f"{prefix}_CLIENT_ID")
        client_secret = os.getenv(f"{prefix}_CLIENT_SECRET")
        # ...
```

環境変数ベースの設定で、GitHub / Google OAuth2 SSO を有効化できます。

### Prometheus継続監視

Web サーバー起動時に Prometheus URL が環境変数 `INFRASIM_PROMETHEUS_URL` で設定されていれば、バックグラウンドで Prometheus からメトリクスを定期取得し、リアルタイムにインフラグラフを更新します。

### Cloud Deploy Configs

Railway、Render、Fly.io の設定ファイルを同梱し、ワンクリックデプロイを実現しました。

```toml
# fly.toml
[build]
  dockerfile = "Dockerfile"

[[services]]
  internal_port = 8000
  protocol = "tcp"
```

## 技術的な設計判断

### AI分析はハイブリッドアプローチを採択

AI 分析エンジンの設計で最も悩んだのは「LLM をどこまで使うか」でした。

```python
class LLMProvider(Protocol):
    """将来のLLM統合用インターフェース"""
    def generate_summary(self, context: dict) -> str: ...
    def generate_recommendations(self, context: dict) -> list[dict]: ...
```

最終的に3層のハイブリッドアプローチを採用しました。

| 層 | 方式 | 特徴 | 現在の状態 |
|----|------|------|-----------|
| **Layer 1** | ルールベース | 決定的・再現可能・無料・常時利用可能 | **実装済み** |
| **Layer 2** | AI分析 | シミュレーション結果の解釈・自然言語サマリー | Protocol定義済み |
| **Layer 3** | AIシナリオ生成 | 未知の障害パターンをLLMで生成 | インターフェース準備済み |

**なぜルールベースを Layer 1 にしたか：**

1. **再現性**: ルールベースは同じ入力に対して常に同じ結果を返す。カオスエンジニアリングの文脈では、テスト結果の再現性は非常に重要
2. **コスト**: API呼び出し不要で無料。OSS として配布する以上、ユーザーに API キーの取得を強制したくない
3. **速度**: ルールベースは即座に結果を返す。482テスト全件が1.5秒で完了する環境で、API 呼び出しの数秒は許容できない

LLM は Layer 2 以降で「結果の解釈」と「改善提案の詳細化」に使う設計で、`Protocol` でインターフェースだけ定義しておき、後から OpenAI / Anthropic / ローカル LLM を差し替え可能にしています。

### プラグインシステムの設計

プラグインの設計では **Protocol（構造的サブタイピング）** を採用しました。

```python
class ScenarioPlugin(Protocol):
    name: str
    description: str
    def generate_scenarios(self, graph, component_ids, components) -> list: ...
```

`ABC`（抽象基底クラス）ではなく `Protocol` を選んだ理由は以下です。

1. **継承不要**: プラグイン作成者が InfraSim のソースに依存せずに実装できる
2. **型チェック**: mypy / pyright で静的型チェックが効く
3. **ダックタイピング**: Python の哲学に合致

ファイルベースの動的ローディングにより、`~/.infrasim/plugins/` にファイルを置くだけでカスタムシナリオが追加されます。

### 後方互換性を壊さない認証設計

商用化で認証を追加する際、最も注意したのは **既存 OSS ユーザーの体験を壊さないこと** でした。

認証を有効にするには「最初のユーザーを作成する」というアクションが必要で、ユーザーが0人の状態では認証が完全に無効化されます。これにより、`pip install infrasim && infrasim demo` のワークフローが一切変わりません。

## アーキテクチャ全体像

```
Discovery Layer          Model Layer           Simulator Layer
┌─────────────┐    ┌─────────────────┐    ┌──────────────────┐
│ Local Scan   │    │ InfraGraph      │    │ 30-cat Scenarios │
│ Prometheus   │───>│ Components      │───>│ Cascade Engine   │
│ Terraform    │    │ Dependencies    │    │ Dynamic Engine   │
│ YAML Loader  │    │ NetworkX Graph  │    │ Ops Engine       │
└─────────────┘    └─────────────────┘    │ What-If Engine   │
                                          │ Capacity Engine  │
                                          │ Traffic Models   │
                                          │ Feed Scenarios   │
                                          │ Risk Scoring     │
                                          │ 3-Layer Limits   │
                                          └──────────────────┘
                                                    │
                   ┌─────────────────┐    ┌──────────────────┐
                   │ Web Dashboard   │<───│ CLI Reporter     │
                   │ FastAPI + D3.js │    │ HTML/CSV/JSON    │
                   │ OAuth + APIKey  │    │ PDF/Markdown     │
                   │ Docker Ready    │    │ AI Analyzer      │
                   │ Prometheus Mon. │    │ DORA Compliance  │
                   └─────────────────┘    └──────────────────┘
```

## 数字で見る成果

| 指標 | Before (v5.14) | After (v1.0) |
|------|----------------|--------------|
| テスト数 | 89 | **482** |
| テストカバレッジ | 52% | **77%** |
| ソースモジュール数 | 6 | **12** |
| CLIコマンド | 16 | 16（+3新規: analyze, dora-report, export） |
| エクスポート形式 | 1 (HTML) | **5** (HTML/CSV/JSON/PDF/MD) |
| 認証 | なし | **APIキー + OAuth2 SSO** |
| 通知連携 | なし | **Slack/PagerDuty/Generic** |
| DB永続化 | なし | **SQLAlchemy + SQLite** |
| マルチテナント | なし | **Team → User → Project 階層** |
| プラグイン | なし | **ScenarioPlugin / AnalyzerPlugin** |
| AI分析 | なし | **SPOF/カスケード/改善提案** |
| コンプライアンス | なし | **DORA準拠レポート** |
| CI/CD | なし | **GitHub Actions (3.11-3.13 matrix)** |
| Cloud Deploy | なし | **Railway/Render/Fly.io** |
| GitHub Action | なし | **再利用可能なPRチェック** |

## 次のステップ

- **PyPI公開**: `pip install infrasim` で即座にインストール可能にする
- **ライブデモ**: クラウドにデモインスタンスをデプロイし、サインアップなしで体験できる環境を用意
- **ProductHunt / Hacker News ローンチ**: 海外コミュニティへの露出
- **LLM統合**: Layer 2 AI分析の本実装（OpenAI / Anthropic API 連携）
- **Kubernetes マニフェストからの自動インポート**

## まとめ

OSSツールを「売れる製品」にするために最も重要だったのは以下の4点です。

**1. パッケージング（Docker / PyPI / README）**

「5分で試せる」ことが全てです。`docker compose up web` だけで動く、`infrasim demo` で即座に結果が見える、この体験がなければ誰も2度目の起動をしてくれません。

**2. 信頼性の証明（テスト482件、CI/CD、カバレッジバッジ）**

エンタープライズ顧客は「このツールが壊れないこと」を証明してほしいと考えます。Python 3.11/3.12/3.13 のマトリクスビルド、482件のテスト、77%のカバレッジがその証明になります。

**3. エンタープライズ要件（認証 / 監査 / コンプライアンス）**

APIキー認証、OAuth2 SSO、マルチテナント、DORA準拠レポート。これらがなければ、企業のセキュリティレビューを通過できません。ただし、これらの追加が既存 OSS ユーザーの体験を壊さないよう、後方互換性には細心の注意を払いました。

**4. 差別化の可視化（3層限界モデル、AI分析、DORA準拠）**

技術的に優れていても、差別化が伝わらなければ意味がありません。3層可用性限界モデルは「他のツールにはない独自の価値」を一目で理解させる武器です。

---

InfraSim はまだ商用化の旅の途中ですが、OSS から製品への転換で学んだことは、技術力そのものよりも「技術力をどう見せるか」「既存ユーザーの体験をどう守るか」が重要だということでした。

https://github.com/mattyopon/infrasim
