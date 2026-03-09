---
title: "Electron + Phaserでインベントリ管理オートバトラーゲームを作った"
emoji: "🎮"
type: "tech"
topics: ["electron", "gamedev", "typescript", "phaser"]
published: true
---

## TL;DR

**Backpack Game** は、Backpack Battles にインスパイアされたインベントリ管理型オートバトラーゲームです。Electron + Phaser 3 で開発し、デスクトップアプリとして配布しています。

## 技術スタック

| 用途 | 技術 |
|------|------|
| デスクトップ | Electron 30 |
| ゲームエンジン | Phaser 3.80 |
| ビルド | Vite 5 |
| 言語 | TypeScript |
| パッケージング | electron-builder |

## なぜ Electron + Phaser？

ブラウザゲームとして作る選択肢もありましたが、以下の理由でデスクトップアプリにしました：

- **パフォーマンス** - ローカル実行でレンダリングが安定
- **配布** - electron-builder で各OS向けインストーラーを生成
- **オフライン** - ネット接続不要で遊べる

Phaser 3 はHTML5ゲームエンジンとして成熟しており、2Dゲームには最適です。

## 開発のポイント

### Vite + Electron の統合
Vite の高速HMR と Electron のメインプロセスを `concurrently` で並列起動。開発時はブラウザでも確認でき、本番はElectronでパッケージング。

### Phaser のゲームループ
インベントリのドラッグ&ドロップ、アイテムの配置判定、バトルシミュレーションをPhaserのシーンシステムで実装。

## まとめ

Electron + Phaser + Vite + TypeScript は、2Dデスクトップゲーム開発に最適な組み合わせです。Web技術の知識がそのまま活かせます。
