#!/bin/bash

echo "Running examples for data processing..."

##################################################
# process observed asdf file
# Currently, there are two ways to launch the job
# 1) multi-processing
# 2) mpi
# Both examples are provided

echo "++++++"
echo "process observed file..."
# multi-processing
#python process_observed.py \
#  -p ./parfile/proc_obsd.params.json \
#  -f ./parfile/proc_obsd.dirs.json \
#  -v

# mpi
mpiexec -n 2 python process_observed.py \
  -p ./parfile/proc_obsd.50_100.yml \
  -f ./parfile/proc_obsd.path.json \
  -v

##################################################
# process synthetic asdf file
# Currently, there are two ways to launch the job
# 1) multi-processing
# 2) mpi
# Both examples are provided

echo "++++++"
echo "process synthetic file..."
# multi-processing
#python process_synthetic.py \
#  -p ./parfile/proc_synt.params.json \
#  -f ./parfile/proc_synt.dirs.json \
#  -v

#python process_synthetic.py \
#  -p ./parfile/proc_synt.params.json.2 \
#  -f ./parfile/proc_synt.dirs.json.2 \
#  -v

# mpi
mpiexec -n 2 python process_synthetic.py \
  -p ./parfile/proc_synt.50_100.yml \
  -f ./parfile/proc_synt.path.json \
  -v

#mpiexec -n 2 python ../process_synthetic.py \
#  -p ./parfile/proc_synt.params.json.2 \
#  -f ./parfile/proc_synt.dirs.json.2 \
#  -v
