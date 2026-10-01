from price import parse_price

valid_cases = {
    '1234': 1234,
    ' 12 ': 12,
    '\t12\n': 12,
    '¥1,234': 1234,
    '1,234円': 1234,
    '12,345,678': 12345678,
    '１２３': 123,
    '-¥5': -5,
    '-5円': -5,
    ' -¥１２,３４５円 ': -12345,
    '0': 0,
    '-0': 0,
    '123,456': 123456,
    '12345678': 12345678,
}
for value, expected in valid_cases.items():
    assert parse_price(value) == expected, value

invalid_cases = [
    '', ' ', '¥', 'abc', '-', '円', '-¥円',
    '1,23', '1234,567', ',123', '123,', '1,,234', '1,234,56',
    '¥-5', '1 234', '1.5', 'abc123', '123abc', '¥¥5', '5円円',
]
for value in invalid_cases:
    try:
        parse_price(value)
    except ValueError:
        pass
    else:
        raise AssertionError(f'Expected ValueError for {value!r}')

print(f'ok: {len(valid_cases)} valid cases, {len(invalid_cases)} invalid cases')
