import re

with open('app/core/fare_calculator.py', 'r') as f:
    text = f.read()

text = re.sub(
    r'time_cost = dur_min \* _time_rate(?! \* traffic_factor)',
    r'time_cost = dur_min * _time_rate * traffic_factor',
    text
)

text = re.sub(
    r'total_fare = _base \+ fuel_cost \+ time_cost \+ platform_fee\s+',
    r'base_subtotal = _base + fuel_cost + time_cost + platform_fee\n    total_fare = base_subtotal * surge_multiplier\n\n    ',
    text
)

with open('app/core/fare_calculator.py', 'w') as f:
    f.write(text)
print('Patched fare variables')
