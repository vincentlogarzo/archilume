#!/bin/bash
# This script tests that accelerad_rtrace runs.
accelerad_rtrace -version
if [ $? -eq 0 ]; then
	out="test_rtrace.txt"
	rm -f $out
	accelerad_rtrace -h -aa 0 -ad 1024 -as 0 -lr 8 -lw .002 -x 5 -y 5 -ovodwl test.oct < test.inp > $out
	if [[ $? -eq 0 && -s $out ]]; then
		echo "Accelerad rtrace succeeded!"
	else
		echo "Accelerad rtrace failed"
	fi
else
	echo "Accelerad rtrace failed"
fi
