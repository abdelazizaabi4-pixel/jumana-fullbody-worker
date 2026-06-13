import json
from handler import handle
print(json.dumps(handle({"input":{"task":"diagnostic"}}), ensure_ascii=False, indent=2))
