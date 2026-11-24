cd /Users/kgen/Projects/universal_manipulation_interface
export DOCKER_DEFAULT_PLATFORM=linux/amd64
C=example/tag_tracking/tag_tracking_station1.yaml
date +%s > data/subset_check/orig_r2.start
env PATH=$PWD/.venv/bin:$PATH python scripts_tag_tracking/process_station.py data/subset_check/orig_r2 -c $C --tasks sub01 --mcap > data/subset_check/orig_r2.out 2>&1
date +%s > data/subset_check/orig_r2.end
date +%s > data/subset_check/v2_r2.start
.venv/bin/python tag_tracking_v2/scripts_tag_tracking/process_station.py data/subset_check/v2_r2 -c $C --tasks sub01 --mcap > data/subset_check/v2_r2.out 2>&1
date +%s > data/subset_check/v2_r2.end
