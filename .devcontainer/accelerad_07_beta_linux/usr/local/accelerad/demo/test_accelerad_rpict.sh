#!/bin/bash
# This script tests that accelerad_rpict runs.
accelerad_rpict -version
if [ $? -eq 0 ]; then
	out="test_rpict.hdr"
	rm -f $out
	accelerad_rpict -vp 10.0 -2.0 1.5 -vd -1.0 0.0 0.0 -vu 0 0 1 -ab 2 -aa .18 -ad 1024 -as 0 -lr 8 -lw .002 -x 512 -y 512 -pj 0 -ac 1024 test.oct > $out
	if [[ $? -eq 0 && -s $out ]]; then
		echo "Accelerad rpict succeeded!"
	else
		echo "Accelerad rpict failed"
	fi
else
	echo "Accelerad rpict failed"
fi
