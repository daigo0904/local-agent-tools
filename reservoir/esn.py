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

    def 出力(self, 状態):
        """読み出しの生の値（確率にする前）。"""
        return np.hstack([np.ones((len(状態), 1)), 状態]) @ self.Wout.T

    def 予測(self, 状態, 温度=4.0):
        """→ 次の1手の確率（ソフトマックス）。温度は実験1では 4.0 に固定、実験1'では検証用で決める。"""
        z = self.出力(状態)
        z = z - z.max(axis=1, keepdims=True)
        p = np.exp(z * 温度)
        return p / p.sum(axis=1, keepdims=True)


class ロジスティック読み出し:
    """読み出しを、確率を当てる学び方（ソフトマックス＋交差エントロピー＋L2）で学ぶ。

    線形回帰の読み出しは確率の較正が苦手で、実験1・1'で「自信を持って外す」が出た（対数損失で対照に負けた）。
    学び方の手順（Adam・学習率0.05・500回・0から）は実験1''で走らせる前に固定した。"""

    def __init__(self, λ=1e-3, 学習率=0.05, 回数=500):
        self.λ, self.lr, self.回数 = λ, 学習率, 回数
        self.W = None

    def 覚える(self, X, y, V):
        X = np.hstack([np.ones((len(X), 1)), X])
        n, d = X.shape
        W = np.zeros((d, V))
        Y = np.eye(V)[y]
        m = np.zeros_like(W)
        v = np.zeros_like(W)
        b1, b2, ε = 0.9, 0.999, 1e-8
        for t in range(1, self.回数 + 1):
            z = X @ W
            z -= z.max(axis=1, keepdims=True)
            p = np.exp(z)
            p /= p.sum(axis=1, keepdims=True)
            g = X.T @ (p - Y) / n
            g[1:] += self.λ * W[1:]                          # 定数項には L2 を掛けない
            m = b1 * m + (1 - b1) * g
            v = b2 * v + (1 - b2) * g * g
            W -= self.lr * (m / (1 - b1 ** t)) / (np.sqrt(v / (1 - b2 ** t)) + ε)
        self.W = W
        return self

    def 予測(self, X):
        z = np.hstack([np.ones((len(X), 1)), X]) @ self.W
        z -= z.max(axis=1, keepdims=True)
        p = np.exp(z)
        return p / p.sum(axis=1, keepdims=True)
