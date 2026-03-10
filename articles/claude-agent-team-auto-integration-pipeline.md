---
title: "Claude Agent Team 進化録 ― Enterprise機能を無料で再現し、新機能を自動で取り込む仕組みを作った"
emoji: "🔄"
type: "tech"
topics: ["claudecode", "ai", "security", "automation", "devops"]
published: true
---

## TL;DR

[前回の記事](https://zenn.dev/mattyopon/articles/claude-agent-team-gafam-enterprise)では、GAFAM + Anthropic の開発プラクティスを統合した24ロール・10フェーズの AI 開発チームを構築しました。

今回はその続編として、以下の3つの進化を実装しました。

1. **Enterprise 機能の自前再現**: Claude Code Review（$15-25/PR）と Claude Code Security（Enterprise 限定）を無料で再現
2. **フェーズへの自動実行統合**: 再現したツールを10フェーズの品質ゲートに自動組み込み
3. **自動導入パイプライン**: 新機能を検出→評価→実装→統合まで全自動で行う仕組み

結果として、**Enterprise プランでしか使えない機能を無料で手に入れ**、さらに**今後の新機能も自動で取り込まれる自己進化型のシステム**が完成しました。

## 背景：Enterprise の壁

### Claude Code の有料機能

Anthropic は Claude Code に対して、いくつかの有料・プラン限定機能を提供しています。

```
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│  Claude Code Review                                          │
│  ├── 価格: $15-25 / PR（Team / Enterprise プラン）          │
│  ├── 機能: AI によるコードレビュー、PR へのコメント投稿     │
│  └── 制限: 無料プランでは利用不可                           │
│                                                              │
│  Claude Code Security                                        │
│  ├── 価格: Enterprise プラン限定                             │
│  ├── 機能: セキュリティ脆弱性の自動スキャン                 │
│  └── 制限: Enterprise 以外では利用不可                      │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

個人開発者がこれらを使おうとすると、PR ごとに $15-25 かかったり、そもそも Enterprise プランに加入する必要があります。

### 「自分で作ればいいのでは？」

前回の記事で構築した Agent Team システムには、すでに以下の素地がありました。

- Phase 5（コードレビュー）: LGTM + Bar Raiser の2段階レビュー
- Phase 3（STRIDE）: Microsoft SDL ベースの脅威モデリング
- Phase 7（Red Teaming）: Anthropic 式の敵対的テスト

これらのフェーズに **専用のツールを統合** すれば、Enterprise 機能と同等の品質チェックが実現できるはず。そう考えて、2つのツールを自作しました。

## 1. Enterprise 機能の自前再現

### AI Code Review（Claude Code Review の代替）

Claude Code Review は PR に対して AI がレビューコメントを投稿する機能です。Team/Enterprise プランで $15-25/PR。

これを **4つの AI エージェントによる並行レビュー** として再現しました。

#### アーキテクチャ

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│        ai-code-review.sh                                        │
│        (/home/user/scripts/ai-code-review.sh)                   │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │              │  │              │  │              │          │
│  │     入力     │  │  PR番号指定  │  │  diff指定    │          │
│  │     方式     │  │  (GitHub)    │  │  (ローカル)  │          │
│  │              │  │              │  │              │          │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘          │
│         │                 │                 │                   │
│         └─────────────────┴─────────────────┘                   │
│                           │                                     │
│                    ┌──────▼──────┐                               │
│                    │ diff取得    │                               │
│                    │ (gh/git)    │                               │
│                    └──────┬──────┘                               │
│                           │                                     │
│              ┌────────────┼────────────┬────────────┐           │
│              │            │            │            │           │
│              ▼            ▼            ▼            ▼           │
│     ┌──────────────┐┌──────────────┐┌──────────────┐┌────────┐ │
│     │ Bug          ││ Security     ││ Performance  ││ Code   │ │
│     │ Detective    ││ Auditor      ││ Reviewer     ││Quality │ │
│     │              ││              ││              ││        │ │
│     │ ロジック     ││ OWASP Top10  ││ N+1問題      ││ SOLID  │ │
│     │ null参照     ││ STRIDE       ││ メモリリーク  ││ DRY    │ │
│     │ リソース     ││ 認証/認可    ││ 不要な計算    ││ 複雑度 │ │
│     │ リーク       ││ インジェクション││ キャッシュ   ││ 命名   │ │
│     └──────┬───────┘└──────┬───────┘└──────┬───────┘└───┬────┘ │
│            │              │              │            │        │
│            └──────────────┴──────────────┴────────────┘        │
│                           │                                     │
│                    ┌──────▼──────┐                               │
│                    │  結果統合   │                               │
│                    │ 重大度判定  │                               │
│                    └──────┬──────┘                               │
│                           │                                     │
│              ┌────────────┼────────────┐                        │
│              ▼            ▼            ▼                        │
│     ┌──────────────┐┌──────────────┐┌──────────────┐           │
│     │ 標準出力     ││ PRコメント   ││ JSONレポート  │           │
│     │ (デフォルト)  ││ (--post)     ││ (--json)     │           │
│     └──────────────┘└──────────────┘└──────────────┘           │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

#### 4つのレビューエージェント

| エージェント | 検出対象 | 公式機能との対応 |
|------------|---------|----------------|
| **Bug Detective** | ロジックエラー、null 参照、リソースリーク、型不整合 | Claude Code Review のバグ検出 |
| **Security Auditor** | OWASP Top 10、STRIDE、認証/認可の欠陥、インジェクション | Claude Code Security の脆弱性検出 |
| **Performance Reviewer** | N+1 クエリ、メモリリーク、不要な再計算、キャッシュ戦略 | Claude Code Review のパフォーマンス指摘 |
| **Code Quality** | SOLID 原則違反、DRY 違反、循環的複雑度、命名規則 | Claude Code Review の品質指摘 |

ポイントは **4つのエージェントが並行で動く** こと。公式の Claude Code Review が1つの視点でレビューするのに対し、こちらは4つの専門視点で同時にレビューするので、より多角的なフィードバックが得られます。

#### 使い方

```bash
# 基本: PR番号を指定してレビュー（結果は標準出力）
/home/user/scripts/ai-code-review.sh 42

# PRにレビューコメントを自動投稿
/home/user/scripts/ai-code-review.sh 42 --post

# 特定リポジトリのPRをレビュー
/home/user/scripts/ai-code-review.sh 42 --repo owner/repo --post

# ローカルのdiffファイルをレビュー（PRを作る前の事前チェック）
git diff --staged > /tmp/review.patch
/home/user/scripts/ai-code-review.sh --diff /tmp/review.patch
```

#### 出力例

```
═══════════════════════════════════════════════════════
  AI CODE REVIEW REPORT
  PR #42: Add user authentication feature
═══════════════════════════════════════════════════════

🔴 CRITICAL (2 issues)
──────────────────────────────────────────────────────
[Security Auditor] auth/login.ts:45
  SQL injection vulnerability in user lookup query.
  Raw user input is interpolated into SQL string.
  → Fix: Use parameterized queries.

[Bug Detective] auth/session.ts:23
  Session token stored in localStorage without encryption.
  XSS attack could steal session tokens.
  → Fix: Use httpOnly cookies instead.

🟠 HIGH (3 issues)
──────────────────────────────────────────────────────
[Performance Reviewer] api/users.ts:78
  N+1 query detected in user list endpoint.
  Each user triggers a separate role lookup query.
  → Fix: Use eager loading (JOIN or include).

[Security Auditor] auth/password.ts:12
  Password hashing uses MD5 instead of bcrypt/argon2.
  → Fix: Use bcrypt with cost factor >= 12.

[Code Quality] auth/login.ts:30-85
  Function exceeds cyclomatic complexity threshold (15).
  → Fix: Extract validation and token generation into
         separate functions.

🟡 MEDIUM (5 issues)  |  🔵 LOW (8 issues)

──────────────────────────────────────────────────────
SUMMARY: 2 Critical, 3 High, 5 Medium, 8 Low
VERDICT: ❌ CHANGES REQUESTED (Critical/High must be fixed)
══════════════════════════════════════════════════════
```

#### コスト比較

| 項目 | Claude Code Review（公式） | AI Code Review（自前） |
|------|--------------------------|----------------------|
| 価格 | $15-25 / PR | $0（Claude Code の通常利用分のみ） |
| プラン | Team / Enterprise | 全プラン |
| レビュー観点 | 1エージェント | **4エージェント並行** |
| PR コメント投稿 | 対応 | 対応（`--post` フラグ） |
| ローカル diff | 非対応 | **対応**（`--diff` フラグ） |
| カスタマイズ | 不可 | **自由にカスタマイズ可** |

### /security-review スキル（Claude Code Security の代替）

Claude Code Security は Enterprise 限定のセキュリティスキャン機能。これを **5段階の脆弱性スキャンスキル** として再現しました。

#### 5段階プロセス

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│  /security-review スキル                                        │
│  (/home/user/.claude/skills/security-review.md)                 │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ Stage 1: コード収集                                     │    │
│  │ → 対象ファイルの特定（言語・フレームワーク検出）       │    │
│  │ → git diff / staged changes の取得                      │    │
│  │ → 分析スコープの決定                                    │    │
│  └────────────────────┬────────────────────────────────────┘    │
│                       ▼                                         │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ Stage 2: 脆弱性スキャン                                 │    │
│  │ → OWASP Top 10 チェック                                 │    │
│  │   (A01:アクセス制御 〜 A10:SSRF)                        │    │
│  │ → STRIDE ベースの脅威チェック                           │    │
│  │   (なりすまし/改ざん/否認/情報漏洩/DoS/特権昇格)       │    │
│  │ → 追加チェック                                          │    │
│  │   (ハードコード秘密鍵/安全でない乱数/ログ注入 etc.)    │    │
│  └────────────────────┬────────────────────────────────────┘    │
│                       ▼                                         │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ Stage 3: 偽陽性フィルタリング ← ★ここが差別化ポイント │    │
│  │ → データフロー追跡: 入力値がサニタイズされているか     │    │
│  │ → コンテキスト分析: テストコードは除外                  │    │
│  │ → フレームワーク認識: Railsのparams等は自動保護        │    │
│  │ → 到達可能性分析: 攻撃者が到達できるパスか             │    │
│  └────────────────────┬────────────────────────────────────┘    │
│                       ▼                                         │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ Stage 4: 重大度ランク付け                               │    │
│  │ → CRITICAL: リモートコード実行、認証バイパス            │    │
│  │ → HIGH:     SQLi、Stored XSS、権限昇格                 │    │
│  │ → MEDIUM:   Reflected XSS、CSRF                         │    │
│  │ → LOW:      ベストプラクティス違反                       │    │
│  │ → INFO:     参考情報                                     │    │
│  └────────────────────┬────────────────────────────────────┘    │
│                       ▼                                         │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ Stage 5: 修正パッチの提案                               │    │
│  │ → CRITICAL/HIGH のみ修正コードを自動生成                │    │
│  │ → 修正前後の diff を提示                                │    │
│  │ → 修正の副作用を分析                                    │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

#### Stage 3 の偽陽性フィルタリングが重要

一般的なセキュリティスキャナーの最大の問題は **偽陽性（False Positive）の多さ** です。「危険！」と大量にアラートが出るけど、実際に調べると問題ないものばかり — これでは開発者はアラートを無視するようになります。

Stage 3 では以下の4つの手法で偽陽性を削減します。

```
偽陽性フィルタリング4手法
────────────────────────────────────────────────────

1. データフロー追跡
   入力 → サニタイズ → 出力 のフローを追跡
   例: req.body.name → sanitize(name) → db.query(name)
   → サニタイズ済みなのでSQLi報告は偽陽性と判定

2. コンテキスト分析
   テストコード、モックデータ、開発用設定は除外
   例: test/fixtures/dummy-password.ts
   → テスト用のハードコードパスワードは偽陽性

3. フレームワーク認識
   主要フレームワークの自動保護機能を認識
   例: Rails の params.permit(:name, :email)
   → Strong Parameters で保護済み → Mass Assignment は偽陽性

4. 到達可能性分析
   攻撃者が実際に到達できるパスかを検証
   例: 内部専用の管理APIで、VPN経由でのみアクセス可能
   → 外部攻撃者は到達不可 → 重大度を下げる
```

### GitHub Actions テンプレート

CI/CD パイプラインに組み込むための GitHub Actions テンプレートも作成しました。

```yaml
# /home/user/scripts/ai-code-review-action.yml
# .github/workflows/ にコピーして使用

name: AI Code Review
on:
  pull_request:
    types: [opened, synchronize]

jobs:
  ai-review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Get PR diff
        run: |
          gh pr diff ${{ github.event.pull_request.number }} > /tmp/pr.diff
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}

      - name: Run AI Code Review
        run: |
          ./scripts/ai-code-review.sh \
            ${{ github.event.pull_request.number }} --post
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}

  security-scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Run Security Review
        run: |
          claude --skill /security-review \
            --target . \
            --output /tmp/security-report.json

      - name: Check Critical Issues
        run: |
          CRITICAL=$(jq '.critical | length' /tmp/security-report.json)
          if [ "$CRITICAL" -gt 0 ]; then
            echo "::error::$CRITICAL critical vulnerabilities found!"
            exit 1
          fi
```

Security Review 用の Actions テンプレートも同様に用意しました。

```yaml
# /home/user/scripts/ai-security-review-action.yml

name: AI Security Review
on:
  pull_request:
    paths:
      - 'src/**'
      - 'api/**'
      - 'auth/**'
  schedule:
    - cron: '0 3 * * 1'  # 毎週月曜3時に定期スキャン

jobs:
  security-review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Full Security Scan
        run: |
          claude --skill /security-review \
            --target . \
            --format markdown \
            --output security-report.md

      - name: Upload Report
        uses: actions/upload-artifact@v4
        with:
          name: security-report
          path: security-report.md
```

## 2. フェーズへの自動実行統合

ツールを作っただけでは意味がありません。前回構築した10フェーズの開発フローに **自動的に組み込む** ことが重要です。

### 統合箇所

```
Phase 0   規模判定・DRI任命
Phase 1   Working Backwards (PR/FAQ)
Phase 2   Design Doc & RFC
Phase 3   Threat Modeling (STRIDE)       ← 🔒 /security-review 自動実行
Phase 4   実装 (Feature Flag駆動)
Phase 5   LGTM + Bar Raiser Review       ← 🔍 ai-code-review.sh 自動実行
Phase 6   Testing Pyramid (70/20/10)
Phase 7   Red Teaming                    ← 🔒 /security-review 再スキャン
Phase 8   InfraSim 障害耐性評価
Phase 9   SLO/SLI & Error Budget
Phase 10  COE + Blameless Postmortem
```

### Phase 3: STRIDE + /security-review

Phase 3 はもともと Microsoft SDL ベースの脅威モデリングフェーズでした。ここに `/security-review` スキルを自動実行として組み込みます。

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│  Phase 3: Threat Modeling（更新後）                             │
│                                                                 │
│  1. セキュリティエンジニアが STRIDE 分析を実施（従来通り）     │
│     → データフロー図 → 脅威の列挙 → 緩和策の策定              │
│                                                                 │
│  2. /security-review スキルを自動実行（★新規追加）             │
│     → Stage 1: コード収集・分析範囲の特定                      │
│     → Stage 2: OWASP Top 10 + STRIDE ベースのスキャン          │
│     → Stage 3: 偽陽性フィルタリング                            │
│     → Stage 4: 重大度ランク付け                                │
│                                                                 │
│  3. 結果の反映                                                  │
│     → CRITICAL/HIGH → 実装前に修正方針を確定（ブロッカー）    │
│     → MEDIUM/LOW → Design Doc に注意事項として記録             │
│     → Phase 4 の実装時にセキュリティ対策を反映                 │
│                                                                 │
│  意味: 「設計段階で脆弱性を潰す」= Shift Left Security        │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

設計段階でセキュリティスキャンを実行することで、**実装に入る前に脆弱性のリスクを把握** できます。いわゆる「Shift Left Security」の実践です。

### Phase 5: AI Code Review + LGTM + Bar Raiser

Phase 5 のコードレビューフェーズに `ai-code-review.sh` を組み込みます。

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│  Phase 5: コードレビュー（更新後）                              │
│                                                                 │
│  Step 1: AI Code Review 自動実行（★新規追加）                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ ai-code-review.sh <PR番号>                              │    │
│  │                                                         │    │
│  │  Bug Detective ──┐                                      │    │
│  │  Security Auditor ┼─→ 統合レポート → CRITICAL/HIGH 判定 │    │
│  │  Performance ─────┤                                      │    │
│  │  Code Quality ────┘                                      │    │
│  │                                                         │    │
│  │  CRITICAL/HIGH が 0 件 → Step 2 へ進む                  │    │
│  │  CRITICAL/HIGH が 1件以上 → 担当 DRI が修正 → 再実行   │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                 │
│  Step 2: LGTM レビュー（従来通り）                             │
│  → レビューエンジニアが AI レビュー結果も参照しながら手動確認 │
│  → Readability チェック + LGTM 承認                            │
│                                                                 │
│  Step 3: Bar Raiser レビュー（L規模以上、従来通り）            │
│  → Well-Architected 6本柱での独立評価                          │
│  → Veto 権あり                                                 │
│                                                                 │
│  Gate 通過条件（更新後）:                                      │
│  ✅ AI Code Review の CRITICAL/HIGH = 0                        │
│  ✅ レビューエンジニアの LGTM 取得                              │
│  ✅ 未解決コメント = 0                                          │
│  ✅ Bar Raiser の APPROVE（L規模以上）                          │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

重要なのは、**AI Code Review はあくまで1次フィルター** であること。AI レビューで見つからない設計上の問題や、コンテキストに依存する判断は、人間（レビューエンジニア/Bar Raiser）が担います。

### Phase 7: Red Teaming + /security-review 再スキャン

Phase 7 の Red Teaming フェーズでは、`/security-review` を **2回目** 実行します。

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│  Phase 7: Red Teaming（更新後）                                │
│                                                                 │
│  Step 1: /security-review 再スキャン（★新規追加）              │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ Phase 3（設計段階）と Phase 7（実装完了後）の diff       │    │
│  │                                                         │    │
│  │ Phase 3 スキャン結果:                                   │    │
│  │   → 設計段階で検出された脆弱性 A, B, C                  │    │
│  │                                                         │    │
│  │ Phase 7 再スキャン結果:                                 │    │
│  │   → 脆弱性 A: 緩和策が実装済み ✅                       │    │
│  │   → 脆弱性 B: 緩和策が不完全 ⚠️  → 修正指示           │    │
│  │   → 脆弱性 D: 実装中に新たに混入 🔴 → 修正必須        │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                 │
│  Step 2: レッドチームエンジニアの攻撃シミュレーション          │
│  → /security-review の結果を参照しつつ手動で攻撃を試行       │
│  → OWASP Top 10 ベースの攻撃パターン実行                     │
│  → 多回試行攻撃（Multi-Attempt Attack）                      │
│                                                                 │
│  Step 3: 統合レポート                                          │
│  → /security-review 自動スキャン + 手動攻撃結果を統合        │
│  → Critical/High → 即修正 → Gate 4 再実行                   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

Phase 3 と Phase 7 で2回スキャンすることで、**設計段階で検出した脆弱性が正しく修正されたか** と **実装中に新たに混入した脆弱性がないか** の両方を検証できます。

### 更新後の品質ゲート全体像

```
┌──────────────────────────────────────────────────────────────────┐
│                                                                  │
│  ═══════════════════════════════════════════════════════         │
│  Gate 1: AI Code Review + LGTM Review                           │
│  ═══════════════════════════════════════════════════════         │
│                                                                  │
│  Phase 5a  ai-code-review.sh 自動実行 ← ★NEW                  │
│     → 4エージェント並行レビュー                                 │
│     → CRITICAL/HIGH = 0 が通過条件                              │
│  Phase 5b  レビューエンジニアが LGTM レビュー                   │
│     → AI レビュー結果を参照しつつ手動レビュー                   │
│           │                                                      │
│           ├── LGTM + AI CRITICAL/HIGH = 0 → Gate 2 へ          │
│           └── 要修正 → 担当 DRI が修正 → 再レビュー            │
│                                                                  │
│  ═══════════════════════════════════════════════════════         │
│  Gate 2: Bar Raiser Review（L規模以上）                         │
│  ═══════════════════════════════════════════════════════         │
│                                                                  │
│  （従来通り — Well-Architected 6本柱チェック）                  │
│           │                                                      │
│           ├── APPROVE → Gate 3 へ                               │
│           └── VETO → Gate 1 から再実行                          │
│                                                                  │
│  ═══════════════════════════════════════════════════════         │
│  Gate 3: Testing Pyramid（70/20/10）                            │
│  ═══════════════════════════════════════════════════════         │
│                                                                  │
│  （従来通り — Unit 70% / Integration 20% / E2E 10%）           │
│           │                                                      │
│           ├── ALL PASS → Gate 4 へ                              │
│           └── FAIL → 修正 → 再テスト                            │
│                                                                  │
│  ═══════════════════════════════════════════════════════         │
│  Gate 4: /security-review + Red Team                            │
│  ═══════════════════════════════════════════════════════         │
│                                                                  │
│  Phase 7a  /security-review 再スキャン ← ★NEW                  │
│     → Phase 3 結果との差分比較                                  │
│     → 新規脆弱性の検出                                         │
│  Phase 7b  レッドチームエンジニアが攻撃シミュレーション         │
│     → /security-review 結果を参照しつつ手動攻撃                │
│           │                                                      │
│           ├── 脆弱性なし/Low → Gate 5 へ                        │
│           └── Critical/High → 修正 → Gate 4 再実行             │
│                                                                  │
│  ═══════════════════════════════════════════════════════         │
│  Gate 5: InfraSim 障害耐性（インフラ構築時）                    │
│  ═══════════════════════════════════════════════════════         │
│                                                                  │
│  （従来通り — 150+ シナリオの障害シミュレーション）             │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

## 3. 自動導入パイプライン（Auto-Integration Pipeline）

ここまでの「Enterprise 機能の再現」と「フェーズ統合」は、手動で設計・実装しました。でも、Anthropic や競合ツールは常に新機能をリリースしています。**毎回手動で対応するのは非現実的** です。

そこで、**新機能の検出→評価→実装→統合を全自動で行うパイプライン** を構築しました。

### パイプライン全体像

```
┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│    ⚡ AUTO-INTEGRATION PIPELINE                                    │
│       ~ 新機能を自動で取り込む自己進化システム ~                   │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                                                             │    │
│  │  ① 検出（毎朝 6:03 AM 自動実行）                          │    │
│  │                                                             │    │
│  │  日次リサーチ cron が以下をスキャン:                        │    │
│  │                                                             │    │
│  │  ┌── GAFAM + Anthropic ──┐  ┌── 競合ツール ──────────┐     │    │
│  │  │ Google Engineering    │  │ Cursor                 │     │    │
│  │  │ AWS Blog              │  │ GitHub Copilot         │     │    │
│  │  │ Engineering at Meta   │  │ Windsurf               │     │    │
│  │  │ Microsoft DevBlog     │  │ Devin                  │     │    │
│  │  │ Apple ML Research     │  │ Replit Agent            │     │    │
│  │  │ Anthropic Blog        │  │                        │     │    │
│  │  └───────────────────────┘  └────────────────────────┘     │    │
│  │                                                             │    │
│  └──────────────────────────┬──────────────────────────────────┘    │
│                             ▼                                       │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                                                             │    │
│  │  ② バイアス防止チェック（3項目ゲート）                     │    │
│  │                                                             │    │
│  │  □ 必要性の証明                                            │    │
│  │    「この機能がないと具体的に何が困るか」を1つ以上挙げる   │    │
│  │    → 挙がらない場合は中止                                  │    │
│  │                                                             │    │
│  │  □ 重複チェック                                            │    │
│  │    既存ツールで80%以上カバーできないか検証                  │    │
│  │    → カバー可能なら中止                                    │    │
│  │                                                             │    │
│  │  □ 複雑性の代償                                            │    │
│  │    現在のツール総数が15本を超過していないか確認             │    │
│  │    → 超過している場合、まず統合・廃止を先に実施            │    │
│  │                                                             │    │
│  │  3項目すべて Yes → ③ へ進む                                │    │
│  │                                                             │    │
│  └──────────────────────────┬──────────────────────────────────┘    │
│                             ▼                                       │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                                                             │    │
│  │  ③ 7軸スコアリング評価（35点満点）                        │    │
│  │                                                             │    │
│  │  品質向上インパクト      [1-5]  ───┐                       │    │
│  │  コスト削減効果          [1-5]  ───┤                       │    │
│  │  フェーズ適合度          [1-5]  ───┤                       │    │
│  │  実装難易度（逆転）      [1-5]  ───┼─→ 合計スコア算出     │    │
│  │  普及度・信頼性          [1-5]  ───┤                       │    │
│  │  既存ツールとの差分      [1-5]  ───┤                       │    │
│  │  保守コスト              [1-5]  ───┘                       │    │
│  │                                                             │    │
│  └──────────────────────────┬──────────────────────────────────┘    │
│                             ▼                                       │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                                                             │    │
│  │  ④ 判定                                                    │    │
│  │                                                             │    │
│  │  28-35点 → INTEGRATE   → ⑤⑥⑦ を実行                    │    │
│  │  21-27点 → RECOMMEND   → ログに設計案を記録               │    │
│  │  14-20点 → WATCH       → ウォッチリストで監視             │    │
│  │   0-13点 → SKIP        → ログ記録のみ                     │    │
│  │                                                             │    │
│  └──────────────────────────┬──────────────────────────────────┘    │
│                             ▼                                       │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                                                             │    │
│  │  ⑤ 実装（自動）                                           │    │
│  │                                                             │    │
│  │  機能タイプに応じて実装形式を自動決定:                     │    │
│  │                                                             │    │
│  │  コードレビュー系 → Shell Script                           │    │
│  │                      /home/user/scripts/{name}.sh          │    │
│  │                                                             │    │
│  │  セキュリティ系   → Claude Code Skill                      │    │
│  │                      ~/.claude/skills/{name}.md            │    │
│  │                                                             │    │
│  │  CI/CD連携系      → GitHub Actions YAML                    │    │
│  │                      /home/user/scripts/{name}-action.yml  │    │
│  │                                                             │    │
│  │  プロセスルール系 → CLAUDE.md 直接追記                     │    │
│  │                                                             │    │
│  │  MCP連携系        → Wrapper Script                         │    │
│  │                      /home/user/scripts/mcp-{name}.sh      │    │
│  │                                                             │    │
│  └──────────────────────────┬──────────────────────────────────┘    │
│                             ▼                                       │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                                                             │    │
│  │  ⑥ フェーズ統合（4箇所を自動更新）                        │    │
│  │                                                             │    │
│  │  a. 該当 Phase の手順に実行指示を追加                      │    │
│  │  b. 品質ゲートのフローチャートに反映                       │    │
│  │  c. サブエージェント指示テンプレートを追加                  │    │
│  │  d. 再現済み機能テーブルに追加                              │    │
│  │                                                             │    │
│  └──────────────────────────┬──────────────────────────────────┘    │
│                             ▼                                       │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                                                             │    │
│  │  ⑦ 検証 + 効果測定                                        │    │
│  │                                                             │    │
│  │  即時: 構文チェック・整合性チェック・重複最終確認          │    │
│  │  30日後: 効果測定 → 未使用/誤検知過多/重複 → 休止        │    │
│  │                                                             │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### バイアス防止チェック：「新しいもの好き」の罠を防ぐ

エンジニアはよく「新しいツール」を見つけると、すぐ導入したくなります。しかし、ツールが増えすぎるとかえって複雑性が増し、保守コストが跳ね上がります。

バイアス防止チェックは **3つの質問** で「本当に必要か」を検証します。

```
バイアス防止チェック: 3つの質問
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Q1: 必要性の証明
    「この機能がないと、具体的にどんな問題が起きるか？」
    → 具体例が1つも挙がらない → 導入中止
    → 理由: 「あったら便利」は導入理由にならない

Q2: 重複チェック
    「既存のツールで80%以上カバーできないか？」
    → カバー可能 → 導入中止
    → 理由: 似た機能のツールが2つあると混乱する

Q3: 複雑性の代償
    「現在のツール数は15本以下か？」
    → 15本超過 → まず統合・廃止を実施
    → 理由: ツール数には上限がある。増やすなら先に減らす

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

ツール数の上限を **15本** に設定しているのが特徴です。これは Netflix の「Two-Pizza Team」（ピザ2枚で足りるチームサイズが最適）の考え方に似ています。ツールも多すぎると管理しきれなくなるので、上限を設けて **質を維持** します。

### 7軸スコアリングマトリクス

バイアス防止チェックを通過したら、7つの軸で定量評価します。

| 評価軸 | 1点 | 3点 | 5点 |
|--------|-----|-----|-----|
| **品質向上インパクト** | ほぼ変わらない | 一部工程が改善 | 全体の品質水準が向上 |
| **コスト削減効果** | 無料機能の代替 | 有料機能の代替 | Enterprise 限定の代替 |
| **フェーズ適合度** | 既存に合わない | 既存を補完 | 既存の弱点を解消 |
| **実装難易度（逆転）** | 非常に複雑 | 中程度 | シンプル |
| **普及度・信頼性** | 実験段階 | 1社が本番採用 | 2社以上が標準採用 |
| **既存ツールとの差分** | 既存で代替可能 | 一部重複するが独自価値 | 既存では不可能 |
| **保守コスト** | 頻繁な更新が必要 | 年数回の更新 | ほぼメンテフリー |

#### スコアリング例：今回の AI Code Review

```
AI Code Review（ai-code-review.sh）のスコアリング例
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

品質向上インパクト:    5  全体の品質水準が向上（4視点同時レビュー）
コスト削減効果:        4  有料機能（$15-25/PR）の代替
フェーズ適合度:        5  Phase 5 の弱点（手動レビューの限界）を解消
実装難易度（逆転）:    4  Shell Script + Claude CLI で比較的シンプル
普及度・信頼性:        3  Anthropic が公式提供（1社が本番採用）
既存ツールとの差分:    5  既存の手動レビューでは不可能な並行4視点
保守コスト:            4  Claude CLI のアップデートに追従するだけ

合計: 30 / 35 → INTEGRATE 判定（28点以上）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### 判定基準

| スコア | 判定 | アクション |
|--------|------|----------|
| **28-35** | INTEGRATE | 即実装。⑤⑥⑦ を全て実行 |
| **21-27** | RECOMMEND | ログに設計案を記録し、次回の手動レビューで提案 |
| **14-20** | WATCH | ウォッチリストに追加し、継続監視 |
| **0-13** | SKIP | ログに記録するだけで終了 |

INTEGRATE のしきい値を28点（80%）に設定しています。これはかなり高いハードルで、「本当に価値がある」と判断されたものだけが自動導入されます。

### 30日後の効果測定と撤退基準

導入して終わりではありません。**30日後に必ず効果測定** を行い、期待通りの成果が出ていなければ撤退します。

```
30日後の効果測定
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

チェック項目:
  1. 使用頻度: フェーズ実行時に何回利用されたか
  2. 検出精度: 出力が実際に有用だったか（偽陽性率）
  3. 既存との重複: 他のツールと同じ結果を出していないか
  4. 動作安定性: エラーなく動作しているか

撤退基準（1つでも該当すれば休止）:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ❌ 未使用:     30日間でフェーズ実行ゼロ
  ❌ 誤検知過多: 出力の大半が偽陽性
  ❌ 重複発覚:   既存ツールと同じ結果
  ❌ 保守不能:   エラーで動作停止

休止アクション:
  → /home/user/scripts/_archived/ に移動
  → CLAUDE.md の該当セクションを削除
  → 品質ゲートのフローチャートから除去
```

### 実装形式の自動判定

新機能の性質に応じて、最適な実装形式を自動で判定します。

```
機能タイプ → 実装形式の自動判定ルール
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

コードレビュー・解析系
  → Shell Script → /home/user/scripts/{name}.sh
  例: ai-code-review.sh

セキュリティスキャン系
  → Claude Code Skill → ~/.claude/skills/{name}.md
  例: security-review.md

CI/CD連携系
  → GitHub Actions YAML → /home/user/scripts/{name}-action.yml
  例: ai-code-review-action.yml, ai-security-review-action.yml

開発プロセスルール系
  → CLAUDE.md に直接追記
  例: Phase の手順変更、品質ゲートの条件変更

MCP連携系
  → Wrapper Script → /home/user/scripts/mcp-{name}.sh
  例: 外部 MCP サーバーとの連携スクリプト
```

### 現在の再現済み機能

パイプラインを通じて、現時点で以下の Enterprise 機能を再現しています。

| 公式機能 | 価格/プラン | 自前再現 | 統合 Phase |
|---------|------------|---------|-----------|
| Claude Code Review | $15-25/PR (Team/Enterprise) | AI Code Review（4エージェント並行） | Phase 5 |
| Claude Code Security | Enterprise 限定 | /security-review（5段階検証） | Phase 3, 7 |
| Security Review Action | Enterprise 限定 | AI Security Review Action | CI/CD |

### 日次 cron の設定

パイプラインの起点となる日次リサーチは、cron で毎朝自動実行されます。

```bash
# crontab -l
3 6 * * * /usr/bin/flock -n /tmp/agent-team-research.lock \
  /home/user/scripts/agent-team-daily-research.sh
```

毎朝 6:03 に起動し、以下のソースをスキャンします。

```
スキャン対象（11ソース）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

GAFAM + Anthropic（6社）:
  - Google Engineering Blog / SRE Blog
  - AWS Blog / Amazon Science
  - Engineering at Meta
  - Anthropic Research Blog / Changelog
  - Microsoft DevBlog
  - Apple ML Research

競合ツール（5社）:
  - Cursor（Changelog / Blog）
  - GitHub Copilot（Blog / Changelog）
  - Windsurf（Blog）
  - Devin（Blog / Changelog）
  - Replit Agent（Blog）
```

新機能が検出されると、バイアス防止チェック→7軸スコアリング→判定 が自動実行され、INTEGRATE 判定なら実装・統合まで全自動で進みます。

## システム全体の進化

前回と今回の記事を合わせた、Agent Team システムの全体像を改めて整理します。

```
╔══════════════════════════════════════════════════════════════════════════╗
║                                                                        ║
║    C L A U D E   A G E N T   T E A M   v3.0                          ║
║    ~ 自己進化型 GAFAM + Anthropic 統合モデル ~                        ║
║                                                                        ║
║  ┌──────────────────── コア ──────────────────────┐                    ║
║  │                                                  │                    ║
║  │  24ロール・9部門・10フェーズ                     │  ← 前回          ║
║  │  自動規模判定（S/M/L/XL）                        │  ← 前回          ║
║  │  5ゲート品質システム                              │  ← 前回          ║
║  │  毎朝GAFAM自動リサーチ                           │  ← 前回          ║
║  │                                                  │                    ║
║  ├──────────────── 今回の追加 ────────────────────┤                    ║
║  │                                                  │                    ║
║  │  Enterprise機能の自前再現                        │  ← ★NEW          ║
║  │  ├── AI Code Review（4エージェント並行）        │                    ║
║  │  ├── /security-review（5段階脆弱性スキャン）    │                    ║
║  │  └── GitHub Actions テンプレート                 │                    ║
║  │                                                  │                    ║
║  │  フェーズへの自動実行統合                        │  ← ★NEW          ║
║  │  ├── Phase 3: /security-review 自動実行         │                    ║
║  │  ├── Phase 5: ai-code-review.sh 自動実行        │                    ║
║  │  └── Phase 7: /security-review 再スキャン       │                    ║
║  │                                                  │                    ║
║  │  自動導入パイプライン                            │  ← ★NEW          ║
║  │  ├── バイアス防止チェック（3項目ゲート）        │                    ║
║  │  ├── 7軸スコアリング（35点満点）                │                    ║
║  │  ├── 自動実装・フェーズ統合                     │                    ║
║  │  ├── 30日効果測定 + 撤退基準                    │                    ║
║  │  └── ツール数上限15本                            │                    ║
║  │                                                  │                    ║
║  └──────────────────────────────────────────────────┘                    ║
║                                                                        ║
╚══════════════════════════════════════════════════════════════════════════╝
```

## 設計思想：なぜ「自動導入」に制約をかけるのか

自動導入パイプラインの設計で最も注意したのは、**「何でもかんでも取り込まない」こと** です。

### ツール過多の問題

エンジニアリングの現場でよくある失敗パターンがあります。

```
ツール導入のアンチパターン
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Year 1:  3つのツール → 全員が使いこなせる
Year 2:  8つのツール → 半分くらいしか使われていない
Year 3: 15のツール → どれを使えばいいか分からない
Year 4: 20のツール → 誰もメンテしていないツールがある
Year 5:  ツール整理プロジェクトが立ち上がる → 振り出しに戻る
```

これを防ぐために、以下の3つの制約を設けています。

1. **バイアス防止チェック**: 「本当に必要か」を3つの質問で検証
2. **高いしきい値**: 35点中28点（80%）以上でないと自動導入しない
3. **ツール数上限**: 15本を超えたら、まず統合・廃止を先に行う

### 撤退の仕組み

導入と同じくらい重要なのが **撤退** の仕組みです。30日後の効果測定で成果が出ていなければ、容赦なくアーカイブに移動します。

```
撤退フロー
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. ツールを /scripts/_archived/ に移動
2. CLAUDE.md の該当セクションを削除
3. 品質ゲートのフローチャートから除去
4. サブエージェント指示テンプレートを削除
5. 更新ログに撤退理由を記録

「休止」であって「削除」ではない。
将来的に状況が変われば復活させることもある。
```

これにより、**常に最適なツールセットが維持される** ことを保証しています。

## 実際の運用フロー

ここまでの仕組みが実際にどう動くのか、具体例で見てみましょう。

### ケース1: 普段の開発タスク

```
ユーザー: 「ユーザー管理APIを作って」
  ↓
PM: 規模判定 → M（8名）
  ↓
Phase 0: DRI任命
Phase 1: Working Backwards (PR/FAQ)
Phase 2: Design Doc
Phase 3: STRIDE分析
         └→ /security-review 自動実行          ← ★自動
            → CRITICAL: なし
            → HIGH: 1件（パスワードハッシュの要件不足）
            → Design Docに記録 → 実装時に対応
Phase 4: Feature Flag駆動で実装
Phase 5: コードレビュー
         ├→ ai-code-review.sh 自動実行         ← ★自動
         │  → Bug Detective: LOW 2件
         │  → Security Auditor: HIGH 0件
         │  → Performance: MEDIUM 1件（N+1クエリ）
         │  → Code Quality: LOW 3件
         │  → CRITICAL/HIGH = 0 → 通過
         └→ レビューエンジニアが LGTM
Phase 6: Testing Pyramid (70/20/10)
Phase 10: 完了報告
```

### ケース2: 新機能が検出された朝

```
毎朝 6:03 AM
  ↓
日次リサーチスキャン実行
  → Anthropic Blog: 「Claude Code に dependency audit 機能を追加」
  ↓
バイアス防止チェック:
  □ 必要性: 「依存パッケージの脆弱性を検出できない」→ Yes
  □ 重複:   既存の/security-reviewは依存関係の深い分析はしない → Yes
  □ 複雑性: 現在のツール数 = 3本（上限15以内）→ Yes
  → 3項目すべて通過
  ↓
7軸スコアリング:
  品質向上: 4 / コスト削減: 5 / フェーズ適合: 4
  実装難易度: 4 / 普及度: 3 / 差分: 4 / 保守: 4
  → 合計: 28 → INTEGRATE 判定
  ↓
自動実装:
  → /home/user/scripts/dependency-audit.sh を生成
  ↓
フェーズ統合:
  → Phase 6 のテストフェーズに依存関係チェックを追加
  → 品質ゲートに「既知の脆弱性がある依存関係 = FAIL」を追加
  → サブエージェント指示テンプレートを CLAUDE.md に追加
  → 再現済み機能テーブルに追加
  ↓
更新ログに記録
  ↓
30日後に効果測定予定をセット
```

## 前回との比較

| 項目 | v2.0（前回） | v3.0（今回） |
|------|-------------|-------------|
| コードレビュー | 手動 LGTM のみ | **AI 4エージェント + 手動 LGTM** |
| セキュリティスキャン | STRIDE 分析（手動のみ） | **自動スキャン + 偽陽性フィルタリング** |
| Phase 3 | STRIDE 分析のみ | STRIDE + **/security-review 自動実行** |
| Phase 5 | LGTM + Bar Raiser | **AI Code Review** + LGTM + Bar Raiser |
| Phase 7 | Red Teaming（手動のみ） | **/security-review 再スキャン** + Red Teaming |
| 新機能の取り込み | 手動（毎朝リサーチで情報収集のみ） | **自動（検出→評価→実装→統合）** |
| Enterprise 機能 | 利用不可 | **無料で再現** |
| ツール管理 | なし | **15本上限 + 30日効果測定** |

## 公式 vs 自前：どちらを選ぶべきか

「公式の Enterprise 機能を使えばいいのでは？」という疑問はもっともです。判断基準をまとめます。

### 公式を選ぶべきケース

- チーム全員が Claude Code を使っている
- PR 数が多く、人手でのレビューが追いつかない
- Enterprise プランのコストが許容範囲
- セットアップに時間をかけたくない

### 自前再現を選ぶべきケース

- 個人開発者で、コストを抑えたい
- レビューの観点をカスタマイズしたい（4エージェントの役割を変えるなど）
- CI/CD パイプラインに柔軟に統合したい
- 既存の開発フローに組み込みたい

**結論: 個人開発者やスタートアップなら自前再現、大規模チームなら公式が適切。** ただし、自前再現の利点は「カスタマイズの自由度」にあります。公式機能ではできない4エージェント並行レビューや、フェーズへの自動統合は、自前ならではの強みです。

## 今後の展望

### 自動導入パイプラインの発展

- **A/B テスト**: 新ツールと既存ツールの出力を比較し、客観的に優劣を判定
- **フィードバックループ**: Phase 実行時のログを分析し、スコアリング精度を自己改善
- **マルチリポジトリ対応**: 複数プロジェクトでのツール効果を横断分析

### 再現対象の拡大

- **Cursor の AI Code Completion**: コンテキスト認識型の補完ロジックの再現
- **GitHub Copilot の Code Suggestions**: レビューコメントからの自動修正提案
- **Devin の自律実装**: 複雑なタスクの完全自律実装パイプライン

### コミュニティ展開

- スコアリングマトリクスのテンプレート公開
- GitHub Actions テンプレートの OSS 化
- 再現済み機能のプレイブック公開

## まとめ

前回の記事で構築した Agent Team システムに、3つの進化を加えました。

1. **Enterprise 機能の自前再現**: $15-25/PR の Code Review と Enterprise 限定の Security 機能を無料で再現
2. **フェーズへの自動統合**: Phase 3・5・7 に自動実行を組み込み、品質ゲートを強化
3. **自動導入パイプライン**: 7軸スコアリング + バイアス防止 + 撤退基準で、自己進化するシステムを構築

特に重要なのは3つ目の **自動導入パイプライン** です。これにより、Anthropic や競合ツールが新機能をリリースするたびに手動で対応する必要がなくなりました。**システムが自分自身を進化させる** 仕組みが、これで完成しました。

ただし、「何でも取り込む」のではなく、**バイアス防止チェック（3項目）→ 7軸スコアリング（28点以上）→ 30日効果測定 → ツール数上限15本** という多段階のフィルターを設けています。「増やす仕組み」と「減らす仕組み」の両方がないと、システムは複雑化して崩壊します。

AI エージェントシステムの進化は、**機能を追加すること** ではなく、**必要な機能を自動で見極め、不要になったら自動で撤退する仕組みを作ること** にあると考えています。
