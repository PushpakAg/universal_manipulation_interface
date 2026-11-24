"""
tt2: shared infrastructure of the tag tracking v2 scripts.

errors      exception types with an actionable message
log         logging setup (console + per-session file), one logger per module
runner      run a child process with timeout, streamed log file, structured result
fsutil      atomic file writes, atomic directory swap, file fingerprints
s3          boto3 helpers: retrying client, listing, ranged reads, verified transfer
bootstrap   import paths (v2 first, then the original repository) and path helpers
parallel    process pool helpers for tracking and fusion (worker thread limits, cost balanced chunks)
video_chunk chunked per frame processing of a video (shared pool, more chunks than workers)
tag_detection  ArUco corner detection (reused detector, optional coarse-to-fine search)
"""
