cd /Users/kgen/Projects/universal_manipulation_interface
export DOCKER_DEFAULT_PLATFORM=linux/amd64
date +%s > data/full_check/v2.start
.venv/bin/python tag_tracking_v2/scripts_tag_tracking/process_station.py data/full_check/v2 -c example/tag_tracking/tag_tracking_station1.yaml --tasks task01 --mcap > data/full_check/v2.out 2>&1
date +%s > data/full_check/v2.end
