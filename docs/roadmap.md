# Roadmap

## P0（現在）

- [ ] inline介入のstreamKey完全化（stale event guardのテストカバレッジ向上）
- [ ] 実機確認チェックリスト遂行
  - textareaにフォーカス -> タイプ -> Enter -> カーソル位置から再生成
  - 矢印キー移動 -> 空Enter -> truncate + 再生
  - 生成中編集 -> Enter -> abort + 割り込み再生成
  - Shift+Enter改行 / Escape復帰 / IME Enter無視

## P1（次）

- [ ] README / usage のさらなる改善
- [ ] frontend build / test 手順の明文化（完了済み: development.md）
- [ ] CI の整備（GitHub Actions での自動テスト）

## P2（将来）

- [ ] UX説明図の追加
- [ ] examples / ユースケースの追加
- [ ] モデル別の推奨設定ドキュメント

## P3（未定）

- [ ] 永続化（履歴保存）
- [ ] 分岐ツリーUIの検討
- [ ] 自動矛盾検出
