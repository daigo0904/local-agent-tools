from price import parse_price

valid_cases = [
    ('1234', 1234),
    (' 12 ', 12),
    ('¥1,234', 1234),
    ('1,234円', 1234),
    ('12,345,678', 12345678),
    ('１２３', 123),
    ('-¥5', -5),
    ('-5円', -5),
    ('\t -¥１２,３４５円\n', -12345),
    ('1２3', 123),
    ('0', 0),
    ('-0円', 0),
    ('123,456', 123456),
]
invalid_cases = [
    '', ' ', '¥', '円', 'abc', '-', '-¥円',
    '1,23', ',123', '123,', '1234,567', '1,,234', '1,234,56',
    '¥-5', '--5', '1-2', '1¥', '円1', '¥¥1', '1円円',
    '1 234', '¥ 5', '12.5', '1_000', '+5', 'abc123',
]

for value, expected in valid_cases:
    assert parse_price(value) == expected, value

for value in invalid_cases:
    try:
        parse_price(value)
    except ValueError:
        pass
    else:
        raise AssertionError(f'Expected ValueError for {value!r}')

print(f'ok: {len(valid_cases)} valid cases, {len(invalid_cases)} invalid cases')
