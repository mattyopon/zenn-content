---
title: "Xクローン v2.3 — Feature Flag自前基盤 / GraphQL Federation移行パス / コスト最適化ダッシュボード"
emoji: "🚀"
type: "tech"
topics: ["featureflags", "graphql", "grafana", "terraform", "typescript"]
published: false
---

## はじめに

[v2.2の記事](https://qiita.com/ymaeda_it/items/d858969cd6de808b8816)でパフォーマンス・スケーラビリティの3課題を解消しました。本記事では**開発者体験（DX）とコスト可視化**に焦点を当て、残り3課題を解消します。

### 解消する3つの課題

| # | 課題 | 重要度 | 解決策 | 新規ファイル数 |
|---|------|--------|--------|--------------|
| 1 | Feature Flag基盤 | Medium | **PostgreSQL + SSE** による自前実装 | 2 |
| 2 | GraphQL Federation移行パス | Low | **Apollo Subgraph + AppSync** Gateway | 2 |
| 3 | コスト最適化ダッシュボード | Medium | **Grafana + Prometheus** コスト追跡 | 2 |

### v2 → v2.3 の進化マップ

```
v2.0: フルスタック基盤（39ファイル）
  ↓ +11ファイル
v2.1: 品質・運用強化
  (Playwright / ISM / マルチリージョンDB / tRPC / CDC)
  ↓ +5ファイル
v2.2: パフォーマンス・スケーラビリティ
  (分散Rate Limit / 画像最適化 / マルチリージョンWS)
  ↓ +6ファイル
v2.3: DX・コスト最適化（本記事）
  (Feature Flag / GraphQL Federation / コストダッシュボード)
```

---

# 課題1: Feature Flag 自前基盤

## なぜ自前実装なのか

| サービス | 月額 | 機能 | 判定 |
|---------|------|------|------|
| LaunchDarkly | $10,500/月（25万MAU） | フル機能 | 高すぎる |
| Unleash (OSS) | $0 | Self-hosted、要インフラ管理 | 中間策 |
| **自前実装** | **$0** | PostgreSQL活用、最小機能 | **採用** |

既にPostgreSQLとRedisを運用しているため、Feature Flag専用の外部サービスを追加する必要はありません。必要最小限の機能を**500行以下**で実装します。

## 設計思想

```
┌─────────────────────────────────────────────────────┐
│                Feature Flag System                   │
│                                                      │
│  ┌──────────┐    ┌──────────┐    ┌──────────────┐   │
│  │PostgreSQL│──▶ │ In-Memory│──▶ │  Evaluator   │   │
│  │(永続化)  │    │ Cache    │    │  (ルール評価) │   │
│  │          │    │ (TTL 30s)│    │              │   │
│  └──────────┘    └──────────┘    └──────┬───────┘   │
│                                         │           │
│                    ┌────────────────────┼──────┐    │
│                    │                    │      │    │
│                    ▼                    ▼      ▼    │
│              User Override      Rule Match  % Rollout│
│              (最高優先度)     (ターゲティング)(ランダム)│
│                                                      │
│  ┌──────────────────────────────────────────────┐   │
│  │              SSE Stream                       │   │
│  │  フラグ変更時にクライアントへリアルタイム通知  │   │
│  └──────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

### フラグ評価の優先順位

```
1. User Override  → 特定ユーザーに強制ON/OFF（デバッグ用）
2. Rule Match     → 条件マッチング（tier=premium, region=jp, etc.）
3. % Rollout      → ユーザーIDハッシュによる段階的ロールアウト
4. Default Value  → 上記全て不一致時のデフォルト値
```

## 実装: `apps/api/src/services/feature-flags.ts`

```typescript
import { db } from "@xclone/db";
import { eq } from "drizzle-orm";
import crypto from "crypto";

// ─── Types ──────────────────────────────────────────────────────────

type FlagType = "boolean" | "string" | "number" | "json";

interface Flag {
  key: string;
  type: FlagType;
  defaultValue: unknown;
  enabled: boolean;
  description: string;
  rules: TargetingRule[];
  rolloutPercentage: number;
  overrides: Record<string, unknown>; // userId → value
}

interface TargetingRule {
  attribute: string;      // e.g., "tier", "region", "platform"
  operator: "eq" | "neq" | "in" | "nin" | "gt" | "lt";
  value: unknown;
  flagValue: unknown;     // フラグの値（条件マッチ時）
}

interface EvaluationContext {
  userId: string;
  tier?: "free" | "premium";
  region?: string;
  platform?: string;
  [key: string]: unknown;
}

interface EvaluationResult<T = unknown> {
  value: T;
  source: "override" | "rule" | "rollout" | "default" | "disabled";
}

// ─── In-Memory Cache ────────────────────────────────────────────────

const flagCache = new Map<string, { flag: Flag; expiresAt: number }>();
const CACHE_TTL = 30_000; // 30 seconds

async function getCachedFlag(key: string): Promise<Flag | null> {
  const cached = flagCache.get(key);
  if (cached && Date.now() < cached.expiresAt) {
    return cached.flag;
  }

  // Fetch from DB (using raw SQL for simplicity)
  const result = await db.execute(
    `SELECT * FROM feature_flags WHERE key = $1`,
    [key]
  );

  if (!result.rows[0]) return null;

  const flag = deserializeFlag(result.rows[0]);
  flagCache.set(key, { flag, expiresAt: Date.now() + CACHE_TTL });
  return flag;
}

// ─── Flag Evaluator ─────────────────────────────────────────────────

export async function evaluateFlag<T>(
  key: string,
  context: EvaluationContext
): Promise<EvaluationResult<T>> {
  const flag = await getCachedFlag(key);

  if (!flag || !flag.enabled) {
    return {
      value: (flag?.defaultValue ?? null) as T,
      source: "disabled",
    };
  }

  // 1. User Override (highest priority)
  if (context.userId in flag.overrides) {
    return {
      value: flag.overrides[context.userId] as T,
      source: "override",
    };
  }

  // 2. Targeting Rules
  for (const rule of flag.rules) {
    if (matchRule(rule, context)) {
      return {
        value: rule.flagValue as T,
        source: "rule",
      };
    }
  }

  // 3. Percentage Rollout
  if (flag.rolloutPercentage > 0 && flag.rolloutPercentage < 100) {
    const hash = crypto
      .createHash("sha256")
      .update(`${key}:${context.userId}`)
      .digest("hex");
    const bucket = parseInt(hash.slice(0, 8), 16) % 100;

    if (bucket < flag.rolloutPercentage) {
      return { value: flag.defaultValue as T, source: "rollout" };
    }
    return { value: getDisabledValue(flag.type) as T, source: "rollout" };
  }

  // 4. Default
  return { value: flag.defaultValue as T, source: "default" };
}

function matchRule(rule: TargetingRule, ctx: EvaluationContext): boolean {
  const attrValue = ctx[rule.attribute];

  switch (rule.operator) {
    case "eq":  return attrValue === rule.value;
    case "neq": return attrValue !== rule.value;
    case "in":  return Array.isArray(rule.value) && rule.value.includes(attrValue);
    case "nin": return Array.isArray(rule.value) && !rule.value.includes(attrValue);
    case "gt":  return Number(attrValue) > Number(rule.value);
    case "lt":  return Number(attrValue) < Number(rule.value);
    default:    return false;
  }
}
```

### 使用例: 新デザインの段階的ロールアウト

```typescript
// 10% のユーザーに新UIを表示
const { value: showNewUI } = await evaluateFlag<boolean>(
  "new_timeline_design",
  { userId: currentUser.id, tier: currentUser.tier }
);

if (showNewUI) {
  return <NewTimelineLayout tweets={tweets} />;
} else {
  return <ClassicTimelineLayout tweets={tweets} />;
}
```

### SSE (Server-Sent Events) によるリアルタイム更新

```typescript
// GET /api/flags/stream — SSE endpoint
app.get("/api/flags/stream", async (c) => {
  const stream = new ReadableStream({
    start(controller) {
      const encoder = new TextEncoder();

      // 初回: 全フラグ送信
      const sendFlags = async () => {
        const flags = await getAllFlags();
        const data = `data: ${JSON.stringify(flags)}\n\n`;
        controller.enqueue(encoder.encode(data));
      };

      sendFlags();

      // フラグ変更時に通知（PostgreSQL LISTEN/NOTIFY）
      const interval = setInterval(async () => {
        await sendFlags();
      }, 30_000); // 30秒ポーリング（LISTEN/NOTIFY未使用時）

      // Cleanup
      c.req.raw.signal.addEventListener("abort", () => {
        clearInterval(interval);
        controller.close();
      });
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
    },
  });
});
```

### Admin API

| メソッド | パス | 説明 |
|---------|------|------|
| GET | `/api/flags` | 全フラグ一覧 |
| GET | `/api/flags/:key` | フラグ評価（現在のユーザーコンテキスト） |
| POST | `/api/flags` | フラグ作成 |
| PATCH | `/api/flags/:key` | フラグ更新 |
| DELETE | `/api/flags/:key` | フラグ削除 |
| GET | `/api/flags/stream` | SSEリアルタイム更新 |

---

# 課題2: GraphQL Federation 移行パス

## tRPC → GraphQL Federation の段階的移行戦略

現在のtRPC v11は**モノリス内の型安全通信**として最適ですが、将来のマイクロサービス分割時にはGraphQL Federationが必要になります。**両方を共存させる設計**を採用します。

### 移行ロードマップ

```
Phase 1 (現在): tRPC モノリス
  ┌─────────────────────────────────────┐
  │ Next.js ──tRPC──▶ Hono API (全機能) │
  └─────────────────────────────────────┘

Phase 2 (v2.3): tRPC + GraphQL サブグラフ共存
  ┌──────────────────────────────────────────────────┐
  │ Next.js ──tRPC──▶ Hono API                       │
  │          ──GQL──▶ Apollo Subgraph (User/Tweet)   │
  └──────────────────────────────────────────────────┘

Phase 3 (将来): GraphQL Federation Gateway
  ┌──────────────────────────────────────────────────┐
  │ Next.js ──GQL──▶ AppSync/Apollo Router           │
  │                   ├──▶ User Subgraph             │
  │                   ├──▶ Tweet Subgraph            │
  │                   ├──▶ Payment Subgraph          │
  │                   └──▶ Notification Subgraph     │
  └──────────────────────────────────────────────────┘
```

## 実装: `apps/api/src/graphql/schema.ts`

```typescript
import { buildSubgraphSchema } from "@apollo/subgraph";
import { gql } from "graphql-tag";
import { db } from "@xclone/db";
import { users, tweets } from "@xclone/db/schema";
import { eq, desc } from "drizzle-orm";
import DataLoader from "dataloader";

// ─── Type Definitions (SDL) ─────────────────────────────────────────

const typeDefs = gql`
  extend schema
    @link(url: "https://specs.apollo.dev/federation/v2.0",
          import: ["@key", "@shareable", "@external"])

  type User @key(fields: "id") {
    id: ID!
    username: String!
    displayName: String!
    avatarUrl: String
    bio: String
    tier: UserTier!
    followersCount: Int!
    followingCount: Int!
    tweets(first: Int = 20, after: String): TweetConnection!
    createdAt: String!
  }

  enum UserTier {
    FREE
    PREMIUM
  }

  type Tweet @key(fields: "id") {
    id: ID!
    content: String!
    author: User!
    likesCount: Int!
    retweetsCount: Int!
    repliesCount: Int!
    media: [Media!]!
    hashtags: [String!]!
    createdAt: String!
  }

  type Media @shareable {
    url: String!
    type: MediaType!
    blurhash: String
    width: Int
    height: Int
  }

  enum MediaType {
    IMAGE
    VIDEO
    GIF
  }

  type TweetConnection {
    edges: [TweetEdge!]!
    pageInfo: PageInfo!
  }

  type TweetEdge {
    node: Tweet!
    cursor: String!
  }

  type PageInfo @shareable {
    hasNextPage: Boolean!
    endCursor: String
  }

  type Query {
    user(id: ID!): User
    userByUsername(username: String!): User
    timeline(first: Int = 20, after: String): TweetConnection!
    tweet(id: ID!): Tweet
    trending(limit: Int = 10): [String!]!
  }
`;

// ─── DataLoaders (N+1 Prevention) ────────────────────────────────

const createUserLoader = () =>
  new DataLoader<string, typeof users.$inferSelect>(async (ids) => {
    const results = await db
      .select()
      .from(users)
      .where(inArray(users.id, [...ids]));

    const userMap = new Map(results.map((u) => [u.id, u]));
    return ids.map((id) => userMap.get(id)!);
  });

// ─── Resolvers ──────────────────────────────────────────────────────

const resolvers = {
  Query: {
    user: async (_: unknown, { id }: { id: string }) => {
      const [user] = await db
        .select()
        .from(users)
        .where(eq(users.id, id));
      return user ?? null;
    },

    timeline: async (
      _: unknown,
      { first, after }: { first: number; after?: string }
    ) => {
      const limit = Math.min(first, 50);
      const results = await db
        .select()
        .from(tweets)
        .orderBy(desc(tweets.createdAt))
        .limit(limit + 1);

      const hasNextPage = results.length > limit;
      const edges = results.slice(0, limit).map((tweet) => ({
        node: tweet,
        cursor: Buffer.from(tweet.id).toString("base64"),
      }));

      return {
        edges,
        pageInfo: {
          hasNextPage,
          endCursor: edges[edges.length - 1]?.cursor ?? null,
        },
      };
    },
  },

  User: {
    __resolveReference: async (ref: { id: string }, ctx: { userLoader: DataLoader<string, unknown> }) => {
      return ctx.userLoader.load(ref.id);
    },
  },

  Tweet: {
    author: async (tweet: { authorId: string }, _: unknown, ctx: { userLoader: DataLoader<string, unknown> }) => {
      return ctx.userLoader.load(tweet.authorId);
    },
  },
};

// ─── Build Schema ───────────────────────────────────────────────────

export const schema = buildSubgraphSchema([{ typeDefs, resolvers }]);

export const createContext = () => ({
  userLoader: createUserLoader(),
});
```

### N+1 問題の解決: DataLoader

```
# Without DataLoader:
Timeline(20 tweets)
  → 20 × SELECT * FROM users WHERE id = ?  ← 20回のDBクエリ

# With DataLoader:
Timeline(20 tweets)
  → 1 × SELECT * FROM users WHERE id IN (?, ?, ..., ?)  ← 1回のDBクエリ
```

**DataLoader** はGraphQLのリクエストライフサイクル内で同一キーへのアクセスを自動バッチ化します。

## AppSync Gateway: `infra/terraform/modules/appsync/main.tf`

```hcl
resource "aws_appsync_graphql_api" "gateway" {
  name                = "xclone-graphql-${var.environment}"
  authentication_type = "AMAZON_COGNITO_USER_POOLS"
  schema              = file("${path.module}/schema.graphql")

  user_pool_config {
    user_pool_id   = var.cognito_user_pool_id
    aws_region     = var.region
    default_action = "ALLOW"
  }

  additional_authentication_provider {
    authentication_type = "API_KEY"
  }

  xray_enabled = true

  tags = {
    Environment = var.environment
    Service     = "xclone-graphql"
  }
}

# ─── WAF for Rate Limiting ─────────────────────────────────────────

resource "aws_wafv2_web_acl_association" "appsync" {
  resource_arn = aws_appsync_graphql_api.gateway.arn
  web_acl_arn  = aws_wafv2_web_acl.graphql.arn
}

resource "aws_wafv2_web_acl" "graphql" {
  name  = "xclone-graphql-waf-${var.environment}"
  scope = "REGIONAL"

  default_action {
    allow {}
  }

  rule {
    name     = "rate-limit"
    priority = 1

    action {
      block {}
    }

    statement {
      rate_based_statement {
        limit              = 2000
        aggregate_key_type = "IP"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "xclone-graphql-rate-limit"
      sampled_requests_enabled   = true
    }
  }

  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "xclone-graphql-waf"
    sampled_requests_enabled   = true
  }
}

# ─── Caching with ElastiCache ──────────────────────────────────────

resource "aws_appsync_api_cache" "gateway" {
  api_id               = aws_appsync_graphql_api.gateway.id
  type                 = "SMALL"
  api_caching_behavior = "PER_RESOLVER_CACHING"
  ttl                  = 60
  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
}
```

---

# 課題3: コスト最適化ダッシュボード

## アーキテクチャ

```
┌─────────────┐    ┌──────────────────┐    ┌─────────────┐
│ Hono API    │    │ Prometheus       │    │ Grafana     │
│             │    │                  │    │             │
│ cost-       │──▶ │ xclone_request_  │──▶ │ Cost        │
│ tracker.ts  │    │ cost_estimate    │    │ Dashboard   │
│ (per-req    │    │ xclone_daily_    │    │ (8 panels)  │
│  metrics)   │    │ cost_total       │    │             │
└─────────────┘    └──────────────────┘    └─────────────┘
         │
         │         ┌──────────────────┐
         └────────▶│ CloudWatch       │
                   │ AWS/Billing      │──▶ Grafana
                   │ (actual costs)   │    (actual vs est)
                   └──────────────────┘
```

## 実装: `apps/api/src/services/cost-tracker.ts`

```typescript
import { createMiddleware } from "hono/factory";

// ─── Cost Constants (per unit, USD) ─────────────────────────────────

const COSTS = {
  // Fargate: $0.04048/vCPU/hour, $0.004445/GB/hour
  computePerMs:    0.04048 / 3_600_000, // per vCPU-ms
  memoryPerMs:     0.004445 / 3_600_000, // per GB-ms

  // Aurora Serverless v2: $0.12/ACU/hour
  dbQueryBase:     0.12 / 3_600_000 * 0.5, // 0.5 ACU per query (estimated)

  // S3: $0.023/GB/month, $0.0004 per 1000 GETs
  s3Get:           0.0004 / 1000,
  s3Put:           0.005 / 1000,

  // ElastiCache: $0.068/hour (cache.r7g.large)
  cacheOp:         0.068 / 3_600_000,

  // Data Transfer: $0.114/GB (to internet)
  dataTransferPerByte: 0.114 / (1024 * 1024 * 1024),

  // OpenSearch: $0.269/hour (m6g.large.search)
  searchQuery:     0.269 / 3_600_000 * 2, // ~2ms per query
} as const;

// ─── Metrics Storage ────────────────────────────────────────────────

interface CostMetrics {
  totalRequests: number;
  totalEstimatedCost: number;
  costByEndpoint: Map<string, number>;
  costByService: {
    compute: number;
    database: number;
    cache: number;
    storage: number;
    search: number;
    transfer: number;
  };
}

const metrics: CostMetrics = {
  totalRequests: 0,
  totalEstimatedCost: 0,
  costByEndpoint: new Map(),
  costByService: {
    compute: 0,
    database: 0,
    cache: 0,
    storage: 0,
    search: 0,
    transfer: 0,
  },
};

// ─── Cost Estimation Middleware ──────────────────────────────────────

export function costTracker() {
  return createMiddleware(async (c, next) => {
    const start = performance.now();

    await next();

    const duration = performance.now() - start;
    const endpoint = `${c.req.method} ${c.req.routePath}`;
    const responseSize = parseInt(c.res.headers.get("content-length") ?? "0", 10);

    // Estimate cost components
    const computeCost = duration * COSTS.computePerMs;
    const dbCost = estimateDbCost(c.req.path);
    const cacheCost = COSTS.cacheOp; // assume 1 cache op per request
    const transferCost = responseSize * COSTS.dataTransferPerByte;
    const searchCost = c.req.path.includes("/search") ? COSTS.searchQuery : 0;

    const totalCost = computeCost + dbCost + cacheCost + transferCost + searchCost;

    // Update metrics
    metrics.totalRequests++;
    metrics.totalEstimatedCost += totalCost;
    metrics.costByEndpoint.set(
      endpoint,
      (metrics.costByEndpoint.get(endpoint) ?? 0) + totalCost
    );
    metrics.costByService.compute += computeCost;
    metrics.costByService.database += dbCost;
    metrics.costByService.cache += cacheCost;
    metrics.costByService.transfer += transferCost;
    metrics.costByService.search += searchCost;

    // Add cost header (debug mode only)
    if (process.env.NODE_ENV !== "production") {
      c.header("X-Estimated-Cost-USD", totalCost.toFixed(8));
    }
  });
}

function estimateDbCost(path: string): number {
  // Rough heuristics based on endpoint
  if (path.includes("/timeline")) return COSTS.dbQueryBase * 3; // JOIN heavy
  if (path.includes("/tweets"))   return COSTS.dbQueryBase * 2;
  if (path.includes("/auth"))     return COSTS.dbQueryBase * 1;
  return COSTS.dbQueryBase;
}

// ─── Prometheus Metrics Export ──────────────────────────────────────

export function getPrometheusMetrics(): string {
  const lines: string[] = [];

  lines.push("# HELP xclone_request_cost_estimate Estimated cost per request in USD");
  lines.push("# TYPE xclone_request_cost_estimate counter");
  lines.push(`xclone_request_cost_estimate ${metrics.totalEstimatedCost.toFixed(8)}`);

  lines.push("# HELP xclone_total_requests Total number of requests");
  lines.push("# TYPE xclone_total_requests counter");
  lines.push(`xclone_total_requests ${metrics.totalRequests}`);

  lines.push("# HELP xclone_cost_by_service Estimated cost by AWS service in USD");
  lines.push("# TYPE xclone_cost_by_service gauge");
  for (const [service, cost] of Object.entries(metrics.costByService)) {
    lines.push(`xclone_cost_by_service{service="${service}"} ${cost.toFixed(8)}`);
  }

  lines.push("# HELP xclone_cost_per_endpoint Estimated cost per endpoint in USD");
  lines.push("# TYPE xclone_cost_per_endpoint counter");
  for (const [endpoint, cost] of metrics.costByEndpoint) {
    const [method, path] = endpoint.split(" ");
    lines.push(`xclone_cost_per_endpoint{method="${method}",path="${path}"} ${cost.toFixed(8)}`);
  }

  return lines.join("\n");
}
```

### コスト単価表

| サービス | 単位 | 単価 (USD) | 1万リクエスト当たり |
|---------|------|-----------|-------------------|
| Fargate (compute) | vCPU-ms | $0.0000000112 | $0.0034 |
| Aurora Serverless v2 | クエリ | $0.0000000167 | $0.0005 |
| ElastiCache | 操作 | $0.0000000189 | $0.0006 |
| S3 GET | リクエスト | $0.0000004 | $0.004 |
| Data Transfer | GB | $0.114 | 〜$0.001 |
| **合計** | | | **〜$0.01/万リクエスト** |

### Grafana ダッシュボード

8パネル構成のGrafanaダッシュボードを `monitoring/cost-dashboard.json` として定義：

| # | パネル | データソース | 表示形式 |
|---|--------|-------------|---------|
| 1 | 月次コスト（今月 vs 先月） | CloudWatch | Stat |
| 2 | サービス別コスト内訳 | CloudWatch | Pie Chart |
| 3 | 日次コストトレンド（30日） | CloudWatch | Time Series |
| 4 | コスト異常アラート（>20%急増） | CloudWatch | Alert List |
| 5 | Reserved vs On-Demand利用率 | CloudWatch | Bar Gauge |
| 6 | S3ストレージクラス分布 | CloudWatch | Pie Chart |
| 7 | データ転送コスト | CloudWatch | Time Series |
| 8 | APIエンドポイント別コスト | Prometheus | Table |

```
┌──────────────────────────────────────────────────────────────┐
│  📊 XClone Cost Dashboard                                    │
├──────────────┬──────────────┬──────────────┬─────────────────┤
│ Monthly Cost │ Service      │ Daily Trend  │ Anomaly Alerts  │
│   $142.50    │ Breakdown    │ ▁▂▃▄▅▆▇▇▇   │ ⚠ S3 +25%       │
│  (vs $138)   │ 🟦EKS 45%   │              │ ✅ Others OK    │
│              │ 🟩Aurora 25% │              │                 │
│              │ 🟨Redis 15%  │              │                 │
├──────────────┼──────────────┼──────────────┼─────────────────┤
│ RI Usage     │ S3 Classes   │ Transfer     │ Cost/Endpoint   │
│ ██████░░ 75% │ 🟦Std 60%   │ ▂▃▄▃▂▁      │ /timeline $0.04 │
│              │ 🟩IA  30%   │              │ /search   $0.02 │
│              │ 🟨Glacier10% │              │ /auth     $0.01 │
└──────────────┴──────────────┴──────────────┴─────────────────┘
```

---

# 振り返り（v2.3）

## 解消した3課題の効果

| # | 課題 | 解決策 | 効果 |
|---|------|--------|------|
| 1 | Feature Flag | PostgreSQL + SSE + ターゲティング | **外部サービス不要**で段階的ロールアウト |
| 2 | GraphQL Federation | Apollo Subgraph + AppSync | マイクロサービス分割への**移行パス確保** |
| 3 | コスト最適化 | Grafana + Prometheus + CloudWatch | **リクエスト単位のコスト可視化** |

## v2.0 → v2.3 の全体推移

| バージョン | ファイル数 | 主な改善領域 |
|-----------|-----------|-------------|
| v2.0 | 39 | フルスタック基盤 |
| v2.1 | +11 (50) | 品質・運用・型安全・データ整合性 |
| v2.2 | +5 (55) | パフォーマンス・スケーラビリティ |
| v2.3 | +6 (61) | DX・コスト可視化・API進化 |

## v2.3の残課題

| # | 課題 | 重要度 | 詳細 |
|---|------|--------|------|
| 1 | **E2Eテストの拡充** | Low | 現在の10ケースからHappy Path以外（エラー系、エッジケース）を追加すべき |
| 2 | **Terraformモジュールの統合テスト** | Low | `terratest` によるインフラコードのE2Eテストが未実装 |

残課題の重要度はいずれも **Low** であり、プロダクションに大きな影響を与えるものではありません。これをもって改善イテレーションを完了とします。

---

## シリーズまとめ

| 記事 | テーマ | ファイル数 |
|------|--------|-----------|
| [v2.0](https://qiita.com/ymaeda_it/items/902aa019456836624081) | フルスタック基盤（Hono+Bun / Next.js 15 / Drizzle / ArgoCD / Linkerd / OTel） | 39 |
| [v2.1](https://qiita.com/ymaeda_it/items/e44ee09728795595efaa) | 品質強化（Playwright / ISM / マルチリージョン / tRPC / CDC） | +11 |
| [v2.2](https://qiita.com/ymaeda_it/items/d858969cd6de808b8816) | パフォーマンス（分散Rate Limit / 画像最適化 / マルチリージョンWS） | +5 |
| **v2.3**（本記事） | **DX・コスト最適化（Feature Flag / GraphQL Federation / コストダッシュボード）** | **+6** |
| **合計** | | **61ファイル** |

---

*この記事は [Qiita](https://qiita.com/) にも投稿しています。*
