from price import parse_price

assert parse_price('1234') == 1234
assert parse_price('¥1,234') == 1234

for value, expected in [
    (' 12 ', 12),
    ('\t¥1,234円\n', 1234),
    ('1,234円', 1234),
    ('12,345,678', 12345678),
    ('123,456', 123456),
    ('１２３', 123),
    ('-¥5', -5),
    ('-5円', -5),
    (' -¥１２,３４５円 ', -12345),
    ('1２3', 123),
    ('0', 0),
    ('-0', 0),
]:
    assert parse_price(value) == expected, value

for value in [
    '', ' ', '¥', 'abc', '-', '円', '-¥円',
    '1,23', '1234,567', '1,234,56', ',123', '123,', '1,,234',
    '¥-5', '--5', '¥¥5', '5円円', '1 234', '¥ 5', '5 円',
    '12abc', '1.5', '1_000',
]:
    try:
        parse_price(value)
    except ValueError:
        pass
    else:
        raise AssertionError(f'Expected ValueError: {value!r}')

print('ok')
