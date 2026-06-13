#!/usr/bin/env bash
set -e
cd /workspace
if [ ! -d MagicAnimate ]; then
  echo "[JUMANA V28] Clone MagicAnimate here, or mount it via RunPod Volume."
  echo "This script is intentionally conservative because different forks require different weights and commands."
fi
mkdir -p /workspace/models/magicanimate
cat <<'EOF'
[JUMANA V28]
MagicAnimate is a real body/temporal motion engine option.
You must provide:
- MAGICANIMATE_ROOT
- MAGICANIMATE_WEIGHTS
- MAGICANIMATE_COMMAND_TEMPLATE
This worker will not fake success.
EOF
