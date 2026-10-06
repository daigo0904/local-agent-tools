#!/usr/bin/env python3
"""実験6：時系列のやり方の総当たり（参考・副次）。決まりは RESERVOIR.md（新しいデータの結果を見る前に固定）。

    ~/未踏ターゲット/.venv/bin/python reservoir/実験6.py --偽で試す   偽の時系列で、各道具が動くかだけ確かめる
    ~/未踏ターゲット/.venv/bin/python reservoir/実験6.py --読めるか   本物の材料の形だけ出す（始まりの件数は出さない）
    ~/未踏ターゲット/.venv/bin/python reservoir/実験6.py --判定      決まりどおりに1回走らせる（2026-11-03 まで鍵）

GRU・LSTM・TCN・Transformer は torch が要る（~/未踏ターゲット/.venv に入れてある）。
torch が無い機械では、その4つを「走らせられなかった」と書いて残りだけ走らせる（黙って抜かない）。

並べるもの：①EWMA ②Markov ②'HMM ③窓＋ロジスティック ④ESN（実験5そのもの） ⑤GRU ⑤'LSTM ⑥TCN ⑦Transformer
対照は実験4の R5（規則のどれか）。
"""
import bisect
import json
import os
import re
import sys
import time
from datetime import datetime

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import 実験4 as E4                      # noqa: E402  材料の読み方・始まりの定義・規則は実験4と同じものを使う
from esn import ESN, ロジスティック読み出し  # noqa: E402

窓の長さ = 60
検証の長さ = 7 * 24 * 60                # 作る側の最後の1週間（分）
λ候補 = (1e-4, 1e-3, 1e-2)
種たち = (0, 1, 2, 3, 4)


# ───────────────────────── 材料：1分ごとの数値の時系列 ─────────────────────────

機械の数値 = ("空き_MiB", "使用中_MiB", "待機_MiB", "固定_MiB", "圧縮_MiB", "スワップ使用_MiB")


def 速さを読む(道たち):
    """llama-server の時間の行から、前処理と生成の速さ（tok/s）を時刻つきで。時刻の無い行は直前に見えた時刻を使う。"""
    前処理, 生成 = [], []
    今 = None
    for 道 in 道たち:
        for l in open(道, errors="replace"):
            m = re.search(r"time=(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)", l)
            if m:
                今 = datetime.fromisoformat(m.group(1)).timestamp()
            elif l.startswith("[GIN]"):
                m = re.search(r"\[GIN\] (\d{4}/\d\d/\d\d) - (\d\d:\d\d:\d\d)", l)
                if m:
                    今 = datetime.strptime(m.group(1) + " " + m.group(2), "%Y/%m/%d %H:%M:%S").timestamp()
            if 今 is None:
                continue
            m = re.search(r"(prompt eval|\|\s+eval) time =.*?([\d.]+) tokens per second", l)
            if m:
                (前処理 if "prompt" in m.group(1) else 生成).append((今, float(m.group(2))))
    return 前処理, 生成


def 系列を作る(要求, 積み込み, 文脈, キャッシュ, 機械, 速さ):
    """→ (始まりの分, 数値の行列[分×数値], 4ビットの状態[分], 数値の名前)"""
    t0 = int(機械[0]["時刻"] // 60)
    t1 = int(機械[-1]["時刻"] // 60)
    n = t1 - t0 + 1
    名前 = ["負荷1", "負荷5", "負荷15", *機械の数値, "スワップ入の増え", "スワップ出の増え",
          "ollamaのRSS", "ollamaのCPU", "積まれたモデルの数", "VRAM",
          "要求の数", "積み込みの数", "キャッシュの割合", "文脈の長さの種類", "前処理の速さ", "生成の速さ"]
    X = np.full((n, len(名前)), np.nan)
    前 = None
    for r in 機械:
        i = int(r["時刻"] // 60) - t0
        負荷 = r.get("負荷") or [np.nan] * 3
        資源 = r.get("ollama資源") or []
        モデル = r.get("積まれたモデル") or []
        行 = [*負荷[:3], *[r.get(k, np.nan) for k in 機械の数値],
             (r.get("スワップ入_回", 0) - 前.get("スワップ入_回", 0)) if 前 else 0.0,
             (r.get("スワップ出_回", 0) - 前.get("スワップ出_回", 0)) if 前 else 0.0,
             sum(x.get("RSS_MiB", 0) for x in 資源), sum(x.get("CPU%", 0) for x in 資源),
             len(モデル), sum((x.get("VRAM_MiB") or 0) for x in モデル)]
        X[i, :len(行)] = 行
        前 = r
    k = len(名前) - 6
    数え = np.zeros((n, 2))
    for x in 要求:
        i = int(x["終"] // 60) - t0
        if 0 <= i < n:
            数え[i, 0] += 1
    for t in 積み込み:
        i = int(t // 60) - t0
        if 0 <= i < n:
            数え[i, 1] += 1
    X[:, k:k + 2] = 数え
    for t, mib, 上限 in キャッシュ:
        i = int(t // 60) - t0
        if 0 <= i < n and 上限 > 0:
            X[i, k + 2] = mib / 上限
    種類 = [set() for _ in range(n)]
    for t, c in 文脈:
        i = int(t // 60) - t0
        if 0 <= i < n:
            種類[i].add(c)
    X[:, k + 3] = [len(s) for s in 種類]
    for j, 並び in ((k + 4, 速さ[0]), (k + 5, 速さ[1])):
        for t, v in 並び:
            i = int(t // 60) - t0
            if 0 <= i < n:
                X[i, j] = v
    # 抜けは直前の値で埋める（未来の値は使わない）。最初から無いものは 0
    for j in range(X.shape[1]):
        last = 0.0
        for i in range(n):
            if np.isnan(X[i, j]):
                X[i, j] = last
            else:
                last = X[i, j]
    # 4ビットの状態（Markov・HMM 用）：各分の終わりで R1〜R4 を評価
    機械の時刻 = [m["時刻"] for m in 機械]
    状態 = np.zeros(n, dtype=int)
    for i in range(n):
        r = E4.規則({"始": (t0 + i + 1) * 60}, 積み込み, 文脈, キャッシュ, 機械, 機械の時刻)
        状態[i] = r["R1"] | (r["R2"] << 1) | (r["R3"] << 2) | (r["R4"] << 3)
    return t0, X, 状態, 名前


def 標本を作る(候補, t0, n, 積み込み, 文脈, キャッシュ, 機械):
    """→ [(使える最後の分の位置, 答え, R5)]。要求の始まる**前の分まで**しか使わない。
    機械の記録が始まって 窓の長さ 分たつ前の要求は入れない（窓が埋まらない）。"""
    機械の時刻 = [m["時刻"] for m in 機械]
    out = []
    for x, y in 候補:
        i = int(x["始"] // 60) - 1 - t0
        if 窓の長さ - 1 <= i < n:
            r5 = E4.規則(x, 積み込み, 文脈, キャッシュ, 機械, 機械の時刻)["R5"]
            out.append((i, int(y), bool(r5), x["始"]))
    return out


# ───────────────────────── 点数の付け方（全員同じ） ─────────────────────────

def roc_auc(s, y):
    s, y = np.asarray(s, float), np.asarray(y, int)
    p, q = y.sum(), len(y) - y.sum()
    if p == 0 or q == 0:
        return None
    order = np.argsort(s, kind="mergesort")
    r = np.empty(len(s))
    r[order] = np.arange(1, len(s) + 1)
    for v in np.unique(s):                     # 同点は平均順位
        m = s == v
        r[m] = r[m].mean()
    return float((r[y == 1].sum() - p * (p + 1) / 2) / (p * q))


def pr_auc(s, y):
    """平均適合率（average precision）。"""
    s, y = np.asarray(s, float), np.asarray(y, int)
    if y.sum() == 0:
        return None
    o = np.argsort(-s, kind="mergesort")
    y = y[o]
    tp = np.cumsum(y)
    return float(np.sum((tp / np.arange(1, len(y) + 1))[y == 1]) / y.sum())


def 再現と適合(警報, y):
    警報, y = np.asarray(警報, bool), np.asarray(y, int)
    tp = int((警報 & (y == 1)).sum())
    fp = int((警報 & (y == 0)).sum())
    return (tp / y.sum() if y.sum() else None), (tp / (tp + fp) if tp + fp else None)


def しきい値(作る側の点数, 割合):
    """作る側で「黙る」と言う割合が 割合 になる点数。"""
    if 割合 <= 0:
        return np.inf
    return float(np.quantile(作る側の点数, 1 - 割合))


def 区間(試す, 点数, R5, 回数=1000, 種=0):
    """始まりの要求を単位に再標本化。→ 各指標と R5 との差の95%区間"""
    rng = np.random.default_rng(種)
    y = np.array([b for _, b, _, _ in 試す])
    警報 = np.array(点数["警報"])
    s = np.array(点数["点"])
    r5 = np.array(R5)
    溜め = {"再現率の差": [], "PR-AUCの差": []}
    for _ in range(回数):
        k = rng.integers(0, len(y), len(y))
        rm, _ = 再現と適合(警報[k], y[k])
        rr, _ = 再現と適合(r5[k], y[k])
        a, b = pr_auc(s[k], y[k]), pr_auc(r5[k].astype(float), y[k])
        if rm is not None and rr is not None:
            溜め["再現率の差"].append(rm - rr)
        if a is not None and b is not None:
            溜め["PR-AUCの差"].append(a - b)
    return {k: ([round(float(np.quantile(v, 0.025)), 3), round(float(np.quantile(v, 0.975)), 3)] if v else None)
            for k, v in 溜め.items()}


# ───────────────────────── 道具たち ─────────────────────────
# どれも「作る側で学ぶ → 標本ごとに点数（大きいほど黙りそう）」の形にそろえる。
# 学ぶ(材料, 学ぶ標本, 設定) → 点数を返す関数

def _ロジスティック(F学, y学, λ):
    m = ロジスティック読み出し(λ=λ).覚える(F学, np.asarray(y学), 2)
    return lambda F: m.予測(F)[:, 1]


def 道_EWMA(材, 標本, 設定):
    α, λ = 設定
    X = 材["X"]
    E = np.zeros_like(X)
    e = X[0].copy()
    for i in range(len(X)):
        e = α * X[i] + (1 - α) * e
        E[i] = e
    f = _ロジスティック(E[[i for i, *_ in 標本]], [b for _, b, *_ in 標本], λ)
    return lambda 標: f(E[[i for i, *_ in 標]])


def 道_Markov(材, 標本, 設定):
    (k,) = 設定
    S = 材["状態"]
    鍵 = lambda i: tuple(S[i - k + 1:i + 1])
    数 = {}
    for i, b, *_ in 標本:
        a, n = 数.get(鍵(i), (0, 0))
        数[鍵(i)] = (a + b, n + 1)
    return lambda 標: np.array([(数.get(鍵(i), (0, 0))[0] + 1) / (数.get(鍵(i), (0, 0))[1] + 2) for i, *_ in 標])


def _HMMを学ぶ(S, H, 記号=16, 回数=30, 種=0):
    """離散の隠れマルコフ（Baum-Welch・スケーリング付き）。→ (π, A, B)"""
    rng = np.random.default_rng(種)
    π = np.full(H, 1 / H)
    A = rng.dirichlet(np.ones(H) * 5, H)
    B = rng.dirichlet(np.ones(記号), H)
    T = len(S)
    for _ in range(回数):
        α = np.zeros((T, H))
        c = np.zeros(T)
        α[0] = π * B[:, S[0]]
        c[0] = α[0].sum()
        α[0] /= c[0]
        for t in range(1, T):
            α[t] = (α[t - 1] @ A) * B[:, S[t]]
            c[t] = α[t].sum() or 1e-300
            α[t] /= c[t]
        β = np.ones((T, H))
        for t in range(T - 2, -1, -1):
            β[t] = (A @ (B[:, S[t + 1]] * β[t + 1])) / c[t + 1]
        γ = α * β
        γ /= γ.sum(axis=1, keepdims=True)
        ξ = np.zeros((H, H))
        for t in range(T - 1):
            ξ += (α[t][:, None] * A * (B[:, S[t + 1]] * β[t + 1])[None, :]) / c[t + 1]
        π = γ[0]
        A = ξ / ξ.sum(axis=1, keepdims=True)
        for v in range(記号):
            B[:, v] = γ[S == v].sum(axis=0) + 1e-3
        B /= B.sum(axis=1, keepdims=True)
    return π, A, B


def _前向き(S, π, A, B):
    """各分の終わりでの隠れ状態の確率（その分までしか見ない）。"""
    T, H = len(S), len(π)
    P = np.zeros((T, H))
    a = π * B[:, S[0]]
    P[0] = a / a.sum()
    for t in range(1, T):
        a = (P[t - 1] @ A) * B[:, S[t]]
        P[t] = a / (a.sum() or 1e-300)
    return P


def 道_HMM(材, 標本, 設定):
    H, λ = 設定
    学ぶ範囲 = max(i for i, *_ in 標本) + 1          # 作る側の分だけで学ぶ
    π, A, B = _HMMを学ぶ(材["状態"][:学ぶ範囲], H)
    P = _前向き(材["状態"], π, A, B)
    f = _ロジスティック(P[[i for i, *_ in 標本]], [b for _, b, *_ in 標本], λ)
    return lambda 標: f(P[[i for i, *_ in 標]])


def _窓の特徴(X, i, N):
    W = X[i - N + 1:i + 1]
    t = np.arange(N) - (N - 1) / 2
    傾き = (t @ (W - W.mean(axis=0))) / (t @ t)
    return np.concatenate([W.mean(axis=0), W.max(axis=0), W[-1], 傾き])


def 道_窓(材, 標本, 設定):
    N, λ = 設定
    X = 材["X"]
    F = lambda 標: np.array([_窓の特徴(X, i, N) for i, *_ in 標])
    f = _ロジスティック(F(標本), [b for _, b, *_ in 標本], λ)
    return lambda 標: f(F(標))


_ESNの状態 = {}


def 道_ESN(材, 標本, 設定):
    """実験5そのもの：300ノード・半径0.9・漏れ0.3・種0。時系列全体を1回流し、使える最後の分の状態を読む。"""
    (λ,) = 設定
    鍵 = id(材["X"])
    if 鍵 not in _ESNの状態:
        e = ESN(材["X"].shape[1], 1, 大きさ=300, 半径=0.9, 漏れ=0.3, 種=0)
        _ESNの状態[鍵] = e.状態の並び(材["X"])
    R = _ESNの状態[鍵]
    f = _ロジスティック(R[[i for i, *_ in 標本]], [b for _, b, *_ in 標本], λ)
    return lambda 標: f(R[[i for i, *_ in 標]])


try:
    import torch
    from torch import nn
except ImportError:                                   # torch の無い機械
    torch = None


def _深いもの(種類):
    class 網(nn.Module):
        def __init__(self, F):
            super().__init__()
            self.種類 = 種類
            if 種類 in ("GRU", "LSTM"):
                self.本体 = (nn.GRU if 種類 == "GRU" else nn.LSTM)(F, 16, batch_first=True)
                self.出口 = nn.Linear(16, 1)
            elif 種類 == "TCN":
                self.段 = nn.ModuleList([nn.Conv1d(F if k == 0 else 16, 16, 3, dilation=d) for k, d in enumerate((1, 2, 4))])
                self.出口 = nn.Linear(16, 1)
            else:  # Transformer
                self.入口 = nn.Linear(F, 16)
                self.位置 = nn.Parameter(torch.zeros(窓の長さ, 16))
                self.本体 = nn.TransformerEncoder(
                    nn.TransformerEncoderLayer(16, 2, dim_feedforward=32, dropout=0.0, batch_first=True), 1)
                self.出口 = nn.Linear(16, 1)

        def forward(self, W):                          # W: [標本, 窓, 数値]
            if self.種類 in ("GRU", "LSTM"):
                h, _ = self.本体(W)
                return self.出口(h[:, -1]).squeeze(-1)
            if self.種類 == "TCN":
                h = W.transpose(1, 2)
                for k, c in enumerate(self.段):
                    d = c.dilation[0]
                    h = torch.relu(c(nn.functional.pad(h, (2 * d, 0))))   # 因果的（未来を見ない）
                return self.出口(h[:, :, -1]).squeeze(-1)
            h = self.本体(self.入口(W) + self.位置)
            return self.出口(h[:, -1]).squeeze(-1)

    def 道(材, 標本, 設定, 検証=None, 周=None):
        """検証あり＝止めどころを探す（返り値に最良の周を付ける）。周あり＝その周まで学ぶ（学び直し）。"""
        学習率, 種 = 設定
        torch.manual_seed(種)
        X = torch.tensor(材["X"], dtype=torch.float32)
        窓 = lambda 標: torch.stack([X[i - 窓の長さ + 1:i + 1] for i, *_ in 標])
        W, y = 窓(標本), torch.tensor([b for _, b, *_ in 標本], dtype=torch.float32)
        m = 網(X.shape[1])
        opt = torch.optim.Adam(m.parameters(), lr=学習率)
        重み = torch.tensor(max(float(len(y) - y.sum()) / max(float(y.sum()), 1.0), 1.0))
        損失 = nn.BCEWithLogitsLoss(pos_weight=重み)
        最良, 最良の周, 待ち, 最良の重み = -1, 0, 0, None
        for ep in range(1, (周 or 200) + 1):
            m.train()
            for k in torch.randperm(len(y)).split(64):
                opt.zero_grad()
                損失(m(W[k]), y[k]).backward()
                opt.step()
            if 検証 is not None:
                m.eval()
                with torch.no_grad():
                    p = pr_auc(m(窓(検証)).numpy(), [b for _, b, *_ in 検証]) or 0
                if p > 最良:
                    最良, 最良の周, 待ち = p, ep, 0
                    最良の重み = {k: v.clone() for k, v in m.state_dict().items()}
                else:
                    待ち += 1
                    if 待ち >= 10:
                        break
        if 最良の重み is not None:
            m.load_state_dict(最良の重み)
        m.eval()

        def 点(標):
            with torch.no_grad():
                return m(窓(標)).numpy()
        点.最良の周 = 最良の周
        return 点
    return 道


道具 = {
    "①EWMA": (道_EWMA, [(a, l) for a in (0.1, 0.3, 0.6) for l in λ候補], False),
    "②Markov": (道_Markov, [(1,), (2,)], False),
    "②'HMM": (道_HMM, [(h, l) for h in (2, 3, 4) for l in λ候補], False),
    "③窓＋ロジスティック": (道_窓, [(n, l) for n in (5, 10, 30) for l in λ候補], False),
    "④ESN": (道_ESN, [(l,) for l in λ候補], False),
}
if torch is not None:
    torch.set_num_threads(2)                          # 記録中の機械をあまり揺らさない
    for 名, 種類 in (("⑤GRU", "GRU"), ("⑤'LSTM", "LSTM"), ("⑥TCN", "TCN"), ("⑦Transformer", "Transformer")):
        道具[名] = (_深いもの(種類), [(lr,) for lr in (1e-3, 3e-3)], True)


# ───────────────────────── 段取り（全員同じ） ─────────────────────────

def 一つを走らせる(名, 材, 作る, 試す, R5の割合):
    道, 候補, 深い = 道具[名]
    境 = max(i for i, *_ in 作る) - 検証の長さ
    学 = [s for s in 作る if s[0] <= 境]
    検 = [s for s in 作る if s[0] > 境]
    if not 学 or not 検 or sum(b for _, b, *_ in 学) == 0:
        return {"走らなかった": "作る側の学ぶ分か検証の分が空、または学ぶ分に始まりが無い"}
    種々 = 種たち if 深い else (None,)
    結果の種 = []
    for 種 in 種々:
        最良 = (-1, None, None)
        for 設定 in 候補:
            if 深い:
                f = 道(材, 学, (*設定, 種), 検証=検)
                p = pr_auc(f(検), [b for _, b, *_ in 検]) or 0
                if p > 最良[0]:
                    最良 = (p, 設定, f.最良の周)
            else:
                f = 道(材, 学, 設定)
                p = pr_auc(f(検), [b for _, b, *_ in 検]) or 0
                if p > 最良[0]:
                    最良 = (p, 設定, None)
        # 選んだ設定で作る側全体から学び直す
        f = 道(材, 作る, (*最良[1], 種), 周=max(最良[2] or 1, 1)) if 深い else 道(材, 作る, 最良[1])
        s作, s試 = f(作る), f(試す)
        th = しきい値(s作, R5の割合)
        結果の種.append({"設定": 最良[1], "検証のPR-AUC": round(最良[0], 3), "点": s試, "作る側の点": s作,
                       "警報": s試 >= th})
    # 深いものは5つの種の平均の点数を本体にする（決まりどおり）。しきい値も平均点で作る側から決め直す
    if 深い:
        s試 = np.mean([r["点"] for r in 結果の種], axis=0)
        s作 = np.mean([r["作る側の点"] for r in 結果の種], axis=0)
        本体 = {"点": s試, "警報": s試 >= しきい値(s作, R5の割合)}
    else:
        本体 = 結果の種[0]
    y = [b for _, b, *_ in 試す]
    rc, pc = 再現と適合(本体["警報"], y)
    out = {"設定": [r["設定"] for r in 結果の種], "検証のPR-AUC": [r["検証のPR-AUC"] for r in 結果の種],
           "再現率": rc, "適合率": pc, "ROC-AUC": roc_auc(本体["点"], y), "PR-AUC": pr_auc(本体["点"], y),
           "R5との差の95%区間": 区間(試す, 本体, [r5 for _, _, r5, _ in 試す])}
    if 深い:
        out["種ごとのPR-AUC"] = [pr_auc(r["点"], y) for r in 結果の種]
    return {k: (round(v, 3) if isinstance(v, float) else v) for k, v in out.items()}


def 総当たり(材, 作る, 試す, 書き出し=None):
    R5の割合 = float(np.mean([r5 for _, _, r5, _ in 作る]))
    y = [b for _, b, *_ in 試す]
    rc, pc = 再現と適合([r5 for _, _, r5, _ in 試す], y)
    結果 = {"R5（対照）": {"再現率": rc, "適合率": pc, "作る側で黙ると言った割合": round(R5の割合, 3)}}
    for 名 in 道具:
        t = time.time()
        try:
            結果[名] = 一つを走らせる(名, 材, 作る, 試す, R5の割合)
        except Exception as e:                        # noqa: BLE001  落ちた道具も表に残す
            結果[名] = {"落ちた": "%s: %s" % (type(e).__name__, e)}
        結果[名]["秒"] = round(time.time() - t, 1)
        print("  %-18s %s" % (名, {k: v for k, v in 結果[名].items() if k in ("ROC-AUC", "PR-AUC", "再現率", "適合率", "落ちた", "走らなかった", "秒")}),
              flush=True)
    if torch is None:
        for 名 in ("⑤GRU", "⑤'LSTM", "⑥TCN", "⑦Transformer"):
            結果[名] = {"走らせられなかった": "torch が無い（~/未踏ターゲット/.venv/bin/python で走らせる）"}
    if 書き出し:
        json.dump(結果, open(書き出し, "w"), ensure_ascii=False, indent=1, default=str)
    return 結果


# ───────────────────────── 偽の時系列（道具が動くかの安いテスト） ─────────────────────────

def 偽の材料(種=0, 日数=30, 入れ替え=False):
    """数値0 が6分間跳ね上がると、跳ね始めの5分後の要求が始まりになりやすい（仕込み：90%、ほかは2%）。
    1回目（14日・70%/5%）は天井が ROC-AUC 約0.85で合格線0.8に近すぎ、試す側の始まりも13件で揺れた（2026-10-07）。
    状態ビット0 は数値0 が 1.5 を超えている分。入れ替え=True は答えだけ混ぜる（対照）。"""
    rng = np.random.default_rng(種)
    n, F = 日数 * 1440, 8
    X = np.zeros((n, F))
    for j in range(F):                                # AR(1) の雑音
        e = rng.normal(0, 1, n)
        for i in range(1, n):
            X[i, j] = 0.9 * X[i - 1, j] + 0.3 * e[i]
    跳ね = rng.choice(np.arange(窓の長さ, n - 20), size=n // 200, replace=False)
    for s in 跳ね:
        X[s:s + 6, 0] += 3.0
    状態 = (X[:, 0] > 1.5).astype(int) | ((X[:, 1] > 1.5).astype(int) << 1)
    標本 = []
    for s in 跳ね:                                    # 跳ねの5分後に要求（始まりになりやすい）
        標本.append((s + 4, int(rng.random() < 0.9), bool(状態[s + 4]), 0))
    for i in rng.choice(np.arange(窓の長さ, n), size=len(跳ね) * 4, replace=False):
        標本.append((int(i), int(rng.random() < 0.02), bool(状態[i]), 0))
    標本.sort()
    if 入れ替え:
        ys = rng.permutation([b for _, b, _, _ in 標本])
        標本 = [(i, int(y), r, t) for (i, _, r, t), y in zip(標本, ys)]
    境 = int(n * 0.75)
    作る = [s for s in 標本 if s[0] < 境]
    試す = [s for s in 標本 if s[0] >= 境]
    return {"X": X, "状態": 状態}, 作る, 試す


def main():
    if "--偽で試す" in sys.argv:
        判定 = {}
        for 入れ替え in (False, True):
            print("偽の時系列（%s）" % ("答えを入れ替えた対照" if 入れ替え else "仕込みあり"), flush=True)
            _ESNの状態.clear()
            材, 作る, 試す = 偽の材料(入れ替え=入れ替え)
            判定[入れ替え] = 総当たり(材, 作る, 試す)
        print("\n道具ごとの合否（仕込みで ROC-AUC ≥ 0.8、対照で 0.35〜0.65）")
        落ち = 0
        for 名 in 道具:
            a, b = 判定[False][名].get("ROC-AUC"), 判定[True][名].get("ROC-AUC")
            ok = a is not None and b is not None and a >= 0.8 and 0.35 <= b <= 0.65
            落ち += not ok
            print("  %s %-18s 仕込み %s / 対照 %s" % ("○" if ok else "×", 名, a, b))
        return 1 if 落ち else 0

    ログ = sorted(__import__("glob").glob(os.path.join(E4.根, "生", "ollama-*.log")))
    要求, 積み込み, 文脈, キャッシュ = E4.ログを読む(ログ)
    機械 = E4.機械を読む()
    速さ = 速さを読む(ログ)
    t0, X, 状態, 名前 = 系列を作る(要求, 積み込み, 文脈, キャッシュ, 機械, 速さ)

    if "--読めるか" in sys.argv:
        print(json.dumps({"分の数": len(X), "数値の数": len(名前), "数値": 名前,
                          "状態の種類": int(len(set(状態.tolist()))),
                          "前処理の速さが入った分": int((np.diff(X[:, 名前.index("前処理の速さ")]) != 0).sum()),
                          "torch": torch.__version__ if torch else None,
                          "注意": "始まりの件数は出さない（判定まで見ない）"}, ensure_ascii=False, indent=1))
        return 0

    if "--判定" in sys.argv:
        if time.time() < E4.試す側の終わり:
            print("まだ走らせない：試す側（2026-10-27〜11-03）が溜まりきるのは 2026-11-03 0:00。")
            return 2
        候補 = E4.始まりの候補([x for x in 要求 if x["始"] < E4.試す側の終わり])
        標本 = 標本を作る(候補, t0, len(X), 積み込み, 文脈, キャッシュ, 機械)
        境 = int(E4.作る側の終わり // 60) - 1 - t0
        作る = [s for s in 標本 if s[0] < 境 and s[3] < E4.作る側の終わり]
        試す = [s for s in 標本 if s[3] >= E4.作る側の終わり]
        # 標準化は作る側の分だけで
        μ = X[:境 + 1].mean(axis=0)
        σ = X[:境 + 1].std(axis=0) + 1e-9
        材 = {"X": (X - μ) / σ, "状態": 状態}
        n始作, n始試 = sum(b for _, b, *_ in 作る), sum(b for _, b, *_ in 試す)
        print("作る側の始まり %d・試す側の始まり %d" % (n始作, n始試))
        if n始試 < 20:
            print("試す側の始まりが20件未満：何も読まない（決まりどおり）")
        結果 = 総当たり(材, 作る, 試す, os.path.join(os.path.dirname(os.path.abspath(__file__)), "実験6-結果.json"))
        結果["注記"] = {"作る側の始まり": n始作, "試す側の始まり": n始試,
                      "深いものは材料が足りない中での点数": n始作 < 50}
        json.dump(結果, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "実験6-結果.json"), "w"),
                  ensure_ascii=False, indent=1, default=str)
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
