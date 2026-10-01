import re

_FULLWIDTH_DIGITS = str.maketrans("０１２３４５６７８９", "0123456789")
# カンマ無しの数字列か、1〜3桁の後に「,3桁」が続く形だけを受け付ける
_NUMBER = re.compile(r"[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+")


def parse_price(s):
    """値段の文字列を整数（円）にする。

    - 前後の空白は無視する（" 12 " → 12）
    - 先頭の「¥」、末尾の「円」はあってもよい（"¥1,234" → 1234、"1,234円" → 1234）
    - 3桁ごとのカンマはあってもよい。ただし位置が正しくないカンマは ValueError
      （"12,345,678" → 12345678、"1,23" → ValueError）
    - 全角数字も読む（"１２３" → 123）
    - 先頭に「-」があれば負（"-¥5" → -5、"-5円" → -5）
    - 数字が1つも無いもの（""、"¥"、"abc"）は ValueError
    """
    t = s.strip().translate(_FULLWIDTH_DIGITS)
    negative = t.startswith("-")
    if negative:
        t = t[1:]
    if t.startswith("¥"):
        t = t[1:]
    if t.endswith("円"):
        t = t[:-1]
    if not _NUMBER.fullmatch(t):
        raise ValueError(f"値段として読めない: {s!r}")
    n = int(t.replace(",", ""))
    return -n if negative else n
