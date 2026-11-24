cd /Users/kgen/Projects/universal_manipulation_interface
export DOCKER_DEFAULT_PLATFORM=linux/amd64
export PATH="$PWD/.venv/bin:$PATH"
date +%s > data/subset_check/orig_r2.start
python scripts_tag_tracking/process_station.py data/subset_check/orig_r2 -c example/tag_tracking/tag_tracking_station1.yaml --tasks sub01 --mcap > data/subset_check/orig_r2.out 2>&1
date +%s > data/subset_check/orig_r2.end
