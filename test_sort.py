from collections import Counter

relative_values = [
    10.073, 10.073,
    6.736, 6.736,
    6.212, 6.212,
    3.150, 3.150, 3.150, 3.150,
    3.200, 3.200,
    0.000, 0.000,
    -0.020, -0.020, -0.020, -0.020,
    -0.080,
    -0.400,
]

freq = Counter([round(v, 2) for v in relative_values])
ridge_level = max(relative_values)
rounded_vals = [round(v, 3) for v in relative_values]
distinct_levels = sorted(list(set(rounded_vals)), reverse=True)

valid_levels = [level for level in distinct_levels if level < ridge_level - 0.3 and level > 0]
if valid_levels:
    valid_levels.sort(key=lambda lvl: (freq[round(lvl, 2)], lvl), reverse=True)
    eave_level = valid_levels[0]
    
print("valid_levels sorted:", [(lvl, freq[round(lvl, 2)]) for lvl in valid_levels])
print("eave_level:", eave_level)
