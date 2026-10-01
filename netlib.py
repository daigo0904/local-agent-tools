#!/usr/bin/env python3
"""
netlib — 外に出る前に、外に出られるか確かめる共有部品。

    from netlib import wait_online
    if wait_online() is None:
        print("ネットにつながらない", file=sys.stderr); return 1

## なぜ要るか

**このMacの定時仕事は、朝いちばんに走る。ネットより先に走ることがある。**

2026-08-31 に朝の便りの記録を17回ぶん調べたら、届かなかった日の内訳はこうだった。

    08-26 / 08-27 / 08-28 / 08-31   getaddrinfo ENOTFOUND api.line.me
    08-18 / 08-19 / 08-25           cron: job execution timed out

前者は**8時ちょうどに名前解決ができていない**。検索（Tavily）も天気も同時に失敗するので
中身は空になり、送ろうとした LINE も届かない。しかも失敗した理由は捨てられ、
利用者からは「今日も来なかった」としか見えない。
8/29 は staggerMs で **08:03 にずれて走り、そのぶん普通に成功している**。
つまり数分待てば済む話だった。

## 使い方の作法

- **外に出る仕事は、最初に `wait_online()` を通す。**
- つながらないまま終わるときは、**黙って0で終わらない**。失敗として記録を残すこと。
  黙って終わると「調べたが何も無かった」と区別が付かず、壊れていることに誰も気づけない。

## line-guard の internet_ok() との違い

あちらは**数字のIPに直接つないで**「DNSだけ死んでいる」を切り分けるためのもの。
こちらは逆に、**実際に使う相手の名前が引けてつながるか**を見る。
用途が違うので分けてある（片方を消して片方に寄せないこと）。
"""

import socket
import sys
import time

# 見に行く先。**実際に使う相手を見ること。**
# 8.8.8.8 が引けても api.line.me が引けない状態が現にあった。
DEFAULT_HOSTS = ("api.line.me", "api.tavily.com")
DEFAULT_LIMIT = 600      # 何秒まで待つか（10分）
DEFAULT_STEP = 15        # 何秒おきに試すか


def reachable(host, port=443, timeout=4):
    """名前が引けて、つながるか。

    名前解決だけでは足りない。DNS が答えても経路が無い状態があるため、
    TCP でつなぐところまで見る。"""
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except OSError:
        return False
    for family, socktype, proto, _canon, addr in infos:
        s = socket.socket(family, socktype, proto)
        s.settimeout(timeout)
        try:
            s.connect(addr)
            return True
        except OSError:
            continue
        finally:
            s.close()
    return False


def online(hosts=DEFAULT_HOSTS, timeout=4):
    """必要な相手すべてにつながるか。1つでも駄目なら False。"""
    return all(reachable(h, timeout=timeout) for h in hosts)


def wait_online(hosts=DEFAULT_HOSTS, limit=DEFAULT_LIMIT, step=DEFAULT_STEP, log=None):
    """つながるまで待つ。待った秒数を返す。ついに駄目なら None。

    `log` に関数を渡すと、待っていることを1回だけ知らせる
    （毎回書くと、正常な朝でも記録が埋まる）。"""
    t0 = time.time()
    if online(hosts):
        return 0.0
    told = False
    while time.time() - t0 < limit:
        if not told and log:
            log(f"ネットにつながるのを待っています（{', '.join(hosts)}）")
            told = True
        time.sleep(step)
        if online(hosts):
            return round(time.time() - t0, 1)
    return None


def selftest():
    ok = []
    # 届かない先は False（.invalid は RFC 上、必ず名前解決に失敗する）
    ok.append(("届かない先は False", reachable("nowhere.invalid", timeout=2) is False))
    ok.append(("1つでも駄目なら False",
               online(("nowhere.invalid",), timeout=2) is False))
    # 待って駄目なら None（すぐ諦める設定で）
    t0 = time.time()
    ok.append(("諦めたら None",
               wait_online(("nowhere.invalid",), limit=2, step=1) is None))
    ok.append(("諦めるまで待ちすぎない", time.time() - t0 < 10))
    # つながっていれば 0.0（待たない）
    if online():
        ok.append(("つながっていれば待たない", wait_online() == 0.0))
    else:
        ok.append(("いまは外に出られないので、この項目は見送り", True))

    bad = [n for n, r in ok if not r]
    for n, r in ok:
        print(f"  {'ok  ' if r else 'NG  '}{n}")
    print(f"\n  {len(ok) - len(bad)} / {len(ok)} 件")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else (0 if online() else 1))
