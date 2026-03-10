---
title: "Claude Codeで24ロール・10フェーズのAI開発チームを自動編成する ― GAFAM+Anthropicの開発フローを完全再現"
emoji: "🏢"
type: "tech"
topics: ["claudecode", "ai", "devops", "sre", "projectmanagement"]
published: true
---

## TL;DR

Claude Code の Agent Teams モードを使い、**GAFAM（Google/Amazon/Meta/Microsoft/Apple）+ Anthropic のエンジニアリングプラクティスを統合した24ロール・9部門・10フェーズの AI 開発チーム**を自動編成する仕組みを作りました。

タスクを渡すだけで、PM が規模を自動判定（S/M/L/XL）し、最適なチームを編成して、Google の Design Doc から Amazon の Bar Raiser レビュー、Anthropic の Red Teaming まで、世界トップレベルの開発フローを全自動で実行します。

さらに、毎朝 6 時に GAFAM 各社の最新エンジニアリングブログを自動リサーチし、プラクティスを最新状態に保つ自動更新システムも構築しました。

## なぜ作ったのか

### AI エージェントの「一人作業」問題

Claude Code は強力ですが、複雑なタスクを1つの AI エージェントに任せると、品質チェックが甘くなりがちです。

実際に経験した失敗：

- MediaConvert で動画変換したら「成功」と報告されたが、実際の出力は仕様と違っていた
- Terraform apply が成功しても、CloudFront の URL にアクセスしたら 403 エラー
- 元動画の解像度を仮定で進めたら、実際は全然違った

**一人で作業すると、自分の出力を客観的に検証できない。** これは人間もAIも同じです。

### GAFAM はどう解決しているか

世界トップのテック企業は、この問題を「組織構造」と「プロセス」で解決しています。

- **Google**: Design Doc → LGTM レビュー → Testing Pyramid → SLO/SLI 監視
- **Amazon**: Working Backwards → Bar Raiser（独立した品質ゲートキーパー）
- **Meta**: Feature Flag で安全にデプロイ → SEV システムでインシデント管理
- **Anthropic**: Red Teaming で敵対的にテスト
- **Microsoft**: STRIDE で脅威をモデリング
- **Apple**: DRI（Directly Responsible Individual）で責任を明確化

**これらのプラクティスを、AI エージェントのロールに割り当てたらどうなるか？**

それがこのプロジェクトの出発点です。

## システム全体像

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                                                                            ║
║    ⚡  C L A U D E   A G E N T   T E A M   E N T E R P R I S E   v2.0    ║
║            ~ GAFAM + Anthropic 統合モデル ~                                ║
║                                                                            ║
║  ┌────────────── 9部門・24ロール・10フェーズ体制 ──────────────┐           ║
║  │                                                              │           ║
║  │  I.   経営・戦略     [PM] [PO]                               │           ║
║  │  II.  リサーチ・企画 [Research] [UX Researcher]              │           ║
║  │  III. 設計           [Tech Lead] [Solution Architect]        │           ║
║  │  IV.  開発           [Frontend] [Backend] [Mobile]           │           ║
║  │                      [Design] [Data]                         │           ║
║  │  V.   インフラ       [Infra] [SRE] [Platform] [DBA]         │           ║
║  │  VI.  品質管理       [QA] [Review] [Bar Raiser] [TestAuto]   │           ║
║  │                      [Performance]                           │           ║
║  │  VII. セキュリティ   [Security] [Red Team] [Compliance]      │           ║
║  │  VIII.運用保守       [Ops] [Incident Cmd] [Docs]             │           ║
║  │  IX.  横断プラクティス (DRI/STO/InnerSource/Blameless)       │           ║
║  │                                                              │           ║
║  └──────────────────────────────────────────────────────────────┘           ║
║                                                                            ║
║  Scale: Auto (S:3名 / M:6-8名 / L:12-16名 / XL:18-24名)                  ║
║                                                                            ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

## 9部門・24ロールの設計

超一流開発会社と同等の組織体制を、AI エージェントのロールとして定義しています。

### 部門構成

| 部門 | ロール | 参考モデル |
|------|--------|-----------|
| I. 経営・戦略 | PM, PO | Amazon Working Backwards |
| II. リサーチ・企画 | Research Engineer, UX Researcher | - |
| III. 設計 | Tech Lead, Solution Architect | Google Design Doc |
| IV. 開発 | Frontend, Backend, Mobile, Design, Data | - |
| V. インフラ | Infra, SRE, Platform, DBA | Google SRE |
| VI. 品質管理 | QA, Review, **Bar Raiser**, Test Auto, Performance | Amazon Bar Raiser, Google Testing Pyramid |
| VII. セキュリティ | Security, **Red Team**, Compliance | Microsoft STRIDE, **Anthropic Red Teaming**, Apple Privacy by Design |
| VIII. 運用保守 | Ops, Incident Commander, Docs | Meta SEV, Amazon COE, Google Postmortem |
| IX. 横断プラクティス | (全ロール共通) | Apple DRI, Amazon STO |

### 特に重要な新ロール

#### Bar Raiser（Amazon 式 品質ゲートキーパー）

Amazon の採用プロセスで有名な Bar Raiser 制度を、コードレビューに応用しました。

- レビューチームとは**完全に独立した立場**で品質を評価
- **拒否権（Veto）** を持つ — Bar Raiser が承認しないとマージ不可
- AWS Well-Architected Framework の6本柱でチェック：
  - 運用優秀性 / セキュリティ / 信頼性 / 効率性 / コスト / 持続可能性

```
通常のレビュー:  レビュアー → LGTM → マージ
Bar Raiser付き:  レビュアー → LGTM → Bar Raiser独立評価 → APPROVE or VETO
                                                              ↑
                                                       拒否されたら
                                                       Gate 1から再実行
```

#### Red Team Engineer（Anthropic 式 敵対的テスト）

Anthropic が AI モデルの安全性評価で使う Red Teaming 手法を、一般的なソフトウェア開発に応用しました。

- 想定攻撃者の視点でシステムの弱点を探索
- OWASP Top 10 ベースの攻撃パターンを実行
- **多回試行攻撃（Multi-Attempt Attack）**: 単一パターンではなく、複数パターンの組み合わせ
- 発見した脆弱性は Critical/High/Medium/Low で分類し、Critical は即修正

## 10フェーズ開発フロー

各フェーズは GAFAM/Anthropic の具体的なプラクティスに基づいています。

```
Phase 0   規模判定・DRI任命              ← Apple DRI
Phase 1   Working Backwards (PR/FAQ)     ← Amazon
Phase 2   Design Doc & RFC               ← Google
Phase 3   Threat Modeling (STRIDE)       ← Microsoft SDL
Phase 4   実装 (Feature Flag駆動)        ← Meta
Phase 5   LGTM + Bar Raiser Review       ← Google + Amazon
Phase 6   Testing Pyramid (70/20/10)     ← Google
Phase 7   Red Teaming                    ← Anthropic
Phase 8   InfraSim 障害耐性評価          ← 自社ツール
Phase 9   SLO/SLI & Error Budget         ← Google SRE
Phase 10  COE + Blameless Postmortem     ← Amazon + Google
```

### 各フェーズの詳細

#### Phase 0: DRI 任命（Apple 式）

Apple の DRI（Directly Responsible Individual）制度を適用。各サブタスクに1名の最終責任者を任命します。

```
タスク: ECサイト構築
├── フロントエンド DRI: frontend-engineer
├── バックエンド DRI: backend-engineer
├── DB設計 DRI: data-engineer
├── セキュリティ DRI: security-engineer
└── 全体 DRI: tech-lead
```

#### Phase 1: Working Backwards（Amazon 式）

コーディングを始める前に、「完成した状態」から逆算して要件を定義します。

PO（プロダクトオーナー）が以下を作成：

1. **仮想プレスリリース**: この機能が完成したら、ユーザーにどう伝えるか
2. **FAQ**: ユーザー/技術的な想定質問と回答
3. **成功指標（KPI）**: 何をもって「成功」とするか

これにより、「作ったけど誰も使わない」という事態を防ぎます。

#### Phase 2: Design Doc（Google 式）

Google のエンジニアリング文化の根幹である Design Doc を作成します。

- **概要**: 何を、なぜ作るのか
- **トレードオフ分析**: 検討した代替案とその却下理由（**最重要**）
- **横断的関心事**: セキュリティ、プライバシー、可観測性
- **ADR（Architecture Decision Record）**: 重要な意思決定を記録

#### Phase 3: Threat Modeling — STRIDE（Microsoft 式）

Microsoft の Security Development Lifecycle（SDL）に基づく脅威分析です。

| 脅威 | チェック内容 |
|-----|------------|
| **S**poofing（なりすまし） | 認証の脆弱性はないか |
| **T**ampering（改ざん） | データの改ざんリスクはないか |
| **R**epudiation（否認） | 操作ログは適切か |
| **I**nformation Disclosure（情報漏洩） | 機密データの露出リスクはないか |
| **D**enial of Service（DoS） | サービス妨害への耐性はあるか |
| **E**levation of Privilege（特権昇格） | 権限管理は適切か |

#### Phase 4: Feature Flag 駆動開発（Meta 式）

Meta（旧 Facebook）の Gatekeeper システムに倣い、新機能は原則として Feature Flag で包みます。

```
// Feature Flag で包んだ実装
if (featureFlags.isEnabled('new-checkout-flow')) {
  return <NewCheckoutFlow />;
} else {
  return <LegacyCheckoutFlow />;
}
```

- デプロイとロールアウトを分離
- ロールバック = Feature Flag を OFF にするだけ
- 段階的にユーザーへ展開可能

#### Phase 5: LGTM + Bar Raiser レビュー（Google + Amazon 式）

2段階のコードレビューで品質を担保します。

```
┌─────────────────────────────────────────────────────────┐
│  Stage 1: LGTM Review (Google)                          │
│  → レビューエンジニアがコード品質・Readability を審査  │
│  → 承認条件: 未解決コメント0件 + LGTM取得              │
│                                                         │
│  Stage 2: Bar Raiser Review (Amazon) ← L規模以上       │
│  → 独立した立場で Well-Architected 6本柱をチェック     │
│  → 拒否権あり: 品質基準を下げる変更は VETO            │
└─────────────────────────────────────────────────────────┘
```

#### Phase 6: Testing Pyramid 70/20/10（Google 式）

Google の Mike Wacker が提唱した自動テストの黄金比率を適用します。

```
        ┌───────┐
        │ E2E   │  10%  ← 最もコストが高い。ユーザーフロー確認
        │ Tests │
       ─┤       ├─
      ┌─┤       ├─┐
      │ Integration │  20%  ← コンポーネント間連携の確認
      │   Tests     │
     ─┤             ├─
    ┌─┤             ├─┐
    │   Unit Tests    │  70%  ← 高速・低コスト。個別関数の検証
    │                 │
    └─────────────────┘
```

#### Phase 7: Red Teaming（Anthropic 式）

Anthropic の多層的 Red Teaming 手法でセキュリティを検証します。

- OWASP Top 10 ベースの攻撃パターン実行
- 多回試行攻撃（組み合わせ攻撃）
- バグバウンティ的なエッジケース探索
- Critical/High の脆弱性は即修正 → 再テスト

#### Phase 8: InfraSim 障害耐性評価

自作のカオスエンジニアリングツール [InfraSim](https://github.com/mattyopon/infrasim) で、実インフラに触れずに障害耐性を評価します。

- Terraform state や YAML 定義からインフラ構成をインポート
- **150 以上の障害シナリオ**を自動実行（30 カテゴリ）
- CISA/NVD 等のセキュリティフィードと連動した最新脅威シナリオ
- リスクスコア（CRITICAL / WARNING / PASSED）で定量評価

```bash
# Terraform state からインポート → シミュレーション → レポート生成
infrasim tf-import --state terraform.tfstate
infrasim simulate --model model.json --html report.html
infrasim feed-update --model model.json  # 最新脅威連動
```

#### Phase 9: SLO/SLI & Error Budget（Google SRE 式）

Google SRE の信頼性管理フレームワークを適用します。

```
SLI（指標）: 成功リクエスト数 / 全リクエスト数
SLO（目標）: 99.9%（月間ダウンタイム約43分）
Error Budget: 1 - SLO = 0.1%

Error Budget 残存 → 新機能リリースOK
Error Budget 超過 → 安定性改善以外のリリース停止
```

#### Phase 10: COE + Blameless Postmortem（Amazon + Google 式）

- **COE（Correction of Errors）**: Amazon の 5 Whys 分析で根本原因を追究
- **Blameless Postmortem**: Google 式の「誰が悪い」ではなく「なぜ起きた」に集中する文化

## 5ゲート品質システム

Phase 5〜8 で問題が検出されると、自動的に修正ループが回ります。**全ゲートをパスするまで先に進めません。**

```
Gate 1: LGTM Review          ← Google       → FAIL時: 修正→再レビュー
Gate 2: Bar Raiser Veto      ← Amazon       → VETO時: Gate 1から再実行
Gate 3: Testing Pyramid      ← Google       → FAIL時: 修正→再テスト
Gate 4: Red Team             ← Anthropic    → Critical時: 修正→再テスト
Gate 5: InfraSim Chaos       ← 自社ツール   → CRITICAL時: インフラ修正→再シミュレーション
```

## 自動規模判定

タスクを渡すだけで、PM が自動的に規模を判定し、最適なチームを編成します。

| 規模 | 基準 | チーム規模 | 適用フェーズ |
|------|------|-----------|-------------|
| S | バグ修正、設定変更 | 3〜4名 | Phase 0,4,6,10 |
| M | 機能追加、API開発 | 6〜8名 | Phase 0-2,4-6,10 |
| L | フルスタック開発 | 12〜16名 | **全Phase (0-10)** |
| XL | 本番デプロイ | 18〜24名 | **全Phase (0-10)** |

```
ユーザー: 「ECサイトを作って」

PM判定: L規模（16名）
  経営(PM+PO) + リサーチ(research+UX) + 設計(tech-lead+architect)
  + 開発(frontend+backend+design+data)
  + 品質(QA+review+bar-raiser+test-auto)
  + セキュリティ(security+red-team) + ドキュメント(docs)

Phase: 0→1(PR/FAQ)→2(Design Doc)→3(STRIDE)→4(Feature Flag)
       →5(LGTM+Bar Raiser)→6(70/20/10)→7(Red Team)→9(SLO/SLI)→10(COE)
```

## 毎日自動更新する仕組み

GAFAM/Anthropic のプラクティスは日々進化しています。手動で追いかけるのは非現実的なので、**毎朝自動でリサーチ → CLAUDE.md を更新する仕組み**を作りました。

### アーキテクチャ

```
┌─── 毎朝 6:03 AM（crontab）──────────────────────────────┐
│                                                          │
│  1. Claude CLI (sonnet) が非対話モードで起動             │
│                                                          │
│  2. GAFAM 各社の公式ブログをリサーチ                     │
│     - Google Engineering Blog / SRE Blog                 │
│     - AWS Blog / Amazon Science                          │
│     - Engineering at Meta                                │
│     - Anthropic Research Blog                            │
│     - Microsoft DevBlog                                  │
│     - Apple ML Research                                  │
│     + Pragmatic Engineer, InfoQ, DORA, ThoughtWorks      │
│                                                          │
│  3. 現在の CLAUDE.md と比較・差分分析                    │
│                                                          │
│  4. 更新判定                                             │
│     MUST UPDATE (2社以上採用) → 即反映                  │
│     SHOULD UPDATE (1社+実証済) → 反映                   │
│     CONSIDER (実験段階) → ウォッチリストに追加           │
│                                                          │
│  5. CLAUDE.md を自動更新                                 │
│                                                          │
│  6. 更新ログに記録                                       │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

### セットアップ

```bash
# crontab に登録済み
3 6 * * * /usr/bin/flock -n /tmp/agent-team-research.lock \
  /home/user/scripts/agent-team-daily-research.sh
```

- `flock` で多重実行を防止
- ログは 500 行でローテーション
- 更新履歴は `agent-team-updates.md` に全て記録

## 実装方法

### 1. CLAUDE.md にルールを定義

Claude Code は `CLAUDE.md` というファイルでプロジェクトルールを定義できます。ここに Agent Team の全ルール（ロール定義、フェーズ、品質ゲート等）を記述しています。

### 2. `--append-system-prompt` で自動起動

Windows Terminal のプロファイルに以下を設定し、起動時に自動的に Agent Teams モードになるようにしています。

```json
{
  "name": "Claude Agent Team",
  "commandline": "wsl.exe claude --append-system-prompt \"You are running in Agent Teams mode. Always use agent teams for every task. Automatically determine the scale (S/M/L/XL) and create an appropriate agent team following the CLAUDE.md team configuration rules.\""
}
```

### 3. 使い方

ターミナルで「Claude Agent Team」プロファイルを開いて、タスクを投げるだけです。

```
ユーザー: 「ログイン機能を追加して」
  ↓（放置）
PM: 規模判定 → M（8名）
  → Phase 1: PR/FAQ作成
  → Phase 2: Design Doc作成
  → Phase 4: Feature Flag付きで実装
  → Phase 5: LGTM + Bar Raiser レビュー
  → Phase 6: Testing Pyramid (70/20/10)
  → Phase 10: 完了報告 + COE
PM: 「完了しました。実装サマリーと資料はこちらです。」
```

**ユーザーは最初の指示を出したら、完了報告まで一切操作しません。**

## 各社プラクティスの導入マッピング

| 企業 | 導入プラクティス | 適用Phase |
|------|----------------|-----------|
| **Google** | Design Doc/RFC, LGTM + Readability Review, Testing Pyramid 70/20/10, SLO/SLI/Error Budget, Blameless Postmortem | 2, 5, 6, 9, 10 |
| **Amazon** | Working Backwards PR/FAQ, Bar Raiser (Veto権), Well-Architected 6本柱, COE (5 Whys), Single-Threaded Ownership | 1, 5, 10, 全Phase |
| **Meta** | Feature Flag 駆動開発, SEV レベル分類, Gatekeeper 方式ロールアウト | 4, 10 |
| **Anthropic** | Red Teaming (多層的敵対的テスト), Multi-Attempt Attack, バグバウンティ的探索 | 7 |
| **Microsoft** | STRIDE 脅威モデリング, Security Development Lifecycle (SDL), Inner Source | 3 |
| **Apple** | DRI (Directly Responsible Individual), Privacy by Design | 0, 全Phase |

## 既存のアプローチとの比較

| 項目 | 単独AI | Cursor / Copilot | Agent Team (本システム) |
|------|--------|-------------------|------------------------|
| ロール分離 | なし | なし | 24ロール・9部門 |
| 品質ゲート | なし | Lintのみ | 5段階ゲート |
| 設計ドキュメント | なし | なし | Design Doc + ADR |
| セキュリティ | 基本チェック | 基本チェック | STRIDE + Red Team |
| 障害耐性評価 | なし | なし | InfraSim 150+シナリオ |
| 信頼性管理 | なし | なし | SLO/SLI + Error Budget |
| 自動更新 | なし | なし | 毎朝GAFAM最新リサーチ |
| 完全自律 | 途中で質問 | 途中で質問 | 最初の指示→完了報告のみ |

## 今後の展望

- **CI/CD パイプラインとの統合**: GitHub Actions で品質ゲートを自動実行
- **メトリクス収集**: 各フェーズの所要時間・修正ループ回数を記録し、プロセス改善に活用
- **Canary Deployment の実装**: Phase 8 と Phase 9 の間に段階的ロールアウトフェーズを追加
- **A/B テスト統合**: Meta の Ax プラットフォームに倣った実験駆動型開発の導入
- **新興企業のプラクティス追加**: Stripe, Vercel, Linear 等のスタートアップの開発手法も調査対象に

## まとめ

Claude Code の Agent Teams モードと CLAUDE.md のルール定義を組み合わせることで、**GAFAM + Anthropic の世界最高水準の開発プラクティスを AI エージェントチームとして再現**できました。

ポイントは3つ：

1. **ロール分離**: 実装者とレビュアーを分け、独立した品質ゲート（Bar Raiser）を設ける
2. **プロセスの標準化**: 10 フェーズの開発フローで、抜け漏れなく品質を担保する
3. **継続的改善**: 毎朝自動でリサーチし、プラクティスを最新に保つ

AI エージェントの可能性は「1人の優秀なエンジニア」ではなく、**「世界最高の開発チーム」を再現すること**にあると考えています。
