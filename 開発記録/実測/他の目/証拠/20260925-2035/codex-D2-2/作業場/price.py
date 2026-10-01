import re


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
    normalized = s.strip().translate(str.maketrans("０１２３４５６７８９", "0123456789"))
    match = re.fullmatch(r"(-?)¥?([0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)円?", normalized)
    if match is None:
        raise ValueError(f"Invalid price: {s!r}")
    sign, digits = match.groups()
    return int(sign + digits.replace(",", ""))
