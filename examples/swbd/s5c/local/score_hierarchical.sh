#!/bin/bash

. ./path.sh
set -e

### Select GPU
if [ $# -ne 2 ]; then
  echo "Error: set GPU number & config path." 1>&2
  echo "Usage: ./score_hierarchical.sh path_to_saved_model gpu_index" 1>&2
  exit 1
fi

### Set path to save dataset
DATA="/n/sd8/inaguma/corpus/swbd/kaldi"

saved_model_path=$1
gpu_index=$2

CUDA_VISIBLE_DEVICES=$gpu_index \
$PYTHON exp/evaluation/eval_hierarchical.py \
  --data_save_path $DATA \
  --model_path $saved_model_path \
  --epoch -1 \
  --eval_batch_size 4 \
  --beam_width 4 \
  --beam_width_sub 1 \
  --length_penalty 0 \
  --coverage_penalty 0
