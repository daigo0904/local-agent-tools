"""エコーステートネットワーク（リザバーコンピューティング）。numpy だけで書く。

リザバー（中の重み）は乱数で作って固定し、学習するのは最後の読み出し（線形回帰）だけ。
だから CPU で数秒で覚えられ、手元の LLM と GPU・メモリを取り合わない。
"""
import numpy as np


class ESN:
    def __init__(self, 入力の数, 出力の数, 大きさ=300, 半径=0.9, 漏れ=0.3, 入力の強さ=0.5,
                 まばら=0.1, 正則化=1e-2, 種=0):
        r = np.random.default_rng(種)
        W = r.uniform(-1, 1, (大きさ, 大きさ)) * (r.random((大きさ, 大きさ)) < まばら)
        W *= 半径 / max(abs(np.linalg.eigvals(W)))          # スペクトル半径をそろえる（反響が消えも暴れもしない）
        self.W = W
        self.Win = r.uniform(-入力の強さ, 入力の強さ, (大きさ, 入力の数 + 1))
        self.漏れ, self.正則化 = 漏れ, 正則化
        self.出力の数 = 出力の数
        self.Wout = None

    def 状態の並び(self, 入力の並び):
        """入力（one-hot の並び）→ 各時点のリザバーの状態。会話ごとに 0 から始める。"""
        x = np.zeros(self.W.shape[0])
        out = []
        for u in 入力の並び:
            pre = self.Win @ np.concatenate(([1.0], u)) + self.W @ x
            x = (1 - self.漏れ) * x + self.漏れ * np.tanh(pre)
            out.append(x.copy())
        return np.array(out)

    def 覚える(self, 状態たち, 答えたち):
        X = np.vstack([np.hstack([np.ones((len(s), 1)), s]) for s in 状態たち])
        Y = np.vstack(答えたち)
        A = X.T @ X + self.正則化 * np.eye(X.shape[1])
        self.Wout = np.linalg.solve(A, X.T @ Y).T
        return self

    def 予測(self, 状態):
        """→ 次の1手の確率（ソフトマックス）。"""
        z = np.hstack([np.ones((len(状態), 1)), 状態]) @ self.Wout.T
        z = z - z.max(axis=1, keepdims=True)
        p = np.exp(z * 4.0)                                  # 線形出力を確率にするための温度（試す前に固定）
        return p / p.sum(axis=1, keepdims=True)
