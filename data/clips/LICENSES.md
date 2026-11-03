# Clip provenance and licenses

## synthetic.mp4 / synthetic_tracks.json / synthetic_truth.json
**Source:** generated entirely within this repository by `tools/render_synthetic_clip.py`
(crowd-ghost physics sim, `backend/app/physics/social_force.py`, rendered top-down with OpenCV).
**License:** public domain within this project — no third-party footage, no people depicted.
**Purpose:** ground-truth-validated target for `backend/app/vision/`.

## Real footage
Not shipped. No redistributable crowd clip with a countable entry zone could be fetched or
license-verified in this environment (no web search access; Commons API yields no suitable
steady modern crowd clip). The YOLO path (`detect_track.py --detector yolo`) works on real
footage but was NOT validated end-to-end here; on the synthetic clip YOLOv8n detects **zero**
person instances in 120 sampled frames (rendered blobs are not person-like), as expected.
