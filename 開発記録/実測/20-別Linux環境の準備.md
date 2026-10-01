# 別Linux環境の再現準備（2026-09-26）

`comparison/portable-bundle/` に、固定B/Cコード、全体比較実行器、ubuntu-22.04/24.04のGitHub Actions workflowを同梱。ファイルハッシュはmanifest.json。リポジトリのルートへ配置してworkflow_dispatchで実行する構成。bwrapの起動自体が通らなければ比較に進まず、失敗ログをartifactに残す。

実機側の結果はまだ無い。利用していた `ahogorirappa/guardrun-portability` の直近失敗run 35976625478/check 107558551391のannotationをAPIで確認したところ、支払い失敗またはspending limitを理由にジョブが開始されていない。ログも存在しない。課金設定は変更していない。

別のコンテナイメージは同じOrbStackカーネルを共有するので、「別Linux実機の再現」の代わりには数えない。今回作ったworkflowは未実行。枠が利用できる状態になったら固定版を配置・実行し、カーネルとABI、同じケースの動作差を比較する。古いABIで攻撃が通った場合も除外せず報告する。
