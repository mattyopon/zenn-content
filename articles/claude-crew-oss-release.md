---
title: "Claude Codeを24人のAI開発チームにするOSSを公開した ― GAFAM文化をコマンド1つでインストール"
emoji: "🚀"
type: "tech"
topics: ["claudecode", "ai", "oss", "devops", "projectmanagement"]
published: false
---

## TL;DR

Claude Codeに1ファイル（`CLAUDE.md`）を置くだけで、**24ロール・9部門・12フェーズのAI開発チーム**が自動編成されるOSSフレームワーク「**claude-crew**」を公開しました。

https://github.com/mattyopon/claude-crew

```bash
git clone https://github.com/mattyopon/claude-crew.git
cd claude-crew && ./install.sh ~/your-project
```

60秒でインストール。APIキー不要。Claude Codeのサブスクリプションだけで動きます。

## 「一人のAI」から「AIチーム」へ

Claude Codeは強力です。でも、一人の人間に全工程を任せたら品質が落ちるのと同じで、**一つのAIに設計・実装・テスト・レビュー・セキュリティを全部やらせると、どこかで手を抜く**。

実際に経験した失敗：
- 「ビルド成功」と報告されたけど、実際は存在しないnpmパッケージをimportしていた
- テストは通ったけど、本番で504エラー（N+1クエリを見逃していた）
- セキュリティレビューなしでデプロイしたら、XSS脆弱性が残っていた

**解決策はシンプル：役割分担して、相互チェックする。**

でもそれを毎回手動で指示するのは面倒。だからCLAUDE.mdに全部書いて、自動化した。それがclaude-crewです。

## 何が起こるか

あなたがClaude Codeに「ECサイトを作って」と言うと：

```
╔══════════════════════════════════════════════════════════╗
║  🏢 AGENT TEAM ACTIVATED                                ║
║  Project: ec-site                                        ║
║  Scale: L  |  Members: 16  |  Phases: 0→1→2→3→4→5→6→10 ║
╚══════════════════════════════════════════════════════════╝
```

PMが自動で規模判定（L規模: 16名チーム）して：

1. **Working Backwards**（Amazon式）— 完成状態から逆算してPR/FAQを作成
2. **Design Doc**（Google式）— 設計書を書いてからコードに着手
3. **STRIDE脅威分析**（Microsoft式）— セキュリティを設計段階でチェック
4. **実装**（Meta式Feature Flag）— デプロイとリリースを分離
5. **Hallucination Guard** — AIが作った存在しないパッケージ・APIを検出
6. **コードレビュー**（Google LGTM + Amazon Bar Raiser）— 品質ゲートキーパー
7. **Testing Pyramid**（Google式 70/20/10）— Unit 70%, Integration 20%, E2E 10%
8. **完了報告 + COE** — Blameless Postmortemの文化

**全部自動。あなたは最初の一言だけ。**

## 競合との違い

「AIエージェントフレームワーク」は山ほどある。CrewAI、MetaGPT、AutoGen、OpenDevin...

でも全部、致命的な問題がある：

| | claude-crew | CrewAI | MetaGPT | AutoGen |
|---|:---:|:---:|:---:|:---:|
| **APIキー不要** | ✅ | ❌ | ❌ | ❌ |
| **追加コスト** | $0 | API課金 | API課金 | API課金 |
| **GAFAM文化** | ✅ 5社 | ❌ | ❌ | ❌ |
| **品質パイプライン** | ✅ 11スクリプト | ❌ | ❌ | ❌ |
| **ハルシネーション検出** | ✅ | ❌ | ❌ | ❌ |
| **ローカル実行** | ✅ | ❌ | ❌ | ❌ |
| **セットアップ** | 60秒 | 数分 | 数分 | 複雑 |

### なぜローカル実行が重要か

1. **コスト**: API課金なし。サブスクの定額内で動く
2. **プライバシー**: コードが外部に送信されない（Claude Codeはローカル実行）
3. **速度**: MCP呼び出しの80%は500ms未満で解決
4. **安定性**: レートリミットに引っかからない

## アーキテクチャ

```
あなた: "○○を作って"
  │
  ▼
Phase 0: PMが規模を自動判定 (S/M/L/XL/Ops)
  │      24ロールから必要な人材だけ招集
  │      DRI（Apple式 最終責任者）を任命
  │
  ▼
Phase 1-3: 設計フェーズ（M規模以上）
  │  Working Backwards → Design Doc → STRIDE
  │
  ▼
Phase 4: 実装（Feature Flag駆動）
  │  エンジニアが並行実装
  │
  ▼
Phase 4.5: Hallucination Guard ← ★ここが重要
  │  存在しないパッケージ・API・インポートを自動検出
  │  npm/PyPI/Goのレジストリに実際に問い合わせて検証
  │
  ▼
Phase 5-6: レビュー + テスト
  │  5エージェント並行コードレビュー
  │  Google式テストピラミッド
  │
  ▼
Phase 10: 完了報告 + 自動ドキュメント生成
```

## 24ロール・9部門

| 部門 | ロール | いつ招集 |
|------|--------|---------|
| 経営 | PM, Product Owner | 常に |
| リサーチ | Research Engineer, UX Researcher | 常に |
| 設計 | Tech Lead, Solution Architect | 常に |
| 開発 | Frontend, Backend, Mobile, Design, Data | 必要時 |
| インフラ | Infra, SRE, Platform, DBA | インフラ構築時 |
| 品質 | QA, Review, Bar Raiser, Test Auto, Performance | 規模依存 |
| セキュリティ | Security, Red Team, Compliance | 認証/デプロイ時 |
| 運用 | Ops, Incident Commander | 障害対応時 |
| ドキュメント | Docs Engineer | 納品時 |

### 自動スケーリング

```
「バグ直して」       → S（3名）: PM + tech-lead + qa
「ログイン機能追加」  → M（8名）: + backend + security + review
「ECサイト作って」   → L（16名）: 全部門から招集
「本番デプロイ」     → XL（24名）: 全ロールフル稼働
「本番が504」       → Ops（6名）: 障害対応モード
```

## 品質パイプライン（11スクリプト）

claude-crewの心臓部。AIが生成したコードを**出荷前に多段検証**する：

### 1. Hallucination Guard
```bash
./scripts/hallucination-guard.sh
```
AIが「もっともらしいが存在しないもの」を作る問題を解決：
- npmレジストリにパッケージが実在するか確認
- import文とpackage.jsonの整合性チェック
- API呼び出しのメソッド名・シグネチャ検証

### 2. Build & Verify
```bash
./scripts/build-verify.sh
```
3段階の実行検証：
- **Build Gate**: ビルドが通るか
- **Test Gate**: テストが全パスするか
- **Lint Gate**: リンターエラーがないか

### 3. AI Code Review
```bash
./scripts/ai-code-review.sh
```
5つのAIエージェントが並行レビュー：
- Bug Detective: ロジックエラー、null参照
- Security Auditor: OWASP Top 10
- Performance Reviewer: N+1、メモリリーク
- Code Quality: SOLID、DRY
- Hallucination Detector: 架空のAPI参照

### 4. その他
- `project-analyzer.sh` — 技術スタック自動検出
- `dependency-compat.sh` — 依存関係互換性チェック
- `doc-verifier.sh` — README vs コード整合性
- `evidence-store.sh` — 検証エビデンスの保存
- `client-deliverables.sh` — クライアント納品資料自動生成
- `incident-analyzer.sh` — ログ分析・根本原因推定
- `change-impact.sh` — 変更影響範囲の依存グラフ分析

## 運用保守モード（Phase 11）

障害対応や設定変更も対応：

```
あなた: 「本番が504返してる」

🔧 Phase 11a: 現状調査
  incident-analyzer.sh でログ分析
  → CPU spike → Connection pool exhausted → N+1 query

🔧 Phase 11b: 修正
  tech-lead が最小限の修正を実施
  hallucination-guard.sh + build-verify.sh で検証

🔧 Phase 11c: 報告
  COE（5 Whys分析）を自動生成
  再発防止策を提案
```

## インストール方法

```bash
# 方法1: インストーラー
git clone https://github.com/mattyopon/claude-crew.git
cd claude-crew
./install.sh ~/your-project

# 方法2: 手動コピー
cp CLAUDE.md ~/your-project/
cp -r scripts/ ~/your-project/.claude-crew/scripts/
cp -r agents/ ~/your-project/.claude-crew/agents/
```

インストール後はClaude Codeを開いて、好きな指示を出すだけ。CLAUDE.mdを読んで自動的にAgent Teamモードが起動します。

## フリーランスエンジニアとして

自分はフリーランスのクラウドインフラエンジニアです。一人で案件をこなす中で、「チーム開発の品質を一人で出すにはどうすればいいか」をずっと考えていました。

GAFAM各社のエンジニアリングブログを読み漁り、良いプラクティスをCLAUDE.mdに落とし込み、品質パイプラインのスクリプトを書き、AIエージェントに役割を与えて...気づいたら24ロール・12フェーズの開発チームができていました。

**一人でも、チーム開発の品質は出せる。AIが相互チェックする仕組みさえあれば。**

## まとめ

- **claude-crew** = Claude Code用のAI開発チームフレームワーク
- 24ロール・9部門・12フェーズ
- GAFAM5社 + Anthropicの開発プラクティスを内蔵
- 11の品質パイプラインスクリプト
- APIキー不要、60秒でインストール
- 構築モード + 運用保守モード対応

https://github.com/mattyopon/claude-crew

スターもらえると励みになります ⭐
