#!/bin/bash
# This script tests that accelerad_rcontrib runs.
accelerad_rcontrib -version
if [ $? -eq 0 ]; then
	out="test_rcontrib.txt"
	rm -f $out
	accelerad_rcontrib -h -lr 8 -lw .002 -x 5 -y 5 -m sky_mat test.oct < test.inp > $out
	if [[ $? -eq 0 && -s $out ]]; then
		echo "Accelerad rcontrib succeeded!"
	else
		echo "Accelerad rcontrib failed"
	fi
else
	echo "Accelerad rcontrib failed"
fi
