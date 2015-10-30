#!/usr/bin/python

"""
Requirements:
Packages:
python-pythonmagick
jhead
sqlite3
"""
from __future__ import division

import hashlib
import sqlite3
import sys
import time
import os
import subprocess
import shutil
import PythonMagick as PM
import random
import pygame
import math
import ConfigParser
from PIL import Image

def main():
	configFile = os.path.expanduser('~') + '/.picpie.conf'
	if len(sys.argv) > 1 and sys.argv[1] == 'config':
		if os.path.isfile(configFile):
			print "Config file already exists: " + configFile
			print "If you really want to reconfigure picpie, please delete the config."
		set_config()
		print "picpie configured with default settings."
		print "If customization is needed, please edit " + configFile
		sys.exit(0)
	if not os.path.isfile(configFile):
		print 'picpie does not appear to be configured.  Please run this first: ' + sys.argv[0] + ' config'
		sys.exit(0)

	set_config()

	global times
	global screenResolution
	global fileCount

	times = {'program start':time.time(),}

	# Do our directories exist?
	dirSet = ('picpieDir','storagePath','inboundFilePath','tmpPath',)
	for dir in dirSet:
		if not os.path.isdir(gets(dir)):
			os.mkdir(gets(dir))

	fileCount = countFiles()
	screenResolution = getResolution()

	if len(sys.argv) > 1 and sys.argv[1] == 'refresh':
		refreshFiles()
	else:
		runSlideShow()

	times['Complete'] = time.time()
	return config

def p():
	import pdb
	pdb.set_trace()
	return

def gets(setting):
	return c.get('Main',setting)

def set_config():
	global c
	c = ConfigParser.ConfigParser()
	configFile = os.path.expanduser('~') + '/.picpie.conf'
	c.read(configFile)
	if 'Main' not in c.sections():
		c.add_section('Main')
		c.set('Main','picpieDir','/home/pi/picpie')
		c.set('Main','storagePath',gets('picpieDir') + '/storage')
		c.set('Main','inboundFilePath',gets('picpieDir') + '/inbound')
		c.set('Main','tmpPath','/dev/shm')
		c.set('Main','picExts',','.join(('jpg','jpeg','tif','tiff','gif','png','bmp')))
		c.set('Main','vidExts',','.join(('wmv','mpg2','mpg4','mpg')))
		c.set('Main','pictureDuration',5)
		c.set('Main','debug',0)
		cfg = open(configFile,'w')
		c.write(cfg)
		cfg.close()
	return

def stamp():
	# Our timestamp.  Just making it easy.
	return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))

def getSQLite3():
	# Opens the DB, creates if it does not exist.
	dbName = gets('picpieDir') + '/hash_list.db'
	tableName = 'hashes'
	column_text = 'old_filename TEXT, old_sha1hash TEXT, filename TEXT UNIQUE, sha1hash TEXT UNIQUE, date_added REAL'
	db = sqlite3.connect(dbName)
	cur = db.cursor()
	cur.execute('CREATE TABLE IF NOT EXISTS {0} ({1})'.format(tableName, column_text))
	db.commit()
	return db

def getHashFromFile(filename):
	f = open(filename, 'rb')
	sha1 = hashlib.sha1()
	while True:
		data = f.read()
		if not data:
			break
		sha1.update(data)
	f.close()
	return sha1.hexdigest()

def getHashFromDB(db, filename):
	cur = db.cursor()
	cur.execute('SELECT old_sha1hash FROM hashes WHERE old_filename = ?',(filename,))
	hash = cur.fetchall()
	if not hash:
		hashString = ""
	else:
		hashString = hash[0][0]
	return hashString

def getHashFromDestination(db, filename):
	cur = db.cursor()
	cur.execute('SELECT old_sha1hash FROM hashes WHERE filename = ?',(filename,))
	hash = cur.fetchall()
	if not hash:
		hashString = ""
	else:
		hashString = hash[0][0]
	return hashString

def getFileFromHash(db, sha1Hash):
	cur = db.cursor()
	cur.execute('SELECT old_filename FROM hashes WHERE old_sha1hash = ?',(sha1Hash,))
	theFile = cur.fetchall()
	if not theFile:
		fileString = ""
	else:
		fileString = theFile[0][0]
	return fileString

def addHash(db, oldFName, newFName):
	#Does the file even exist?
	if not os.path.isfile(newFName):
		return 1

	#Check to see if it's in the DB already.
	if not getHashFromDB(db, oldFName) and not hashExistsInDB(db, getHashFromFile(oldFName)):
		cur = db.cursor()
		old_sha1hash = getHashFromFile(oldFName)
		sha1hash = getHashFromFile(newFName)
		cur.execute('INSERT INTO hashes VALUES (?, ?, ?, ?, ?)',(oldFName, old_sha1hash, newFName, sha1hash, stamp()))
		db.commit()
		return 0
	else:
		return 2
	return

def hashExistsInDB(db,hash):
	cur = db.cursor()
	cur.execute('SELECT COUNT(*) FROM hashes WHERE old_sha1hash = ?',(hash,))
	hashCount = cur.fetchall()[0][0]
	if not hashCount:
		return False
	else:
		return True
	return

def getResolution():
	#global screenResolution
	screenResolution = subprocess.check_output("fbset -s | grep '^mode' | sed 's/\"//g' | awk '{ print $2 }'", shell=True).rstrip().split('x')
	screenResolution = (int(screenResolution[0]),int(screenResolution[1]))
	#screenResolution = (1920,1080)	#assume 1080p
	print stamp() + " - Found resolution: " + repr(screenResolution)
	return screenResolution

def isAnimatedGif(fileName):
	gif = Image.open(fileName)
	try:
		gif.seek(1)
	except EOFError:
		animated = False
	else:
		animated = True
	return animated

def resizeImage(currentFile,newFName):
	if int(gets('debug')):
		print ""
		print stamp() + " - Resizing " + currentFile
	image = PM.Image(currentFile)
	image.resize(str(screenResolution[0]) + 'x' + str(screenResolution[1]))
	image.write(newFName)
	return

def rotateImage(newFName):
	if int(gets('debug')):
		print stamp() + " - Rotating " + newFName
	subprocess.call('jhead -autorot -q \"{}\" >/dev/null 2>&1'.format(newFName), shell=True)
	return

def fileExistsInDB(db, filename):
	cur = db.cursor()
	cur.execute('SELECT COUNT(*) FROM hashes WHERE old_filename = ?', (filename,))
	fileCount = cur.fetchall()[0][0]
	if not fileCount:
		return False
	else:
		return True
	return

def incrementFile(filename):
	fileRoot, fileExt = os.path.splitext(filename)
	suffixNum = 1
	newName = '{}_{}{}'.format(fileRoot, suffixNum, fileExt)
	while os.path.isfile(newName):
		suffixNum += 1
		newName = '{}_{}{}'.format(fileRoot, suffixNum, fileExt)
	return newName

def processFile(db, currentFile):
	global fileCount
	fileName, fileExt = os.path.splitext(currentFile)
	filePath, fileBase = os.path.split(fileName)
	tmpName = gets('tmpPath') + "/" + fileBase + fileExt
	newFName = gets('storagePath') + "/" + fileBase + fileExt

	if (not hashExistsInDB(db, currentFile) and
		not fileExistsInDB(db,currentFile) and
		getHashFromFile(currentFile) != getHashFromDestination(db, newFName)
		):
		print stamp() + " - Processing " + currentFile,
		if os.path.isfile(newFName):
			newFName = incrementFile(newFName)
		ext = fileExt[1:].lower()
	
		processIt = True
		if ext not in gets('picExts').lower().split(','):
			processIt = False
		if ext == 'gif':
			if isAnimatedGif(currentFile):
				#We're only resizing and rotating if it's not animated.
				#If it's animated, someone should have already oriented and resized it properly
				displayPic = False

		if processIt:
			resizeImage(currentFile, tmpName)
			rotateImage(tmpName)
		else:
			print " - Skipped."
			return
		shutil.move(tmpName,newFName)
		fileCount += 1
		print stamp() + ' - File count: ' + str(fileCount)
	else:
		print stamp() + " - Skipping: " + currentFile
		if int(gets('debug')):
			print stamp() + " - File exists in database: " + newFName

	# Add hash to db
	status = addHash(db, currentFile, newFName)
	if int(gets('debug')):
		if status == 0:
			print stamp() + " - Success: {0}".format(currentFile)
		elif status == 1:
			# We shouldn't actually be able to hit this.
			print stamp() + " - File does not exist: {0}".format(currentFile)
		elif status == 2:
			print stamp() + " - Hash already exists for {0}".format(currentFile)
		else:
			print stamp() + " - Unknown error has occurred."
	return

def getNewFiles(db):
	times['rsync'] = time.time()
	print stamp() + " - Syncing from mothership."
	status = subprocess.call('rsync -av --itemize-changes --delete-before picpie@scheels.dyndns.org:/home/picpie/picpie/ {} >{} 2>&1'.format(gets('inboundFilePath'), gets('picpieDir') + "/rsync.log"), shell=True)
	print stamp() + " - Syncing complete."
	times['processing'] = time.time()
	if status:
		print stamp() + " - Error syncing files.  Check log file: " + gets('storagePath') + "/rsync.log"
	for root, dir, files in os.walk(gets('inboundFilePath')):
		for fname in files:
			currentFile = root + "/" + fname
			processFile(db, currentFile)
	return

def runSlideShow():
	drivers = ('directfb', 'fbcon', 'svgalib')
	os.putenv('SDL_FBDEV', '/dev/fb0')

	found = False
	for driver in drivers:
		if not os.getenv('SDL_VIDEODRIVER'):
			os.putenv('SDL_VIDEODRIVER', driver)
		try:
			pygame.display.init()
		except pygame.error:
			continue
		found = True
		break
	if not found:
		raise Exception('No suitable video driver found.')

	screenSize = (pygame.display.Info().current_w, pygame.display.Info().current_h)
	screen = pygame.display.set_mode(screenSize, pygame.FULLSCREEN)

	# Make mouse cursor go away
	pygame.mouse.set_visible(False)

	# Init it
	pygame.init()

	firstIteration = True
	while 1:
		for waitTime in range(int(gets('pictureDuration'))):
			if firstIteration = False:
				pygame.time.wait(1000)
				checkEvents()
		firstIteration = False
		if os.listdir(gets('storagePath')) == []:
			print stamp() + " - No files in " + gets('StoragePath')
			waitPage('nofiles')
		else:
			fileName = gets('storagePath') + "/" + random.choice(os.listdir(gets('storagePath')))
			if os.path.splitext(fileName)[1].lower()[1:] not in gets('picExts').split(','):
				print stamp() + " - skipping " + fileName + ". Not a picture."
				continue

			# Get the size appropriate for the new pictures for resizing
			# Maintains aspect ratio.
			newSize = getNewSize(fileName)

			img = pygame.image.load(fileName).convert()
			img = pygame.transform.scale(img, newSize)
			
			# newSize might work, but let's get the real size just to be sure
			loadedImageSize = img.get_rect().size

			# We start with a black screen to overwrite anything previously present
			screen.fill((0,0,0))

			# Blit our image to the screen, centered.
			screen.blit(img,getImgCenterCoords(img))

			# But nothing shows up until we update.
			pygame.display.update()
	return

def waitPage(status):
	if status == 'nofiles':
		screen.convert()
		screen.fill((255,255,255))	#Give us some white
		font = pygame.font.Font(None, 36)
		text = font.render('No files to process.', 1, (10, 10, 10))
		textpos = text.get_rect()
		textpos.centerx = screen.get_rect().centerx
		screen.blit(text, textpos)
		pygame.time.wait(1000)
		pygame.display.flip()
	return

def checkEvents():
	for e in pygame.event.get():
		if e.type == pygame.KEYDOWN:
			if e.key == pygame.K_q:
				logIt(1,'Q key pressed.  Exiting application.')
				pygame.quit()
				sys.exit()
	return

def getImgCenterCoords(img):
	width = img.get_rect().size[0]
	imgCenterHoriz = int(width / 2)

	height = img.get_rect().size[1]
	imgCenterVert = int(height / 2)

	#logIt(1,'center: ' + str(imgCenterHoriz))
	#logIt(1,'center: ' + str(imgCenterVert))

	centerHoriz = True
	#logIt(1,'img ratio: ' + str(width / height))
	#logIt(1,'screen ratio: ' + str(screenResolution[0] / screenResolution[1]))

	imgRatio = width / height
	screenRatio = screenResolution[0] / screenResolution[1]
	if imgRatio > screenRatio:
		centerHoriz = False

	if centerHoriz == True:
		imgX = (screenResolution[0] / 2) - imgCenterHoriz
		imgY = 0
	else:
		imgX = 0
		imgY = (screenResolution[1] / 2) - imgCenterVert

	return (imgX, imgY)

def logIt(debugLevel,msg):
	if debugLevel <= int(gets('debug')):
		f = open('/home/pi/sda1/picpie/log.txt','aw')
		f.write(msg + '\n')
	return

def getImgSize(fileName):
	return Image.open(fileName).size

def getNewSize(fileName):
	imageSize = getImgSize(fileName)
	ratioWidth = screenResolution[0] / imageSize[0]
	ratioHeight = screenResolution[1] / imageSize[1]

	#logIt(1,'screenResolution: ' + str(screenResolution))
	#logIt(1,'imageSize       : ' + str(imageSize))
	#logIt(1,'ratioWidth:  ' + str(ratioWidth))
	#logIt(1,'ratioHeight: ' + str(ratioHeight))

	useRatio = screenResolution[0] / imageSize[0]
	if screenResolution[1] / imageSize[1] < screenResolution[0] / imageSize[0]:
		useRatio = screenResolution[1] / imageSize[1]

	width = int(math.floor(imageSize[0] * useRatio))
	height = int(math.floor(imageSize[1] * useRatio))

	#logIt(1,'New image size:   ({}, {})'.format(width,height))
	
	return (width, height)

def getOldFileName(db,filename):
	cur = db.cursor()
	cur.execute('SELECT old_filename FROM hashes WHERE filename = ?',(filename,))
	theFile = cur.fetchall()
	if not theFile:
		fileString = ""
	else:
		fileString = theFile[0][0]
	return fileString

def refreshFiles():
	times['refresh'] = time.time()
	resolution = ""
	db = getSQLite3()

	print stamp() + " - Checking for new files."
	getNewFiles(db)

	print stamp() + " - Verifying existing storage."
	checkResized(db)

	print stamp() + " - Verifying database."
	verifyDB(db)

	return

def verifyDB(db):
	times['verifyDB'] = time.time()
	cur = db.cursor()
	cur.execute('SELECT old_filename FROM hashes')
	oldFiles = cur.fetchall()
	if not oldFiles:
		return
	for filename in oldFiles[0]:
		if not os.path.isfile(filename):
			if int(gets('debug')):
				print stamp() + " - Cleaning up from missing file: " + filename
			cur.execute('DELETE FROM hashes WHERE old_filename = ?',(filename,))
	return

def checkResized(db):
	times['checkResized'] = time.time()
	exceptions = ('hash_list.db','rsync.log','bin')
	for filename in os.listdir(gets('storagePath')):
		if filename not in exceptions:
			filename = gets('storagePath') + "/" + filename
			oldFileName = getOldFileName(db,filename)
			if not oldFileName or not os.path.isfile(oldFileName):
				print stamp() + " - Deleting: " + filename
				os.remove(filename)
	return

def countFiles():
	count = 0
	fileList = os.listdir(gets('storagePath'))
	if fileList != []:
		for fileName in fileList:
			count += 1
	return count

if __name__ == "__main__":
	main()


