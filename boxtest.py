#!/usr/bin/python3

import shutil
import sys

def boxText(msg,symbol='*'):
	import os
	sz = os.get_terminal_size()
	print(repr(sz))
	boxsize = len(msg) + 4
	screenMidpoint = int(sz[0]/2)
	textHalf = int(boxsize/2)
	print(screenMidpoint)
	print(textHalf)
	printStart = screenMidpoint - textHalf
	print(' ' * printStart + symbol * boxsize)
	print(' ' * printStart + symbol + ' ' + msg + ' ' + symbol)
	print(' ' * printStart + symbol * boxsize)
	return

boxText('testing')

