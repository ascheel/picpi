import sys

#if sys.version_info[0] != 3:
#	print('Python3 required.')
#	sys.exit(1)

import os
#import pygame
import signal

from picpi2 import picpi

def signal_handler(signal, frame):
	print('ctrl-c detected.')
	sys.exit(1)

signal.signal(signal.SIGINT, signal_handler)


if len(sys.argv):
	for x in range(len(sys.argv)):
		if sys.argv[x] == 'refresh':
			p = picpi('refresh','/home/pi/.picpi.conf')
			#p.verify_db()
			#p.delete_old()
			p.get_new_files()
			del p
		if sys.argv[x] == 'slideshow':
			p = picpi('slideshow','/home/pi/.picpi.conf')
			p.silent = True
			p.slideshow()
			del p
		if sys.argv[x] == 'wipe':
			p = picpi('wipe','/home/pi/.picpi.conf')
			p.wipe()
			del p
		if sys.argv[x] == 'status':
			p = picpi('status','/home/pi/.picpi.conf')
			p.get_processes()
			del p
		if sys.argv[x] == 'check':
			p = picpi('check','/home/pi/.picpi.conf')
			p.check_integrity()
			del p
		if sys.argv[x] == 'test':
			p = picpi('test','/home/pi/.picpi.conf')
			p.test()
			del p
sys.exit(0)

