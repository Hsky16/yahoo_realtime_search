# yahoo_realtime_search

Yahoo!リアルタイム検索を簡単に呼び出せる MCP です。

ツール説明等は全て日本語なので検索も日本語が多めになるかもしれません。

~~(そもそもYahooリアルタイム検索なんて日本人しか使ってないだろ)~~

参考にした記事:

[Yahooリアルタイム検索のAPIが本当に有能だからみんな使ったほうがいい話](https://qiita.com/maebahesioru/items/4fc4e6baf5b96aa84061)

APIをまとめてくださってありがとうございます。

> この API は公式API ではありません。節度を持って、自己責任で使いましょう。

## 概要

Yahoo!リアルタイム検索の検索結果を MCP ツールとして呼び出せます。

X の最近の投稿、反応、画像や動画付き投稿を調べたいときに使う想定です。

標準では、エージェントが読みやすい Markdown 形式で結果を返します。

## 使い方

### AI に導入を任せる

Claude Code や Codex などの AI コーディングツールに以下をそのまま貼り付ければ、クローンから設定ファイルへの追記まで全部やってくれるはず。

```
以下のMCPサーバーを導入してください。

リポジトリ: https://github.com/Hsky16/yahoo_realtime_search

手順:
1. 適切な場所にgit cloneする
2. 依存関係をインストールする
3. このMCPクライアントの設定ファイルにサーバー設定を追記する
```

### 手動で導入する場合
手動で入れたい場合は以下のコマンドをパワーシェルで順番に実行してください。
わからないことがあったらAIに聞けばいい感じにやってくれると思います。

```powershell
git clone https://github.com/Hsky16/yahoo_realtime_search.git
cd yahoo_realtime_search
uv sync
```

MCP クライアントの設定ファイルに以下を追記します（`/path/to/yahoo_realtime_search` はご自身の環境のパスにしてください）。

```json
{
  "mcpServers": {
    "yahoo_realtime_search": {
      "command": "uv",
      "args": [
        "--directory",
        "/path/to/yahoo_realtime_search",
        "run",
        "yahoo-realtime-search"
      ]
    }
  }
}
```

## ツール

- `search_realtime`: Yahoo!リアルタイム検索を呼び出します。

この MCP を使うべき場面、Markdown の出力構造、`output_format` の使い分けは、MCP の instructions と description に入れています。

運用方針にあわせてClaudeCode、Codex等用いて改変するのがおすすめです。

## ツール呼び出し例

画像付き投稿を人気順で 20 件:

```json
{
  "query": "#AI",
  "sort": "popular",
  "media_type": "image",
  "limit": 20,
  "output_format": "markdown"
}
```

特定ユーザーの動画付き投稿:

```json
{
  "query": "ID:nhk_news",
  "media_type": "video",
  "limit": 10
}
```

2 ページ分をまとめて取得:

```json
{
  "query": "アニメ",
  "pages": 2,
  "limit": 20
}
```

期間指定:

```json
{
  "query": "アニメ",
  "since": "2026-01-01T00:00:00+09:00",
  "until": "2026-03-01T00:00:00+09:00"
}
```

## ライセンス

MIT License です。利用、改変、再配布、商用利用などご自由にお使いください。
