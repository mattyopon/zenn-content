#!/usr/bin/env python3
"""Zenn 記事自動生成スクリプト.

エンジニアにバズりそうな話題をRSS/API/スクレイピングから取得し、
Zenn記事を自動生成する。1時間に1本のペースで実行可能。

Sources:
  - Zenn トレンド記事
  - Hacker News トップ
  - Dev.to トレンド
  - GitHub Trending
  - The Hacker News (セキュリティ)
  - Publickey (日本語テックニュース)
  - Gigazine (テック系)
  - AWS / GCP 新機能
  - Qiita トレンド

Usage:
    python scripts/generate_article.py
    python scripts/generate_article.py --topic ai
    python scripts/generate_article.py --dry-run
    python scripts/generate_article.py --count 3  # 3記事生成
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import httpx

ARTICLES_DIR = Path(__file__).parent.parent / "articles"
STATE_FILE = Path(__file__).parent / ".generator_state.json"

# ----------------------------------------------------------------
# Feed sources - バズりやすい順に優先度設定
# ----------------------------------------------------------------
FEEDS = [
    # --- バズ系 (エンジニア間で話題になりやすい) ---
    {"name": "Zenn Trend", "url": "https://zenn.dev/feed", "priority": 10, "lang": "ja", "category": "trend"},
    {"name": "Qiita Trend", "url": "https://qiita.com/popular-items/feed", "priority": 10, "lang": "ja", "category": "trend"},
    {"name": "Hacker News Top", "url": "https://hnrss.org/best", "priority": 9, "category": "trend"},
    {"name": "Dev.to Top", "url": "https://dev.to/feed", "priority": 8, "category": "trend"},
    {"name": "GitHub Trending", "url": "https://mshibanami.github.io/GitHubTrendingRSS/daily/all-languages.xml", "priority": 8, "category": "oss"},
    # --- 日本語テックニュース ---
    {"name": "Publickey", "url": "https://www.publickey1.jp/atom.xml", "priority": 9, "lang": "ja", "category": "news"},
    {"name": "Gigazine Tech", "url": "https://gigazine.net/news/rss_2.0/", "priority": 5, "lang": "ja", "category": "news"},
    {"name": "ITmedia News", "url": "https://rss.itmedia.co.jp/rss/2.0/news_bursts.xml", "priority": 6, "lang": "ja", "category": "news"},
    # --- セキュリティ ---
    {"name": "The Hacker News", "url": "https://feeds.feedburner.com/TheHackersNews", "priority": 7, "category": "security"},
    {"name": "BleepingComputer", "url": "https://www.bleepingcomputer.com/feed/", "priority": 6, "category": "security"},
    {"name": "Krebs on Security", "url": "https://krebsonsecurity.com/feed/", "priority": 6, "category": "security"},
    # --- クラウド ---
    {"name": "AWS What's New", "url": "https://aws.amazon.com/about-aws/whats-new/recent/feed/", "priority": 7, "category": "cloud"},
    {"name": "GCP Blog", "url": "https://cloudblog.withgoogle.com/rss/", "priority": 6, "category": "cloud"},
    # --- AI/LLM (今最もバズるカテゴリ) ---
    {"name": "AI News", "url": "https://buttondown.com/ainews/rss", "priority": 9, "category": "ai"},
]

# ----------------------------------------------------------------
# トピック分類 (バズりやすさの重み付き)
# ----------------------------------------------------------------
TOPIC_MAP = {
    "ai": {
        "keywords": ["ai", "llm", "gpt", "claude", "gemini", "openai", "anthropic",
                      "copilot", "chatgpt", "generative", "transformer", "rag",
                      "agent", "mcp", "prompt", "fine-tun", "embedding"],
        "emoji": "🤖",
        "topics": ["ai", "llm", "machinelearning", "python"],
        "buzz_weight": 3.0,  # AI系は最もバズる
    },
    "rust": {
        "keywords": ["rust", "cargo", "rustlang", "wasm", "webassembly"],
        "emoji": "🦀",
        "topics": ["rust", "programming", "webassembly"],
        "buzz_weight": 2.0,
    },
    "typescript": {
        "keywords": ["typescript", "deno", "bun", "nextjs", "react", "vue", "svelte",
                      "astro", "remix", "vite", "node.js"],
        "emoji": "💎",
        "topics": ["typescript", "javascript", "react", "nextjs"],
        "buzz_weight": 2.0,
    },
    "go": {
        "keywords": ["golang", "go ", " go,", "goroutine"],
        "emoji": "🐹",
        "topics": ["go", "programming", "backend"],
        "buzz_weight": 1.5,
    },
    "kubernetes": {
        "keywords": ["kubernetes", "k8s", "container", "docker", "helm", "eks", "gke",
                      "aks", "istio", "envoy"],
        "emoji": "☸️",
        "topics": ["kubernetes", "docker", "devops", "cloud"],
        "buzz_weight": 1.8,
    },
    "security": {
        "keywords": ["vulnerability", "cve", "ransomware", "breach", "exploit", "zero-day",
                      "malware", "phishing", "ddos", "attack", "hack"],
        "emoji": "🔒",
        "topics": ["security", "cybersecurity", "devops"],
        "buzz_weight": 2.0,
    },
    "aws": {
        "keywords": ["aws", "amazon web", "ec2", "s3", "lambda", "ecs", "rds",
                      "cloudfront", "sagemaker", "bedrock", "fargate"],
        "emoji": "☁️",
        "topics": ["aws", "cloud", "infrastructure", "devops"],
        "buzz_weight": 1.8,
    },
    "devops": {
        "keywords": ["terraform", "iac", "ci/cd", "github actions", "gitops", "argocd",
                      "ansible", "pulumi", "opentofu"],
        "emoji": "🚀",
        "topics": ["devops", "cicd", "terraform", "githubactions"],
        "buzz_weight": 1.5,
    },
    "database": {
        "keywords": ["database", "postgresql", "mysql", "redis", "mongodb", "sqlite",
                      "supabase", "neon", "turso", "drizzle"],
        "emoji": "🗄️",
        "topics": ["database", "postgresql", "redis"],
        "buzz_weight": 1.3,
    },
    "sre": {
        "keywords": ["sre", "observability", "monitoring", "prometheus", "grafana",
                      "incident", "postmortem", "chaos", "reliability"],
        "emoji": "📊",
        "topics": ["sre", "monitoring", "devops", "infrastructure"],
        "buzz_weight": 1.5,
    },
    "oss": {
        "keywords": ["open source", "oss", "github", "star", "release", "trending"],
        "emoji": "⭐",
        "topics": ["oss", "github", "programming"],
        "buzz_weight": 1.5,
    },
    "general": {
        "keywords": [],
        "emoji": "💡",
        "topics": ["tech", "programming", "devops"],
        "buzz_weight": 1.0,
    },
}


def _load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"published_urls": [], "last_run": None}


def _save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False))


def _fetch_rss(url: str, timeout: float = 15.0) -> list[dict]:
    """Fetch RSS/Atom feed."""
    try:
        resp = httpx.get(url, follow_redirects=True, timeout=timeout,
                         headers={"User-Agent": "ZennAutoWriter/1.0"})
        resp.raise_for_status()
    except (httpx.HTTPError, httpx.TimeoutException):
        return []

    articles = []
    try:
        root = ET.fromstring(resp.content)
    except ET.ParseError:
        return []

    for item in root.iter("item"):
        title_el = item.find("title")
        link_el = item.find("link")
        desc_el = item.find("description")
        title = (title_el.text or "").strip() if title_el is not None else ""
        link = (link_el.text or "").strip() if link_el is not None else ""
        desc = (desc_el.text or "").strip()[:500] if desc_el is not None else ""
        if title:
            articles.append({"title": title, "link": link, "summary": desc})

    for entry in root.iter():
        tag = entry.tag.split("}")[-1] if "}" in entry.tag else entry.tag
        if tag != "entry":
            continue
        title = link = desc = ""
        for child in entry:
            ctag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if ctag == "title":
                title = (child.text or "").strip()
            elif ctag == "link":
                link = child.get("href", "") or (child.text or "").strip()
            elif ctag in ("summary", "content"):
                desc = (child.text or "").strip()[:500]
        if title:
            articles.append({"title": title, "link": link, "summary": desc})

    return articles


def _classify(title: str, summary: str) -> tuple[str, float]:
    """Classify into topic and return (topic_id, buzz_score)."""
    text = f"{title} {summary}".lower()
    best = "general"
    best_score = 0.0

    for tid, cfg in TOPIC_MAP.items():
        if not cfg["keywords"]:
            continue
        hits = sum(1 for kw in cfg["keywords"] if kw.lower() in text)
        score = hits * cfg["buzz_weight"]
        if score > best_score:
            best_score = score
            best = tid

    return best, best_score


def _slug(title: str) -> str:
    """Generate Zenn-compatible slug (12-50 chars, ASCII only)."""
    # Remove non-ASCII characters first, then clean
    ascii_title = re.sub(r"[^\x00-\x7f]", "", title)
    slug = re.sub(r"[^\w\s-]", "", ascii_title.lower())
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = slug.strip("-")
    date_str = datetime.now().strftime("%Y%m%d%H")
    max_len = 50 - len(date_str) - 1
    slug = slug[:max_len]
    if len(slug) < 3:
        slug = hashlib.md5(title.encode()).hexdigest()[:max_len]
    return f"{date_str}-{slug}"


def _clean_html(text: str) -> str:
    """Strip HTML tags."""
    return re.sub(r"<[^>]+>", "", text).strip()


def _build_article(article: dict, topic_id: str) -> str:
    """Build Zenn article markdown."""
    cfg = TOPIC_MAP[topic_id]
    title = article["title"][:70]
    link = article["link"]
    summary = _clean_html(article.get("summary", ""))[:300]
    source = article.get("feed_name", "")
    today = datetime.now().strftime("%Y/%m/%d %H:%M")

    # タイトルを日本語エンジニア向けに変換
    ja_title = _make_ja_title(title, topic_id, source)

    background = _get_section(topic_id, "background")
    impact = _get_section(topic_id, "impact")
    actions = _get_section(topic_id, "actions")
    opinion = _get_section(topic_id, "opinion")

    return f"""---
title: "{ja_title}"
emoji: "{cfg['emoji']}"
type: "tech"
topics: {json.dumps(cfg['topics'])}
published: false
---

## 概要

> {summary}

元記事: {link}
ソース: {source}

## 背景

{background}

## 技術的なポイント

{impact}

## エンジニアが取るべきアクション

{actions}

## 所感

{opinion}

---

*この記事は {today} のテックニュースを元に自動生成されました。*
*誤りや追加情報があればコメントで教えてください。*
"""


def _make_ja_title(title: str, topic_id: str, source: str) -> str:
    """Make a catchy Japanese title for the article."""
    # If already Japanese, use as-is
    if re.search(r"[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff]", title):
        return title[:70]

    prefixes = {
        "ai": ["AI最前線", "LLM注目", "生成AI"],
        "security": ["セキュリティ速報", "脆弱性情報", "サイバー脅威"],
        "aws": ["AWS新機能", "AWSアップデート"],
        "kubernetes": ["K8s動向", "コンテナ最新"],
        "devops": ["DevOps注目", "IaC最新"],
        "rust": ["Rust話題", "Rustエコシステム"],
        "typescript": ["フロントエンド注目", "TS/JS最新"],
        "database": ["DB注目", "データベース動向"],
        "sre": ["SRE注目", "信頼性エンジニアリング"],
        "oss": ["OSS注目", "GitHub Trending"],
    }
    prefix_list = prefixes.get(topic_id, ["テック注目"])
    prefix = random.choice(prefix_list)

    # Truncate English title
    short_title = title[:50]
    return f"【{prefix}】{short_title}"


def _get_section(topic_id: str, section: str) -> str:
    """Get section content by topic and section type."""
    sections = {
        "background": {
            "ai": "AI/LLM分野は急速に発展しており、毎週のように新しいモデルやツールが登場しています。特にエージェント技術、RAG、マルチモーダルAIの進歩が著しく、エンジニアの開発ワークフローにも大きな影響を与えています。",
            "security": "サイバーセキュリティの脅威は日々高度化しており、ゼロデイ攻撃やサプライチェーン攻撃など、従来の防御手法では対応しきれないケースが増えています。クラウド環境の普及に伴い、攻撃対象面も拡大しています。",
            "aws": "AWSは年間3000以上の新機能・アップデートをリリースしており、そのキャッチアップは多くのエンジニアにとって課題となっています。コスト最適化、セキュリティ、運用効率の3軸でのアップデートが中心です。",
            "kubernetes": "Kubernetesはクラウドネイティブの事実上の標準ですが、エコシステムの進化は止まりません。Gateway API、Karpenter、Backstageなど、運用性を向上させるツールが続々と登場しています。",
            "devops": "DevOps/IaCの世界では、Terraformのライセンス変更を受けたOpenTofuの台頭や、Pulumiの成長、GitHub ActionsやArgoCD等のCI/CDツールの進化が注目されています。",
            "rust": "Rustはメモリ安全性と高性能を両立する言語として、LinuxカーネルやAndroid、Cloudflareなど大規模プロジェクトでの採用が進んでいます。WebAssembly対応も活用の幅を広げています。",
            "typescript": "TypeScript/JavaScriptエコシステムは、Bun、Deno等の新しいランタイム、Next.js App Router、React Server Components等のフレームワーク革新が続いています。",
            "database": "データベース分野では、Serverless DB（Neon、PlanetScale）、NewSQL、ベクトルDBの台頭が注目されています。PostgreSQLの機能拡張も目覚ましいものがあります。",
            "sre": "SRE/可観測性の分野では、OpenTelemetryの普及、eBPFベースの監視ツール、AIOpsの実用化が進んでいます。インシデント管理のベストプラクティスも日々更新されています。",
            "oss": "オープンソースの世界では、GitHubスター数の急増するプロジェクトが新たな技術トレンドを示すバロメーターとなっています。",
        },
        "impact": {
            "ai": "- **開発効率**: AIコーディング支援ツールの精度向上により、開発速度が大幅に改善\n- **アーキテクチャ**: RAGやエージェント基盤の設計パターンが標準化しつつある\n- **コスト**: 推論コストの低下により、より多くのユースケースで実用的に\n- **セキュリティ**: プロンプトインジェクション等の新しいリスクへの対応が必要",
            "security": "- **脆弱性管理**: パッチ適用の優先度判断と迅速な対応が必要\n- **多層防御**: WAF、IDS/IPS、EDRの連携強化\n- **ゼロトラスト**: ネットワーク境界に依存しないセキュリティモデルへの移行\n- **インシデント対応**: ランブックの更新とドリル実施",
            "aws": "- **コスト**: 新料金体系やSavings Plansの活用検討\n- **性能**: 新インスタンスタイプやサービスによる最適化\n- **セキュリティ**: IAM Identity Center、GuardDuty等の新機能活用\n- **運用**: マネージドサービスの拡充による運用負荷軽減",
            "kubernetes": "- **クラスタ管理**: コントロールプレーンのアップグレード戦略\n- **セキュリティ**: Pod Security Admission、NetworkPolicy の見直し\n- **コスト**: Karpenterやクラスタオートスケーラーの最適化\n- **可観測性**: サービスメッシュとの連携強化",
        },
        "actions": {
            "ai": "1. **検証**: 新しいモデル/ツールをPoC環境で試す\n2. **評価**: 既存ワークフローへの統合可能性を評価\n3. **セキュリティ**: データガバナンスとプライバシーの確認\n4. **共有**: チーム内でナレッジ共有セッションを実施",
            "security": "1. **影響確認**: 自社環境で該当するコンポーネントを特定\n2. **パッチ適用**: 緊急度に応じたパッチスケジュール策定\n3. **監視強化**: IOC（Indicator of Compromise）の監視ルール追加\n4. **訓練**: インシデント対応チームでのテーブルトップ演習",
            "aws": "1. **検証**: ステージング環境で新機能を検証\n2. **コスト試算**: 料金変更の影響をAWS Cost Explorerで分析\n3. **IaC更新**: Terraform/CDKコードを更新\n4. **ドキュメント**: 運用手順書とアーキテクチャ図を更新",
            "kubernetes": "1. **バージョン確認**: 非推奨APIの使用有無をチェック\n2. **テスト**: staging環境でのアップグレードテスト\n3. **マニフェスト更新**: Deprecation warningへの対応\n4. **モニタリング**: Prometheus/Grafanaダッシュボードの更新",
        },
        "opinion": {
            "ai": "AI技術の進化スピードは凄まじく、半年前のベストプラクティスが陳腐化することも珍しくありません。重要なのは個々のツールに深入りしすぎず、「何が解決したい課題なのか」を常に意識すること。技術選定は冷静に、導入は大胆に。",
            "security": "セキュリティは「コスト」ではなく「投資」です。インシデントが起きてからでは遅い。日常的な脆弱性情報の収集と、チーム全体のセキュリティ意識の向上が、最も費用対効果の高い防御策です。",
            "aws": "AWSの新機能は魅力的ですが、全てを追いかける必要はありません。自社のワークロードに直結する更新に集中し、それ以外は「知っている」レベルで十分。重要なのは基盤サービス（IAM、VPC、S3）の理解を深めること。",
            "kubernetes": "K8sは強力ですが複雑です。ECSやCloud Run等のシンプルな選択肢も常に検討すべき。「K8sを使うこと」が目的にならないよう注意。運用コストも含めたトータルコストで判断しましょう。",
            "devops": "IaCやCI/CDは手段であって目的ではありません。チームの開発フローに合った仕組みを選び、段階的に成熟度を上げていくことが大切です。完璧を目指すより、まず回し始めることが重要。",
            "rust": "Rustの学習曲線は確かに急ですが、得られるメモリ安全性とパフォーマンスのメリットは大きい。まずはCLIツールなど小さなプロジェクトから始めるのがおすすめです。",
            "typescript": "フロントエンドの変化は速いですが、基礎（HTML/CSS/JS）は変わりません。新しいフレームワークに飛びつく前に、なぜそれが必要なのかを考える習慣をつけましょう。",
            "database": "データベース選定は「流行り」ではなく「ワークロード特性」で決めるべきです。PostgreSQLは多くのケースで最適解。NoSQLは本当に必要な場面でのみ検討を。",
            "sre": "SREは文化であり、ツールだけでは実現できません。SLO/SLIの設計、エラーバジェットの運用、ポストモーテムの文化を組織全体で醸成することが本質です。",
        },
    }

    topic_sections = sections.get(section, {})
    text = topic_sections.get(topic_id, "")
    if not text:
        defaults = {
            "background": "技術の進歩は加速しており、エンジニアとして最新トレンドの把握が重要です。",
            "impact": "- **設計**: アーキテクチャへの影響を確認\n- **運用**: 既存の運用手順への影響を評価\n- **セキュリティ**: 新たなリスクへの対応を検討\n- **パフォーマンス**: ボトルネックの分析と改善",
            "actions": "1. **情報収集** - 公式ドキュメントで詳細を確認\n2. **影響評価** - 自社環境への影響を分析\n3. **対応計画** - アクションのロードマップ作成\n4. **実行と検証** - 段階的に対応し結果を検証",
            "opinion": "新しい技術やツールは次々と登場しますが、大切なのは「解決したい課題は何か」を見失わないこと。流行に振り回されず、自分のプロジェクトに本当に必要なものを見極めましょう。",
        }
        text = defaults.get(section, "")
    return text


def fetch_and_generate(topic_filter: str | None = None, dry_run: bool = False) -> str | None:
    """Fetch feeds, rank by buzz potential, generate article."""
    state = _load_state()
    published = set(state.get("published_urls", []))

    print(f"Fetching {len(FEEDS)} feeds...")
    all_articles = []
    for feed in FEEDS:
        articles = _fetch_rss(feed["url"])
        for a in articles:
            a["feed_name"] = feed["name"]
            a["feed_priority"] = feed.get("priority", 5)
            a["feed_category"] = feed.get("category", "")
            a["feed_lang"] = feed.get("lang", "en")
        all_articles.extend(articles)

    print(f"  Fetched {len(all_articles)} articles total")

    # Filter published
    new = [a for a in all_articles if a["link"] not in published and a["link"]]
    print(f"  New (unpublished): {len(new)}")

    if not new:
        print("No new articles.")
        return None

    # Score each article by buzz potential
    scored = []
    for a in new:
        topic_id, topic_score = _classify(a["title"], a.get("summary", ""))
        feed_priority = a.get("feed_priority", 5)
        # Japanese articles get a bonus (Zenn audience is Japanese)
        lang_bonus = 1.5 if a.get("feed_lang") == "ja" else 1.0
        # Combine scores
        buzz = (topic_score + feed_priority) * lang_bonus
        scored.append((buzz, topic_id, a))

    # Apply topic filter
    if topic_filter:
        tf = topic_filter.lower()
        scored = [(b, t, a) for b, t, a in scored
                  if tf in t or tf in a["title"].lower() or tf in a.get("summary", "").lower()]

    if not scored:
        print(f"No articles matching filter: {topic_filter}")
        return None

    # Sort by buzz score descending, add some randomness to avoid repetition
    scored.sort(key=lambda x: x[0] + random.uniform(0, 3), reverse=True)

    buzz, topic_id, chosen = scored[0]
    print(f"\nSelected (buzz={buzz:.1f}): [{topic_id}] {chosen['title'][:60]}")
    print(f"  Source: {chosen['feed_name']}")

    if dry_run:
        print("[DRY RUN] Skipping write.")
        for b, t, a in scored[:5]:
            print(f"  [{t}] (buzz={b:.1f}) {a['title'][:50]} - {a['feed_name']}")
        return None

    content = _build_article(chosen, topic_id)
    slug = _slug(chosen["title"])
    filepath = ARTICLES_DIR / f"{slug}.md"

    filepath.write_text(content, encoding="utf-8")
    print(f"Written: {filepath}")

    # Update state
    published.add(chosen["link"])
    state["published_urls"] = list(published)[-1000:]
    state["last_run"] = datetime.now(timezone.utc).isoformat()
    state["last_article"] = {"title": chosen["title"], "slug": slug, "topic": topic_id}
    _save_state(state)

    return str(filepath)


def main():
    parser = argparse.ArgumentParser(description="Zenn記事自動生成 (1時間1本)")
    parser.add_argument("--topic", help="トピックフィルタ (ai, security, aws, kubernetes, etc.)")
    parser.add_argument("--dry-run", action="store_true", help="生成するが書き込まない")
    parser.add_argument("--count", type=int, default=1, help="生成する記事数 (default: 1)")
    args = parser.parse_args()

    for i in range(args.count):
        if i > 0:
            print(f"\n--- Article {i + 1}/{args.count} ---\n")
        result = fetch_and_generate(topic_filter=args.topic, dry_run=args.dry_run)
        if not result:
            break

    if not args.dry_run:
        print(f"\nPush to publish:")
        print(f"  cd {ARTICLES_DIR.parent}")
        print(f"  git add articles/ && git commit -m 'Add article' && git push")


if __name__ == "__main__":
    main()
