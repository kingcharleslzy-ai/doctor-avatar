#!/usr/bin/env bash
set -euo pipefail

ENV_NAME="${1:-ditto}"
MINICONDA_ROOT="${MINICONDA_ROOT:-$HOME/miniconda3}"
INSTALL_GRADIO="${INSTALL_GRADIO:-1}"
INSTALL_XFORMERS="${INSTALL_XFORMERS:-0}"

if [[ ! -f "${MINICONDA_ROOT}/etc/profile.d/conda.sh" ]]; then
  echo "Missing conda bootstrap: ${MINICONDA_ROOT}/etc/profile.d/conda.sh" >&2
  exit 1
fi

source "${MINICONDA_ROOT}/etc/profile.d/conda.sh"
conda activate "${ENV_NAME}"

echo "==> Installing required runtime packages into conda env: ${ENV_NAME}"
python -m pip install --upgrade pip
python -m pip install \
  "fastapi>=0.135,<1" \
  "uvicorn[standard]>=0.41,<1" \
  "websockets>=16,<17" \
  "soundfile>=0.13,<1" \
  "ffmpeg-python>=0.2,<1"

echo "==> Installing optional helper packages"
if [[ "${INSTALL_GRADIO}" == "1" ]]; then
  python -m pip install "gradio>=5,<6"
fi

if [[ "${INSTALL_XFORMERS}" == "1" ]]; then
  echo "WARNING: xformers may replace the existing torch stack; only enable this if you have already planned a compatible torch/torchvision/torchaudio set." >&2
  python -m pip install "xformers>=0.0.29,<1"
else
  echo "Skipping xformers by default to avoid accidentally replacing the working torch stack." >&2
fi

echo "==> Import verification"
python - <<'PY'
import importlib.util
import json

mods = [
    "cv2",
    "numpy",
    "librosa",
    "fastapi",
    "uvicorn",
    "gradio",
    "xformers",
    "onnxruntime",
    "websockets",
    "soundfile",
    "ffmpeg",
]
print(json.dumps({m: bool(importlib.util.find_spec(m)) for m in mods}, ensure_ascii=False, indent=2))
PY
