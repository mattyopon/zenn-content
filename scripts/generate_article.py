#!/usr/bin/env python3
"""Zenn 記事自動生成スクリプト.

セキュリティニュースやエンジニアリングトピックから
Zenn 記事を自動生成する。cron で毎日実行することを想定。

Usage:
    python scripts/generate_article.py
    python scripts/generate_article.py --topic "kubernetes security"
    python scripts/generate_article.py --dry-run
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from textwrap import dedent

import httpx

ARTICLES_DIR = Path(__file__).parent.parent / "articles"
STATE_FILE = Path(__file__).parent / ".generator_state.json"

# ----------------------------------------------------------------
# Topic RSS feeds (engineering / security / cloud)
# ----------------------------------------------------------------
TOPIC_FEEDS = [
    {
        "name": "The Hacker News",
        "url": "https://feeds.feedburner.com/TheHackersNews",
        "category": "security",
    },
    {
        "name": "BleepingComputer",
        "url": "https://www.bleepingcomputer.com/feed/",
        "category": "security",
    },
    {
        "name": "Krebs on Security",
        "url": "https://krebsonsecurity.com/feed/",
        "category": "security",
    },
    {
        "name": "AWS What's New",
        "url": "https://aws.amazon.com/about-aws/whats-new/recent/feed/",
        "category": "cloud",
    },
    {
        "name": "Google Cloud Blog",
        "url": "https://cloudblog.withgoogle.com/rss/",
        "category": "cloud",
    },
    {
        "name": "Dev.to Top",
        "url": "https://dev.to/feed",
        "category": "engineering",
    },
    {
        "name": "Hacker News Best",
        "url": "https://hnrss.org/best",
        "category": "engineering",
    },
]

# ----------------------------------------------------------------
# Topic classification keywords
# ----------------------------------------------------------------
TOPIC_MAP = {
    "kubernetes": {
        "keywords": ["kubernetes", "k8s", "container", "pod", "helm", "eks", "gke", "aks"],
        "emoji": "☸️",
        "topics": ["kubernetes", "docker", "devops", "cloud"],
    },
    "security": {
        "keywords": ["vulnerability", "cve", "ransomware", "breach", "exploit", "zero-day",
                      "malware", "phishing", "ddos", "attack"],
        "emoji": "🔒",
        "topics": ["security", "cybersecurity", "devops", "infrastructure"],
    },
    "aws": {
        "keywords": ["aws", "amazon", "ec2", "s3", "lambda", "ecs", "rds", "cloudfront",
                      "sagemaker", "bedrock"],
        "emoji": "☁️",
        "topics": ["aws", "cloud", "infrastructure", "devops"],
    },
    "terraform": {
        "keywords": ["terraform", "iac", "infrastructure as code", "opentofu", "hcl"],
        "emoji": "🏗️",
        "topics": ["terraform", "iac", "devops", "infrastructure"],
    },
    "observability": {
        "keywords": ["monitoring", "observability", "prometheus", "grafana", "datadog",
                      "alerting", "sre", "incident"],
        "emoji": "📊",
        "topics": ["monitoring", "sre", "devops", "observability"],
    },
    "ai_ml": {
        "keywords": ["ai", "machine learning", "llm", "gpt", "claude", "generative",
                      "copilot", "neural"],
        "emoji": "🤖",
        "topics": ["ai", "machinelearning", "llm", "python"],
    },
    "performance": {
        "keywords": ["performance", "optimization", "latency", "throughput", "caching",
                      "cdn", "load balancing"],
        "emoji": "⚡",
        "topics": ["performance", "infrastructure", "sre", "devops"],
    },
    "database": {
        "keywords": ["database", "postgresql", "mysql", "redis", "mongodb", "dynamodb",
                      "migration", "replication"],
        "emoji": "🗄️",
        "topics": ["database", "postgresql", "redis", "infrastructure"],
    },
    "cicd": {
        "keywords": ["ci/cd", "github actions", "jenkins", "deployment", "pipeline",
                      "argocd", "gitops"],
        "emoji": "🚀",
        "topics": ["cicd", "githubactions", "devops", "automation"],
    },
    "general_engineering": {
        "keywords": [],  # fallback
        "emoji": "💡",
        "topics": ["engineering", "tech", "devops", "programming"],
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
    """Fetch RSS feed and return list of {title, link, summary}."""
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

    # RSS items
    for item in root.iter("item"):
        title_el = item.find("title")
        link_el = item.find("link")
        desc_el = item.find("description")
        title = (title_el.text or "").strip() if title_el is not None else ""
        link = (link_el.text or "").strip() if link_el is not None else ""
        desc = (desc_el.text or "").strip()[:500] if desc_el is not None else ""
        if title:
            articles.append({"title": title, "link": link, "summary": desc})

    # Atom entries
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


def _classify_topic(title: str, summary: str) -> str:
    """Classify article into a topic category."""
    text = f"{title} {summary}".lower()
    best_topic = "general_engineering"
    best_score = 0

    for topic_id, config in TOPIC_MAP.items():
        if not config["keywords"]:
            continue
        score = sum(1 for kw in config["keywords"] if kw.lower() in text)
        if score > best_score:
            best_score = score
            best_topic = topic_id

    return best_topic


def _slug(title: str) -> str:
    """Generate URL-safe slug from title."""
    # Remove non-alphanumeric (keep hyphens)
    slug = re.sub(r"[^\w\s-]", "", title.lower())
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = slug.strip("-")[:50]
    # Add date prefix for uniqueness
    date_str = datetime.now().strftime("%Y%m%d")
    return f"{date_str}-{slug}"


def _generate_article_content(article: dict, topic_id: str) -> str:
    """Generate Zenn article markdown from a news article."""
    config = TOPIC_MAP[topic_id]
    title = article["title"]
    link = article["link"]
    summary = article["summary"]
    # Strip HTML tags from summary
    clean_summary = re.sub(r"<[^>]+>", "", summary).strip()

    today = datetime.now().strftime("%Y/%m/%d")

    content = dedent(f"""\
    ---
    title: "{title[:70]}"
    emoji: "{config['emoji']}"
    type: "tech"
    topics: {json.dumps(config['topics'])}
    published: true
    ---

    ## 概要

    > {clean_summary[:300]}

    元記事: {link}

    ## ポイント

    本記事では、上記ニュースの技術的なポイントをエンジニア視点で解説します。

    ### 背景

    {_generate_background(topic_id, title)}

    ### 技術的な影響

    {_generate_impact(topic_id, title, clean_summary)}

    ### エンジニアが取るべきアクション

    {_generate_actions(topic_id, title)}

    ## まとめ

    {_generate_summary(topic_id, title)}

    ---

    *この記事は {today} のエンジニアリングニュースを元に作成されました。*
    """)

    return content


def _generate_background(topic_id: str, title: str) -> str:
    backgrounds = {
        "security": "サイバーセキュリティの脅威は日々進化しており、インフラエンジニアにとって最新の脆弱性情報を把握することは不可欠です。特にクラウド環境では、1つの設定ミスが大規模なインシデントにつながる可能性があります。",
        "aws": "AWSは継続的に新機能やアップデートをリリースしています。これらの変更はコスト最適化、セキュリティ強化、運用効率の改善に直結するため、キャッチアップが重要です。",
        "kubernetes": "Kubernetesエコシステムは急速に進化を続けており、セキュリティ、スケーラビリティ、運用性の面で新しいベストプラクティスが次々と登場しています。",
        "terraform": "Infrastructure as Code（IaC）は現代のインフラ管理の基盤であり、Terraformの更新やベストプラクティスの変化はインフラチーム全体に影響します。",
        "observability": "可観測性はSREの中核をなす概念であり、障害の早期検知と原因分析のためにメトリクス・ログ・トレースの統合的な管理が求められています。",
        "ai_ml": "AI/MLの急速な進歩はエンジニアリングの在り方を変えつつあります。開発支援から運用自動化まで、幅広い領域で活用が進んでいます。",
        "performance": "パフォーマンス最適化はユーザー体験とコスト効率の両面で重要です。特にクラウド環境では、リソースの適切なサイジングとキャッシュ戦略が鍵となります。",
        "database": "データベースはシステムの心臓部であり、その設計・運用の質がサービス全体の信頼性とパフォーマンスを左右します。",
        "cicd": "CI/CDパイプラインの成熟度は開発チームの生産性に直結します。デプロイ頻度の向上と品質の両立が求められています。",
    }
    return backgrounds.get(topic_id, "技術の進歩は常に加速しており、エンジニアとして最新のトレンドを把握し続けることが重要です。")


def _generate_impact(topic_id: str, title: str, summary: str) -> str:
    impacts = {
        "security": f"このセキュリティ関連の動向は、以下の観点でインフラに影響を与える可能性があります：\n\n- **脆弱性管理**: パッチ適用の優先度判断が必要\n- **ネットワーク防御**: ファイアウォールルールやWAF設定の見直し\n- **監視強化**: 異常検知ルールの追加や閾値の調整\n- **インシデント対応**: ランブックの更新と対応手順の確認",
        "aws": f"AWSの更新がインフラに与える影響：\n\n- **コスト**: 新サービス・価格改定による費用の変動\n- **アーキテクチャ**: より効率的な構成への移行検討\n- **セキュリティ**: 新機能によるセキュリティ体制の強化\n- **運用**: マネージドサービスの活用による運用負荷の軽減",
        "kubernetes": f"Kubernetes関連の更新がもたらす影響：\n\n- **クラスタ管理**: アップグレード計画への反映\n- **セキュリティ**: Pod Security Standards の適用見直し\n- **スケーリング**: オートスケーラーの設定最適化\n- **ネットワーク**: Service Mesh やIngress設定の更新",
    }
    return impacts.get(topic_id, f"この技術動向は、システムの信頼性・セキュリティ・パフォーマンスの各面で影響があります。\n\n- **設計**: アーキテクチャの見直し検討\n- **運用**: 既存の運用手順への影響確認\n- **セキュリティ**: 新たなリスクへの対応\n- **パフォーマンス**: ボトルネック分析の実施")


def _generate_actions(topic_id: str, title: str) -> str:
    actions = {
        "security": "1. **影響範囲の確認** - 自社環境で該当するコンポーネントを特定する\n2. **パッチ適用の計画** - 緊急度に応じてパッチ適用スケジュールを策定\n3. **監視の強化** - 関連するメトリクス・ログの監視ルールを追加\n4. **チーム共有** - セキュリティチームと情報を共有し、対応方針を決定",
        "aws": "1. **検証環境での確認** - 新機能をステージング環境で検証\n2. **コスト影響の試算** - AWS Pricing Calculator で費用を見積もり\n3. **移行計画の策定** - 必要に応じてインフラコードを更新\n4. **ドキュメント更新** - 運用手順書やアーキテクチャ図を更新",
        "kubernetes": "1. **バージョン確認** - 現在のクラスタバージョンと影響範囲を確認\n2. **テスト実行** - staging環境でアップグレードテスト\n3. **マニフェスト更新** - 非推奨APIの置き換え\n4. **モニタリング** - アップグレード後のメトリクス監視強化",
    }
    return actions.get(topic_id, "1. **情報収集** - 公式ドキュメントで詳細を確認\n2. **影響評価** - 自社環境への影響を分析\n3. **対応計画** - 必要なアクションのロードマップ作成\n4. **実行と検証** - 段階的に対応を実施し、結果を検証")


def _generate_summary(topic_id: str, title: str) -> str:
    return f"最新の技術動向を把握し、自社環境への影響を事前に評価することで、インシデントの予防と迅速な対応が可能になります。日々の情報収集と、それに基づくプロアクティブな対応を心がけましょう。"


def fetch_and_generate(topic_filter: str | None = None, dry_run: bool = False) -> str | None:
    """Fetch feeds, pick best article, generate Zenn article."""
    state = _load_state()
    published_urls = set(state.get("published_urls", []))

    print(f"Fetching {len(TOPIC_FEEDS)} feeds...")
    all_articles = []
    for feed in TOPIC_FEEDS:
        if topic_filter and topic_filter.lower() not in feed["category"]:
            continue
        articles = _fetch_rss(feed["url"])
        for a in articles:
            a["feed_name"] = feed["name"]
            a["feed_category"] = feed["category"]
        all_articles.extend(articles)

    print(f"  Fetched {len(all_articles)} articles")

    # Filter already published
    new_articles = [a for a in all_articles if a["link"] not in published_urls]
    print(f"  New (unpublished): {len(new_articles)}")

    if not new_articles:
        print("No new articles to write about.")
        return None

    # Pick the best article (prefer security > cloud > engineering)
    priority = {"security": 3, "cloud": 2, "engineering": 1}
    new_articles.sort(key=lambda a: priority.get(a.get("feed_category", ""), 0), reverse=True)

    # Use topic filter if specified
    if topic_filter:
        filtered = [a for a in new_articles
                    if topic_filter.lower() in a.get("title", "").lower()
                    or topic_filter.lower() in a.get("summary", "").lower()
                    or topic_filter.lower() in a.get("feed_category", "").lower()]
        if filtered:
            new_articles = filtered

    chosen = new_articles[0]
    topic_id = _classify_topic(chosen["title"], chosen.get("summary", ""))

    print(f"\nSelected: [{topic_id}] {chosen['title'][:60]}")
    print(f"  Source: {chosen.get('feed_name', '?')}")
    print(f"  URL: {chosen['link']}")

    if dry_run:
        print("\n[DRY RUN] Would generate article but not writing.")
        return None

    # Generate article
    content = _generate_article_content(chosen, topic_id)
    slug = _slug(chosen["title"])
    filename = f"{slug}.md"
    filepath = ARTICLES_DIR / filename

    filepath.write_text(content, encoding="utf-8")
    print(f"\nArticle written: {filepath}")

    # Update state
    published_urls.add(chosen["link"])
    state["published_urls"] = list(published_urls)[-500:]  # Keep last 500
    state["last_run"] = datetime.now(timezone.utc).isoformat()
    state["last_article"] = {
        "title": chosen["title"],
        "slug": slug,
        "topic": topic_id,
        "source": chosen.get("feed_name"),
    }
    _save_state(state)

    return str(filepath)


def main():
    parser = argparse.ArgumentParser(description="Zenn記事自動生成")
    parser.add_argument("--topic", help="トピックフィルタ (security, cloud, kubernetes, etc.)")
    parser.add_argument("--dry-run", action="store_true", help="記事を生成するが保存しない")
    args = parser.parse_args()

    result = fetch_and_generate(topic_filter=args.topic, dry_run=args.dry_run)
    if result:
        print(f"\nDone! Push to GitHub to publish:")
        print(f"  cd {ARTICLES_DIR.parent}")
        print(f"  git add articles/ && git commit -m 'Add daily article' && git push")


if __name__ == "__main__":
    main()
