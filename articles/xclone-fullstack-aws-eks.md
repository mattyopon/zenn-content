---
title: "X(Twitter)クローンをReact + Express + AWS EKSでフルスタック構築した"
emoji: "🐦"
type: "tech"
topics: ["react", "aws", "kubernetes", "typescript"]
published: true
---

## TL;DR

X（旧Twitter）のクローンアプリを、React + Express + PostgreSQL でフルスタック開発し、AWS CDK で EKS / RDS / CloudFront / ALB のインフラを構築しました。

## 技術スタック

### フロントエンド
- React + Vite + Tailwind CSS
- TypeScript

### バックエンド
- Node.js + Express
- PostgreSQL

### インフラ (AWS CDK)
- **EKS** - Kubernetes クラスタ
- **RDS** - PostgreSQL マネージド DB
- **CloudFront** - CDN
- **ALB** - ロードバランサー

## アーキテクチャ

```
CloudFront ──> ALB ──> EKS (Express Pods)
                              │
                         RDS (PostgreSQL)
```

## IaC (AWS CDK)

インフラは全て AWS CDK (TypeScript) で定義。VPC、サブネット、セキュリティグループ、IAMロールまで含めてコード管理しています。

## 学び

- **EKS の運用** は想像以上に複雑。小規模なら ECS Fargate のほうが楽
- **CDK** は CloudFormation より遥かに書きやすい
- **フルスタック + インフラ** を一人で構築する経験は非常に価値がある

## まとめ

SNSのクローンは、認証・リアルタイム更新・スケーリング等、Webアプリの主要課題を網羅的に学べる最高の題材です。AWS EKS での本番想定のインフラ構築まで行うことで、実務レベルの経験が得られました。

