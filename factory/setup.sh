#!/bin/bash
# Rebuild the owner's Mac layout (~/ClipMachine) on a GitHub server, so the clip pipeline
# runs here UNCHANGED - every script finds its tools and files where it expects.
# 19 Sept 2026: the cloud clip factory, so clips get made with the Mac shut.
set -euo pipefail
K="$HOME/ClipMachine"
mkdir -p "$K/bin" "$K/Content/1_RAW/KT_SOURCE" "$K/POST_TODAY" "$K/work/proposals" \
         "$K/transcripts" "$K/logs" "$K/whisper.cpp/build/bin" "$K/whisper.cpp/models"

sudo apt-get -qq update >/dev/null
sudo apt-get -qq install -y ffmpeg fonts-liberation cmake >/dev/null
pip install -q opencv-python-headless numpy pillow

ln -sf /usr/bin/ffmpeg  "$K/bin/ffmpeg"
ln -sf /usr/bin/ffprobe "$K/bin/ffprobe"
ln -sf "$(command -v gh)" "$K/bin/gh"
cp factory/assets/mont_black.ttf factory/assets/yunet.onnx "$K/bin/"
# Liberation Sans is metrically identical to Arial and free to ship; Apple's
# Arial file is not ours to publish in a public repository.
ln -sf /usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf "$K/bin/arial_bold.ttf"
cp factory/pipeline/*.py "$K/"
# 10 Oct 2026: the club look (factory/restyle.py) puts the hook in its own frame
# BELOW the video, so the render no longer burns the small hook card on top of
# Kevin's face. The card is still built (other steps read its size); it is just
# never shown.
python3 - "$K/kt_render.py" <<'PY'
import sys
p = sys.argv[1]; s = open(p).read()
old = "enable='lt(t,{HOOK_SECS})'[vv];"
assert old in s, "kt_render changed - hook card switch not applied"
open(p, "w").write(s.replace(old, "enable='lt(t,0)'[vv];"))
PY
cp factory/kt_series.json "$K/kt_series.json"
ln -sfn "$GITHUB_WORKSPACE" "$K/kt-machine"

# whisper.cpp pinned to the exact commit the Mac runs, so word timings match.
W="$HOME/wcache"
if [ ! -x "$W/whisper-cli" ]; then
  mkdir -p "$W"
  git clone -q https://github.com/ggml-org/whisper.cpp /tmp/whisper.cpp
  git -C /tmp/whisper.cpp checkout -q 2ca53bb45e38748d07b310eeb36245a7157ac882
  cmake -S /tmp/whisper.cpp -B /tmp/whisper.cpp/build -DCMAKE_BUILD_TYPE=Release \
        -DBUILD_SHARED_LIBS=OFF -DWHISPER_BUILD_TESTS=OFF >/dev/null
  cmake --build /tmp/whisper.cpp/build -j"$(nproc)" --config Release --target whisper-cli >/dev/null
  cp /tmp/whisper.cpp/build/bin/whisper-cli "$W/"
fi
[ -s "$W/ggml-small.en.bin" ] || curl -sL -o "$W/ggml-small.en.bin" \
  https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.en.bin
ln -sf "$W/whisper-cli" "$K/whisper.cpp/build/bin/whisper-cli"
ln -sf "$W/ggml-small.en.bin" "$K/whisper.cpp/models/ggml-small.en.bin"
"$K/whisper.cpp/build/bin/whisper-cli" --help >/dev/null 2>&1 && echo "setup ok: whisper, ffmpeg, fonts, pipeline"
