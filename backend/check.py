import re

with open('app/modules/rides/service.py', 'r') as f:
    text = f.read()

pattern = '''def create_ride_service\(.*?ride_data: RideCreate.*?\) -> Dict\[str, Any\]:'''
match = re.search(pattern, text, re.DOTALL)
if match:
    print('Found create_ride_service')
else:
    print('create_ride_service not found')
