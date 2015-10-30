#!/usr/bin/python

"""
Requirements:
Packages:
python-pythonmagick
jhead
sqlite3
Dropbox Python SDK from https://www.dropbox.com/developers-v1/core/sdks/python
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
import dropbox
from PIL import Image

def main():
	global db
	global times

	if len(sys.argv) > 1 and sys.argv[1] == 'config':
		set_config()
	if not os.path.isfile('/home/pi/.piepi.conf'):
		print 'piepi does not appear to be configured.  Please run this first: ' + sys.argv[0] + ' config'
		sys.exit(0)

	set_config()

	times = {'program start':time.time(),}

	db = getSQLite3()

	# Do our directories exist?
	dirList = ('piepiDir','storagePath','inboundFilePath','tmpPath',)
	for dir in dirList:
		if not os.path.isdir(gets(dir)):
			os.mkdir(gets(dir))

	screenResolution = getResolution()

	if len(sys.argv) > 1 and sys.argv[1] == 'refresh':
		refreshFiles()
	else:
		runSlideShow()

	times['Complete'] = time.time()
	return

def p():
	import pdb
	pdb.set_trace()
	return

def gets(setting):
	c = getc()
	return c.get('Main',setting)

def getc():
	c = ConfigParser.ConfigParser()
	configFile = os.path.expanduser('~') + '/.piepi.conf'
	c.read(configFile)
	return c

def set_config():
	c = getc()
	configFile = os.path.expanduser('~') + '/.piepi.conf'
	if os.path.isfile(configFile) and len(sys.argv) > 1 and sys.argv[1] == 'config':
		print "Config file already exists: " + configFile
		print "If you really want to reconfigure piepi, please delete the config."
	if 'Main' not in c.sections():
		c.add_section('Main')
		c.set('Main','piepiDir','/home/pi/piepi')
		c.set('Main','storagePath','/home/pi/piepi/storage')
		c.set('Main','inboundFilePath','/home/pi/piepi/inbound')
		c.set('Main','tmpPath','/home/pi/piepi/tmp')
		c.set('Main','picExts',','.join(('jpg','jpeg','tif','tiff','gif','png','bmp')))
		c.set('Main','vidExts',','.join(('wmv','mpg2','mpg4','mpg','mkv')))
		c.set('Main','pictureDuration',5)
		c.set('Main','debug',0)
		c.set('Main','dropbox_access_token','')
		c.set('Main','dropbox_base_dir','/Media/piepi')
		cfg = open(configFile,'w')
		c.write(cfg)
		cfg.close()
		print "piepi configured with default settings."
		print "If customization is needed, please edit " + configFile
		sys.exit(0)
	return

def stamp():
	# Our timestamp.  Just making it easy.
	return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))

def getSQLite3():
	# Opens the DB, creates if it does not exist.
	dbName = gets('piepiDir') + '/file_list.db'
	db = sqlite3.connect(dbName)
	cur = db.cursor()

	tableName = 'files'
	column_text = 'path TEXT UNIQUE, rev TEXT, bytes INTEGER, sha1hash TEXT UNIQUE, date_synced REAL, modified TEXT'
	cur.execute('CREATE TABLE IF NOT EXISTS {} ({})'.format(tableName, column_text))

	tableName = 'directories'
	column_text = 'path TEXT UNIQUE, hash TEXT, date_added REAL'
	cur.execute('CREATE TABLE IF NOT EXISTS {} ({})'.format(tableName, column_text))

	db.commit()
	return db

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
			print stamp() + " - Success: {}".format(currentFile)
		elif status == 1:
			# We shouldn't actually be able to hit this.
			print stamp() + " - File does not exist: {}".format(currentFile)
		elif status == 2:
			print stamp() + " - Hash already exists for {}".format(currentFile)
		else:
			print stamp() + " - Unknown error has occurred."
	return

def getPathFromDB(path):
	cur = db.cursor()
	cur.execute('SELECT hash FROM directories WHERE path = ?', (path,))
	results = cur.fetchall()[0][0]
	if not fileCount:
		return False
	else:
		return True
	return

	return False

def dropboxWalk(client, path, fileList=[], dirList=[]):
	data = client.metadata(path)
	if data['is_dir']:
		dirList.append(data['path'])
		relativePath = getRelative(data['path'])
		newPath = gets('storagePath') + '/' + relativePath
		if not os.path.exists(newPath):
			print 'Creating directory: ' + newPath
			os.mkdir(newPath)
		for entry in data['contents']:
			dropboxWalk(client, entry['path'], fileList, dirList)
	else:
		fileList.append(data['path'])
		getDropboxFile(client, data['path'])
	return fileList, dirList

def getDropboxFile(client, path):
	for file in os.listdir(gets('tmppath')):
		os.remove(file)
	newFile = gets('storagePath') + '/' + getRelative(path)
	# Need to check revision against stored revision.
	if not os.path.exists(newFile):
		print "Downloading: " + getRelative(path),
		f, metadata = client.get_file_and_metadata(path)
		outFile = gets('tmpPath') + '/' + os.path.split(path)[1]
		save = open(outFile, 'w')
		startTime = int(round(time.time() * 1000))
		save.write(f.read())
		duration = int(round(time.time() * 1000)) - startTime
		save.close()
		#print metadata
		shutil.move(outFile, newFile)
		fileSize = os.path.getsize(newFile)
		bps = fileSize / duration
		print "- Speed: " + str(round(fileSize / duration / 1024,2)) + ' MB/s'
	return

def storeRevision(path):
	cur = db.cursor()
	cur.execute('INSERT INTO files VALUES (?, ?, ?, ?, ?, ?)', (path,))
	results = cur.fetchall()[0][0]
	if not fileCount:
		return False
	else:
		return True

def getRelative(path):
	oldPath = path.split('/')
	dropbox_base_dir = gets('dropbox_base_dir').split('/')
	try:
		while dropbox_base_dir[0].lower() == oldPath[0].lower():
			del oldPath[0]
			del dropbox_base_dir[0]
	except IndexError:
		relativePath = '/'.join(oldPath)
	return relativePath

def getNewFiles(db):
	times['sync'] = time.time()
	print stamp() + " - Syncing from mothership."

	# Get Dropbox contents
	client = dropbox.client.DropboxClient(gets('dropbox_access_token'))
	baseDir = gets('dropbox_base_dir')
	if not client.metadata(baseDir)['is_dir']:
		print 'base Dropbox path is not a directory.'
		sys.exit(1)
	fileList, dirList = dropboxWalk(client, baseDir)
	print stamp() + " - Syncing complete."

	times['processing'] = time.time()
	for root, dir, files in os.walk(gets('inboundFilePath')):
		for fname in files:
			currentFile = root + "/" + fname
			#processFile(db, currentFile)
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
		if firstIteration == False:
			for waitTime in range(int(gets('pictureDuration'))):
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
		f = open('/home/pi/sda1/piepi/log.txt','aw')
		f.write(msg + '\n')
	return

def getImgSize(fileName):
	return Image.open(fileName).size

def getNewSize(fileName):
	imageSize = getImgSize(fileName)
	ratioWidth = screenResolution[0] / imageSize[0]
	ratioHeight = screenResolution[1] / imageSize[1]

	useRatio = screenResolution[0] / imageSize[0]
	if screenResolution[1] / imageSize[1] < screenResolution[0] / imageSize[0]:
		useRatio = screenResolution[1] / imageSize[1]

	width = int(math.floor(imageSize[0] * useRatio))
	height = int(math.floor(imageSize[1] * useRatio))

	return (width, height)

def refreshFiles():
	times['refresh'] = time.time()
	resolution = ""

	print stamp() + " - Checking for new files."
	getNewFiles(db)

	return

if __name__ == "__main__":
	main()


