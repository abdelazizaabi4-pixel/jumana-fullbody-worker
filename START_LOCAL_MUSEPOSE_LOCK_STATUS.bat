@echo off
chcp 65001
set PYTHONUTF8=1
python -c "from handler import handle; import json; print(json.dumps(handle({'input':{'task':'musepose_lock_status'}}), ensure_ascii=False, indent=2))"
pause
