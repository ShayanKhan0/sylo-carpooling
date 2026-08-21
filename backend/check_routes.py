import requests
r = requests.get('http://localhost:8000/openapi.json')
data = r.json()
paths = [p for p in data['paths'].keys() if 'wallet' in p or 'driver' in p or 'payment' in p or 'payout' in p]
for p in sorted(paths):
    methods = list(data['paths'][p].keys())
    print(f"  {methods} {p}")
