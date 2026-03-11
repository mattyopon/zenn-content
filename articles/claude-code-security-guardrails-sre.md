---
title: "Claude Codeに本番環境を触らせる前に ― SRE視点で構築した5層セキュリティガードレール"
emoji: "🛡️"
type: "tech"
topics: ["claudecode", "security", "sre", "devops", "ai"]
published: true
---

## TL;DR

Claude Codeは強力だが、**何も制限せずに使うと本番DBを消したりバックドア入りOSSを導入するリスクがある**。SREとして8年インフラを守ってきた経験から、Claude Codeに安全に仕事を任せるための**5層セキュリティガードレール**を構築した。AI Code Review、OWASP自動スキャン、STRIDE脅威分析をClaude Code自身に実行させる仕組みで、Enterprise版の有料機能に頼らず無料で実現している。

## なぜこの記事を書いたか

最近、Qiitaで[「Claude Codeにバックドア入りOSSを渡したら、何の疑いもなく実装した」](https://qiita.com/)という記事がトレンド入りした。また[「Claude Codeが本番DBを消した事故」](https://qiita.com/)も話題になった。

これらの記事を読んで「そうだよな」と思った。なぜなら、私自身も似た経験をしているからだ。

### 実際に起きたインシデント

あるプロジェクトで、Claude Codeに「S3バケットのアクセス設定を修正して」と指示した。結果：

- IAMポリシーが `Action: "*"` に変更されていた（全権限付与）
- S3バケットポリシーが `Principal: "*"` になっていた（全世界公開）
- CloudFrontのOAC設定が吹き飛んでいた

幸い、Terraformの`plan`で気づいて`apply`前に止めたが、もし`--auto-approve`を付けていたら公開事故になっていた。

**AIは「動くコード」は書けるが、「安全なコード」を書く保証はない。** ガードレールは人間が作る必要がある。

## 5層セキュリティガードレールの全体像

```
┌─────────────────────────────────────────────────┐
│                                                 │
│  Layer 1: 権限制御                               │
│  └─ CLAUDE.md で禁止操作を定義                   │
│                                                 │
│  Layer 2: 設計段階スキャン（STRIDE）             │
│  └─ 実装前に脅威モデリング                       │
│                                                 │
│  Layer 3: AI Code Review（4エージェント並行）    │
│  └─ Bug / Security / Performance / Quality      │
│                                                 │
│  Layer 4: OWASP自動スキャン                      │
│  └─ 実装後のコードを多段階検証                   │
│                                                 │
│  Layer 5: Infrastructure Guard                   │
│  └─ Terraform plan差分チェック + IAM監査         │
│                                                 │
└─────────────────────────────────────────────────┘
```

各レイヤーが独立して機能し、1つが抜けても他で補完する**多層防御（Defense in Depth）**の設計。

## Layer 1: CLAUDE.mdによる権限制御

最もシンプルだが最も効果的な層。Claude Codeが読む`CLAUDE.md`に明示的な禁止事項を書く。

```markdown
# CLAUDE.md

## 禁止操作
- `terraform apply --auto-approve` は絶対に実行しない
- `terraform destroy` はユーザーの明示的な承認なしに実行しない
- IAMポリシーで `Action: "*"` や `Resource: "*"` を使わない
- S3バケットポリシーで `Principal: "*"` を使わない
- 本番環境のデータベースに対する DELETE / DROP 文を実行しない
- `--force` フラグを安易に使わない

## 必須チェック
- Terraform変更時は必ず `terraform plan` の出力を確認してからapply
- IAMポリシーは最小権限の原則に従う
- セキュリティグループのインバウンドルールで 0.0.0.0/0 を許可しない（HTTP/HTTPS除く）
```

**効果**: Claude Codeはこのルールを高い確率で遵守する。ただし100%ではないので、他のレイヤーが必要。

## Layer 2: STRIDE脅威モデリング（設計段階）

Microsoft SDL由来のSTRIDE分析をClaude Code自身に実行させる。

```
設計レビュー時に以下を自動チェック:

S - Spoofing（なりすまし）
  → 認証はどこで行っているか？バイパス可能な経路はないか？

T - Tampering（改ざん）
  → 入力バリデーションは十分か？SQLインジェクション対策は？

R - Repudiation（否認）
  → 操作ログは記録されているか？改ざん防止は？

I - Information Disclosure（情報漏洩）
  → 機密データがログや画面に露出していないか？

D - Denial of Service（DoS）
  → レート制限は設定されているか？

E - Elevation of Privilege（特権昇格）
  → IAMポリシーは最小権限か？
```

これを自動実行するスキルを作った：

```bash
# /security-review スキルの実行
# 5段階プロセスで自動スキャン
# Stage 1: コード収集
# Stage 2: 脆弱性スキャン（OWASP Top 10 + STRIDE）
# Stage 3: 偽陽性フィルタリング
# Stage 4: 重大度ランク付け
# Stage 5: 修正パッチ提案
```

**ポイント**: 実装前にやること。実装してから「脆弱性がありました」では手戻りが大きい。

## Layer 3: AI Code Review（4エージェント並行レビュー）

Anthropicの有料Code Review機能（$15-25/PR、Team/Enterprise限定）を自前で再現した。

```bash
#!/bin/bash
# ai-code-review.sh - 4つのAIエージェントが並行レビュー

DIFF=$(git diff --staged)

# 4つの観点で並行レビュー
review_bug() {
  # Bug Detective: ロジックエラー、null参照、リソースリーク
  claude --print "以下のdiffからバグを探してください:
    - ロジックエラー
    - null/undefined参照
    - リソースリーク（未クローズのファイル、DB接続等）
    - エッジケースの未処理
    $DIFF"
}

review_security() {
  # Security Auditor: OWASP Top 10 + STRIDE
  claude --print "以下のdiffのセキュリティ脆弱性を検出してください:
    - SQLインジェクション
    - XSS（stored/reflected）
    - CSRF
    - 認証バイパス
    - 機密情報のハードコード
    $DIFF"
}

review_performance() {
  # Performance Reviewer: N+1, メモリリーク
  claude --print "以下のdiffのパフォーマンス問題を検出してください:
    - N+1クエリ
    - 不要なループ内DB呼び出し
    - メモリリーク
    - 不要な再レンダリング
    $DIFF"
}

review_quality() {
  # Code Quality: SOLID, DRY, 複雑度
  claude --print "以下のdiffのコード品質を評価してください:
    - SOLID原則違反
    - DRY原則違反
    - 循環的複雑度が高い関数
    - 命名規則の不一致
    $DIFF"
}

# 並行実行
review_bug &
review_security &
review_performance &
review_quality &
wait
```

**結果の重大度分類**:
- 🔴 **CRITICAL**: リモートコード実行、認証バイパス → **マージ禁止**
- 🟠 **HIGH**: SQLi、XSS(stored)、権限昇格 → **修正必須**
- 🟡 **MEDIUM**: CSRF、XSS(reflected) → **修正推奨**
- 🔵 **LOW**: ベストプラクティス違反 → **改善推奨**

## Layer 4: OWASP自動スキャン（実装後）

Layer 2が設計段階なら、Layer 4は実装後の検証。同じ`/security-review`スキルを再実行するが、今度は**実際のコードに対して**スキャンする。

```
Phase 3（設計段階）のスキャン結果:
  - XSS対策が必要 → Content-Security-Policyヘッダーの追加を推奨
  - 入力バリデーションが必要 → sanitize関数の実装を推奨

Phase 7（実装後）のスキャン結果:
  - ✅ CSPヘッダー: 実装済み
  - ❌ sanitize関数: 一部のエンドポイントで未実装
    → 修正パッチを自動生成
```

**設計段階と実装後の2回スキャンすることで、緩和策の実装漏れを検出**できる。

## Layer 5: Infrastructure Guard（Terraform特化）

インフラ変更は特にリスクが高い。Terraform plan の差分を自動分析するガードを設けた。

```python
# terraform plan の出力を解析して危険な変更を検出

DANGEROUS_PATTERNS = [
    # IAM
    (r'"Action":\s*"\*"', "CRITICAL", "IAM全権限付与"),
    (r'"Resource":\s*"\*"', "HIGH", "全リソースアクセス"),
    (r'"Effect":\s*"Allow".*"Principal":\s*"\*"', "CRITICAL", "全世界許可"),

    # ネットワーク
    (r'ingress.*0\.0\.0\.0/0.*(?!443|80)', "HIGH", "非HTTP/Sポートの全開放"),

    # データ
    (r'force_destroy\s*=\s*true', "HIGH", "強制削除の有効化"),
    (r'deletion_protection\s*=\s*false', "CRITICAL", "削除保護の無効化"),

    # 暗号化
    (r'encrypted\s*=\s*false', "MEDIUM", "暗号化の無効化"),
    (r'kms_key_id\s*=\s*""', "MEDIUM", "KMSキー未設定"),
]
```

`terraform plan` の出力にこれらのパターンが含まれていたら**自動でブロック**する。

## 実際の運用フロー

```
開発者: 「ログイン機能を追加して」
  │
  ├─ Layer 1: CLAUDE.md のルールを確認
  │
  ├─ Layer 2: STRIDE分析を実行
  │   └─ 認証バイパスのリスクを検出 → 設計に反映
  │
  ├─ [実装]
  │
  ├─ Layer 3: AI Code Review（4エージェント）
  │   └─ SQLi脆弱性を検出 → 修正
  │
  ├─ Layer 4: OWASP自動スキャン
  │   └─ XSS対策の実装漏れを検出 → 修正
  │
  └─ Layer 5: Terraform plan チェック
      └─ IAMポリシーの過剰権限を検出 → 修正
```

**全レイヤーをパスするまでデプロイしない。**

## Enterprise版との比較

| 機能 | Anthropic Enterprise | 自前実装 | コスト |
|------|---------------------|---------|--------|
| Code Review | $15-25/PR | AI Code Review スクリプト | $0 |
| Security Scan | Enterprise限定 | /security-review スキル | $0 |
| 権限制御 | Enterprise Guardrails | CLAUDE.md + Infrastructure Guard | $0 |
| 脅威モデリング | なし | STRIDE自動分析 | $0 |

**Enterprise版の主要なセキュリティ機能を、Claude Codeの標準機能だけで再現している。**

## 導入後の効果

3ヶ月運用した結果：

| 指標 | 導入前 | 導入後 |
|------|--------|--------|
| セキュリティ指摘（レビュー時） | 月平均5件 | 月平均0.5件 |
| IAMポリシーの過剰権限 | 月2〜3件検出 | 0件 |
| 本番インシデント | 1件（S3公開事故未遂） | 0件 |
| Code Review時間 | 30分/PR | 5分/PR（AI自動+人間確認） |

## ハマったポイント

### 1. CLAUDE.mdのルールは「具体的に」書かないと効かない

❌ 「セキュリティに気をつけて」
✅ 「IAMポリシーで `Action: "*"` を使わない」

抽象的な指示はAIに無視される。**具体的な禁止パターンを列挙する**ことが重要。

### 2. 偽陽性のチューニングが大変

初期のスキャンは偽陽性だらけだった。Stage 3の偽陽性フィルタリング（データフロー追跡・コンテキスト分析）を追加して、精度を上げた。

### 3. Layer間の依存を切ること

Layer 3（Code Review）がLayer 2（STRIDE）の結果に依存すると、1箇所のエラーで全体が止まる。各レイヤーは**独立して動作**するように設計した。

## まとめ

- Claude Codeは強力だが、**セキュリティガードレールなしでは本番環境に触らせてはいけない**
- **5層の多層防御**（権限制御 / STRIDE / Code Review / OWASP / Infra Guard）で網羅的にカバー
- **Enterprise版の有料機能に頼らず**、標準のClaude Code + スキル + シェルスクリプトで実現可能
- 最も効果的なのは**Layer 1（CLAUDE.md）の具体的な禁止事項の記述**
- 設計段階（Layer 2）と実装後（Layer 4）の**2回スキャン**で実装漏れを検出

**「AIに任せる」と「AIを信頼する」は違う。信頼は検証の上に成り立つ。**

---

**関連記事:**
- [Claude Codeで24ロール・10フェーズのAI開発チームを自動編成する](https://zenn.dev/yutaro2076145/articles/claude-agent-team-gafam-enterprise)
- [InfraSim: 実インフラに触れずに150+障害シナリオを仮想実行するカオスエンジニアリングツール](https://zenn.dev/yutaro2076145/articles/infrasim-virtual-chaos-engineering)
