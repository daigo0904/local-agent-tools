#!/usr/bin/env python3
"""
modellib — ローカルのモデルを呼ぶときの作法。道具を足すたびに書き直さないための共有部品。

    from modellib import ctx_options
    options = ctx_options("gemma4:26b", {"temperature": 0.4})

## なぜ要るか

**このMacの Ollama は1つで、それを使う道具が5つある。** それなのに、
「どのモデルを、どれだけの広さ（num_ctx）で載せるか」を各道具が勝手に決めていた。

Ollama は、同じモデルでも広さが違えば**別物として積み直す**。積み直すとき、
先に載っているほうは降ろされる。**降ろされた側が処理中だった依頼は途中で消え、
頼んだ側には HTTP 500 "unexpected EOF" だけが返る。**

2026-08-31 の朝がこれだった。qwc（65536）が、見張りの点検（広さ未指定＝32768）と
音声アシスタント（8192）に交互に降ろされ続け、**25分で25回積み直されて1手も終われなかった**。
悪いのは3つとも「自分の都合で広さを決めた」ことで、どれも単体では正しく動いていた。

## 作法

1. **広さを自分で決めない。** `ctx_options(モデル名, もとの options)` を通す
2. 決まり方は、①いま載っている広さ ②qwc と同じモデルなら qwc の設定
   ③それ以外は**指定しない**（そのモデルの都合に任せる）
3. 新しい道具を足すときも、ここを通す。**ここを直せば全部が直る**

## ここに無いもの

`keep_alive` はまだ各自で決めてよい（積み直しの原因にならないため）。
ただし常駐（-1）を上書きすると常駐が切れるので、長く載せておきたいモデルには
短い値を渡さないこと。見張りが60秒ごとに常駐に戻すので実害は出にくいが、
それに頼らないほうがよい。
"""

import json
import os
import sys
import urllib.request

OLLAMA_URL = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
if not OLLAMA_URL.startswith("http"):
    OLLAMA_URL = "http://" + OLLAMA_URL

QWC_CONFIG = os.path.expanduser("~/.qwythos-code/config.json")

# 何も手がかりが無いときの控え。**ここを気軽に変えないこと。**
# qwc の設定と食い違うと、また積み直しが始まる。
FALLBACK_NUM_CTX = 65536


def _family(name):
    """`gemma4:26b` と `gemma4:26b-mlx` を同じものとして扱わない。
    タグだけ落として比べる（`:latest` の有無を吸収するため）。"""
    return (name or "").split(":")[0]


def resident_ctx(model=None):
    """いま載っているモデルの広さ。載っていなければ None。

    `model` を渡すと、その系統が載っているときだけ答える。
    別のモデルの広さに合わせても意味がない（どうせ積み直しになる）ため。"""
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/ps", timeout=5) as r:
            for m in json.loads(r.read()).get("models", []):
                name = m.get("name") or m.get("model") or ""
                if model and _family(name) != _family(model):
                    continue
                if m.get("context_length"):
                    return int(m["context_length"])
    except Exception:
        pass
    return None


def resident_model():
    """いま GPU に載っているモデルの名前。載っていなければ qwc の既定。

    **重い仕事は、載っているものに任せるのがいちばん速い。**
    別のモデルを呼ぶと、17GB を降ろして積み直すところから始まる。
    実測 2026-08-31: 朝の便りの調べもの1件が
    qwen3:14b（載っていない・密14B）で **420秒たっても終わらず**、
    gemma4:26b（載っている・MoE）なら **44秒**だった。10倍近い差が出る。"""
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/ps", timeout=5) as r:
            for m in json.loads(r.read()).get("models", []):
                name = m.get("name") or m.get("model") or ""
                if name:
                    return name
    except Exception:
        pass
    return qwc_model()


def _qwc_config(key, default=None):
    try:
        with open(QWC_CONFIG) as f:
            return json.load(f).get(key, default)
    except (OSError, ValueError, AttributeError):
        return default


def qwc_ctx():
    """qwc が使う広さ。設定を変えたら、ほかの道具が勝手に追いかける。

    qwc を基準にするのは、**いちばん長い仕事をするのが qwc だから**。
    短い用の道具が長い仕事を降ろす形にしない。"""
    try:
        return int(_qwc_config("numCtx"))
    except (TypeError, ValueError):
        return None


def qwc_model():
    """qwc が使うモデル。設定に書いていなければ、qwc の出荷時の既定。"""
    return _qwc_config("model") or "gemma4:26b"


def num_ctx_for(model=None):
    """このモデルを呼ぶときに渡す広さ。決められないときは None。

    ①載っているならその広さ（積み直させないため）
    ②載っていなくても、qwc と同じモデルなら qwc の設定に合わせる
      （次に来るのはたいてい qwc なので、そこで積み直しが起きない状態にしておく）
    ③それ以外は **None＝指定しない**。**qwc の広さを別のモデルに使い回さないこと。**
      qwen3:14b は密モデルで、広く取ると枠を食う。載せ方はそのモデルの都合で決まる。
    """
    on_gpu = resident_ctx(model)
    if on_gpu:
        return on_gpu
    if model is None or _family(model) == _family(qwc_model()):
        return qwc_ctx() or FALLBACK_NUM_CTX
    return None


def ctx_options(model=None, base=None):
    """`options` に混ぜて使う形。**決められないときは num_ctx を入れない。**

    `{"num_ctx": None}` を送ると Ollama 側で解釈が揺れるので、
    入れないという選択をここで引き受ける。呼ぶ側に if を書かせないため。"""
    opts = dict(base or {})
    n = num_ctx_for(model)
    if n:
        opts["num_ctx"] = n
    return opts


def selftest():
    """壊れていないかを、外に出ずに確かめる。

    ollama が立っていなくても通ること。道具の入り口に置く部品なので、
    ここが落ちると呼び出し側が丸ごと動かなくなる。"""
    global OLLAMA_URL, QWC_CONFIG
    import tempfile
    keep = (OLLAMA_URL, QWC_CONFIG)
    tmp = tempfile.mkdtemp(prefix="modellib-test-")
    ok = []
    try:
        ok.append(("タグを落として比べる",
                   _family("gemma4:26b") == _family("gemma4:26b-mlx") == "gemma4"))
        ok.append(("別の系統は別物", _family("qwen3:14b") != _family("gemma4:26b")))

        # 相手がいなくても落ちない
        OLLAMA_URL = "http://127.0.0.1:1"   # 誰もいない番地
        ok.append(("Ollama が居なくても落ちない", resident_ctx("gemma4:26b") is None))

        cfg = os.path.join(tmp, "config.json")
        with open(cfg, "w") as f:
            json.dump({"numCtx": 12345}, f)
        QWC_CONFIG = cfg
        ok.append(("qwc の設定を読む", qwc_ctx() == 12345))
        ok.append(("載っていなければ qwc に合わせる", num_ctx_for("gemma4:26b") == 12345))

        ok.append(("qwc と違うモデルには使い回さない", num_ctx_for("qwen3:14b-q4_K_M") is None))
        ok.append(("決められなければ num_ctx を入れない",
                   "num_ctx" not in ctx_options("qwen3:14b-q4_K_M", {"temperature": 0.4})))
        ok.append(("決まれば混ぜて返す",
                   ctx_options("gemma4:26b", {"temperature": 0.4})
                   == {"temperature": 0.4, "num_ctx": 12345}))

        QWC_CONFIG = os.path.join(tmp, "ない.json")
        ok.append(("設定が無ければ None", qwc_ctx() is None))
        ok.append(("最後は控えの値", num_ctx_for("gemma4:26b") == FALLBACK_NUM_CTX))

        with open(cfg, "w") as f:
            f.write("{壊れている")
        QWC_CONFIG = cfg
        ok.append(("設定が壊れていても落ちない", qwc_ctx() is None))
        ok.append(("設定が壊れていてもモデル名は答える", qwc_model() == "gemma4:26b"))
        OLLAMA_URL = "http://127.0.0.1:1"   # 誰もいない番地
        ok.append(("載っていなければ qwc の既定を返す", resident_model() == "gemma4:26b"))
    finally:
        OLLAMA_URL, QWC_CONFIG = keep
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    bad = [n for n, r in ok if not r]
    for n, r in ok:
        print(f"  {'ok  ' if r else 'NG  '}{n}")
    print(f"\n  {len(ok) - len(bad)} / {len(ok)} 件")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else 0)
