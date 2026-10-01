from price import parse_price

assert parse_price('1234') == 1234
assert parse_price('¥1,234') == 1234
print('ok')
