from price import parse_price

assert parse_price('1234') == 1234
assert parse_price('¥1,234') == 1234
for value, expected in [
    (' 12 ', 12),
    ('1,234円', 1234),
    ('12,345,678', 12345678),
    ('１２３', 123),
    ('-¥5', -5),
    ('-5円', -5),
    (' \t-¥１２,３４５円\n', -12345),
    ('0', 0),
    ('123,456', 123456),
]:
    assert parse_price(value) == expected, value

for value in [
    '', ' ', '¥', 'abc', '円', '-', '-¥円',
    '1,23', '1234,567', ',123', '123,', '1,,234', '1,234,56',
    '¥-5', '1 234', '1.5', '123abc', '¥¥5', '5円円',
]:
    try:
        parse_price(value)
    except ValueError:
        pass
    else:
        raise AssertionError(f'Expected ValueError: {value!r}')
print('ok')
