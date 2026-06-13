#!/usr/bin/env bash
set -e
mkdir -p /workspace/AnimateAnyone
mkdir -p /workspace/models/animateanyone
cat <<'TXT'
[JUMANA V29]
ضع كود AnimateAnyone أو البديل المستقر داخل:
/workspace/AnimateAnyone

ضع الأوزان داخل:
/workspace/models/animateanyone

ثم اضبط إن لزم:
ANIMATEANYONE_COMMAND_TEMPLATE
مثال:
python -u {root}/scripts/inference.py --source_image {source_image} --motion {motion_json} --output_dir {output_dir} --weights {weights}
TXT
