from pathlib import Path

root = Path(__file__).resolve().parent / 'project'

p025 = root / 'scripts' / 'dilemma_4x6_4_top.py'
text = p025.read_text(encoding='utf-8')
old = "    ((237.40062, -83.10167), (244.51852, -80.01642), (246.668798, -80.01642)),\n"
new = "    ((237.40062, -83.10167), (244.51852, -80.01642), (246.668798, -80.01642), (244.56601, -80.06390), (244.56601, -80.06788)),\n"
if old not in text:
    raise SystemExit('P025 exact rib-10 anchor not found')
p025.write_text(text.replace(old, new, 1), encoding='utf-8')
print('Applied P025 exact rib-10 return/contact points')
