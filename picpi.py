#!/usr/bin/python

"""
Requirements:
Packages:
jhead
sqlite3
python-arrow
python-pyexiv2
"""
from __future__ import division
from __future__ import print_function

import hashlib
import sqlite3
import sys
import time
import os
import subprocess
import shutil
#import random
import pygame
import math
import ConfigParser
import dropbox
import arrow
import pyexiv2
from PIL import Image

def main():
	global db
	global times
	global slideshowMode
	slideshowMode = False

	if len(sys.argv) > 1 and sys.argv[1] == 'config':
		set_config()
	if len(sys.argv) > 1 and sys.argv[1] == 'wipe':
		wipeAll()
		log('Wiped.')
		sys.exit(0)
	if not os.path.isfile('/home/pi/.picpi.conf'):
		log('picpi does not appear to be configured.  Please run this first: ' + sys.argv[0] + ' config')
		sys.exit(0)

	set_config()

	times = {'program start':time.time(),}

	db = getSQLite3()

	# Do our directories exist?
	dirList = ('picpiDir','storagePath','inboundFilePath','tmpPath',)
	for dir in dirList:
		if not os.path.isdir(gets(dir)):
			os.mkdir(gets(dir))

	screenResolution = getResolution()

	if len(sys.argv) > 1 and sys.argv[1] == 'refresh':
		refreshFiles()
	else:
		slideshowMode = True
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
	configFile = os.path.expanduser('~') + '/.picpi.conf'
	c.read(configFile)
	return c

def set_config():
	c = getc()
	configFile = os.path.expanduser('~') + '/.picpi.conf'
	if os.path.isfile(configFile) and len(sys.argv) > 1 and sys.argv[1] == 'config':
		log("Config file already exists: " + configFile)
		log("If you really want to reconfigure picpi, please delete the config.")
	if 'Main' not in c.sections():
		c.add_section('Main')
		baseDir = os.getcwd()
		c.set('Main','picpiDir',baseDir + '/picpi')
		c.set('Main','storagePath',baseDir + '/picpi/storage')
		c.set('Main','inboundFilePath',baseDir + '/picpi/inbound')
		c.set('Main','tmpPath',baseDir + '/picpi/tmp')
		c.set('Main','picExts',','.join(('jpg','jpeg','tif','tiff','gif','png','bmp')))
		c.set('Main','vidExts',','.join(('wmv','mpg2','mpg4','mpg','mkv')))
		c.set('Main','pictureDuration',5)
		c.set('Main','resize_width',1920)
		c.set('Main','resize_height',1920)	# Same as width in case someone wants to go vertical with a monitor
		c.set('Main','debug',0)
		c.set('Main','dropbox_access_token','')
		c.set('Main','dropbox_base_dir','/Media/picpi')
		cfg = open(configFile,'w')
		c.write(cfg)
		cfg.close()
		log("picpi configured with default settings.")
		log("If customization is needed, please edit " + configFile)
		sys.exit(0)
	return

def stamp():
	# Our timestamp.  Just making it easy.
	return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))

def getSQLite3():
	# Opens the DB, creates if it does not exist.
	dbName = gets('picpiDir') + '/file_list.db'
	db = sqlite3.connect(dbName)
	cur = db.cursor()

	tableName = 'files'
	column_text = 'path TEXT UNIQUE, revision INTEGER, bytes INTEGER, date_synced REAL, modified TEXT, local_path TEXT, blacklisted INTEGER'
	cur.execute('CREATE TABLE IF NOT EXISTS {} ({})'.format(tableName, column_text))

	tableName = 'directories'
	column_text = 'path TEXT UNIQUE, hash TEXT, date_added REAL'
	cur.execute('CREATE TABLE IF NOT EXISTS {} ({})'.format(tableName, column_text))

	db.commit()
	return db

def getResolution():
	log('in getResolution()',3)
	#global screenResolution
	log('Running fbset to get resolution.',2)
	screenResolution = subprocess.check_output("fbset -s | grep '^mode' | sed 's/\"//g' | awk '{ print $2 }'", shell=True).rstrip()
	minusPos = screenResolution.find('-')
	if minusPos >= 0:
		screenResolution = screenResolution[0:minusPos].split('x')
	log('Returned from fbset.',3)
	log('screenResolution: ' + repr(screenResolution),2)
	screenResolution = (int(screenResolution[0]),int(screenResolution[1]))
	#screenResolution = (1920,1080)	#assume 1080p
	log("Found resolution: " + repr(screenResolution),2)
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
	log("Resizing:    " + currentFile,2)
	image = Image.open(currentFile)
	image.thumbnail((int(gets('resize_width')),int(gets('resize_height'))), Image.ANTIALIAS)
	image.save(newFName)

	#Copy exif data
	copyExif(currentFile,newFName)
	return
 
def rotateImage(newFName):
	log("Rotating:    " + newFName,2)
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

def processFile(db, currentFile, newFName):
	fileExt = os.path.splitext(currentFile)[1]
	fileBase = os.path.split(currentFile)[1]
	tmpName = gets('tmpPath') + "/" + fileBase
	
	newPath = gets('storagePath') + "/" + getRelative(os.path.split(currentFile)[0], gets('inboundFilePath'))
	newFName = newPath + "/" + fileBase
	if not os.path.isdir(newPath):
		log('Creating directory: ' + newPath,1)
		os.mkdir(newPath)

	log("Processing:  " + currentFile,1)
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
			ProcessIt = False

	if processIt:
		resizeImage(currentFile, tmpName)
		rotateImage(tmpName)
	shutil.move(tmpName,newFName)

	return

def getHashFromDB(path):
	cur = db.cursor()
	cur.execute('SELECT hash FROM directories WHERE path = ?', (path,))
	results = cur.fetchall()
	if not results:
		return None
	else:
		return results

def dropboxWalk(client, path, fileList=[], dirList=[]):
	data = client.metadata(path)
	if data['is_dir']:
		dirList.append(data['path'])
		relativePath = getRelative(data['path'],gets('dropbox_base_dir'))
		newPath = gets('inboundFilePath') + '/' + relativePath
		if not os.path.exists(newPath):
			log('Creating directory: ' + newPath)
			os.mkdir(newPath)
			storeDir(path, data)
		for entry in data['contents']:
			dropboxWalk(client, entry['path'], fileList, dirList)
	else:
		fileList.append(data['path'])
		getDropboxFile(client, data['path'])
	return fileList, dirList

def getDropboxFile(client, path):
	for file in os.listdir(gets('tmppath')):
		os.remove(gets('tmppath') + '/' + file)
	newFile = gets('inboundFilePath') + '/' + getRelative(path, gets('dropbox_base_dir'))
	metadata = client.metadata(path)

	log('Database revision: ' + str(metadata['revision']) + ' - ' + str(getRevision(path)) + ' :Dropbox revision',2)
	if not os.path.exists(newFile) or metadata['revision'] != getRevision(path):
		log('In process if.',3)
		log("Downloading: " + getRelative(path, gets('dropbox_base_dir')))
		outFile = gets('tmpPath') + '/' + os.path.split(path)[1]
		f = client.get_file(path)
		save = open(outFile, 'w')
		startTime = int(round(time.time() * 1000))
		save.write(f.read())
		duration = int(round(time.time() * 1000)) - startTime
		save.close()
		shutil.move(outFile, newFile)
		fileSize = os.path.getsize(newFile)
		bps = fileSize / duration

		# Set modified time to that on Dropbox.  Don't use 'modified'.
		newTime = arrow.get(metadata['client_mtime'].replace('+0000',''),'ddd, D MMM YYYY HH:mm:ss').to('local').timestamp
		os.utime(newFile,(newTime,newTime))

		log(" - Speed: " + str(round(bps / 1024,2)) + ' MB/s',2)

		storageName = gets('storagePath') + '/' + getRelative(newFile, gets('inboundFilePath'))
		processFile(db, newFile, storageName)
		storeFile(path, metadata, storageName)
	else:
		log('Skipping:    ' + getRelative(path, gets('dropbox_base_dir')) + '. File already exists.')
	return

def getRevision(file):
	cur = db.cursor()
	cur.execute('SELECT revision FROM files WHERE path = (?)',(file,))
	results = cur.fetchall()
	if not results:
		return None
	else:
		return results[0][0]

def wipeAll():
	dbFile = gets('picpidir') + '/' + 'file_list.db'
	if os.path.exists(dbFile):
		if not os.remove(dbFile):
			log("DB file deleted: " + dbFile)
		else:
			log("Unable to delete DB file: " + dbFile)
	for dir in ('inboundFilePath', 'storagePath', 'tmpPath',):
		if os.path.isdir(gets(dir)):
			shutil.rmtree(gets(dir),ignore_errors=True)
			log("Directory deleted: " + gets(dir))
	return

def storeFile(path, metadata, newPath):
	cur = db.cursor()
	cur.execute('INSERT INTO files VALUES (?, ?, ?, ?, ?, ?)', (path, metadata['revision'], metadata['bytes'], stamp(), metadata['client_mtime'].replace('+0000',''), newPath))
	db.commit()
	return

def storeDir(path, metadata):
	cur = db.cursor()
	cur.execute('INSERT INTO directories VALUES (?, ?, ?)', (path, metadata['hash'], stamp()))
	db.commit()
	return

def getRelative(path,base):
	oldPath = path.split('/')
	base_dir = base.split('/')
	try:
		while base_dir[0].lower() == oldPath[0].lower():
			del oldPath[0]
			del base_dir[0]
	except IndexError:
		relativePath = '/'.join(oldPath)
	return relativePath

def getNewFiles():
	global db
	times['sync'] = time.time()
	log("Syncing from mothership.")
	
	# Get Dropbox contents
	client = dropbox.client.DropboxClient(gets('dropbox_access_token'))
	baseDir = gets('dropbox_base_dir')
	if not client.metadata(baseDir)['is_dir']:
		log('base Dropbox path is not a directory.')
		sys.exit(1)
	fileList, dirList = dropboxWalk(client, baseDir)
	log("Syncing complete.")
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

	log('Available resolutions: ' + str(pygame.display.list_modes()))
	if pygame.display.mode_ok(pygame.display.list_modes()[0],pygame.FULLSCREEN):
		log('Setting resolution: ' + str(pygame.display.list_modes()[0]))
		pygame.display.set_mode(pygame.display.list_modes()[0],pygame.FULLSCREEN)


	screenSize = (pygame.display.Info().current_w, pygame.display.Info().current_h)
	screen = pygame.display.set_mode(screenSize, pygame.FULLSCREEN)

	# Make mouse cursor go away
	log('Making mouse cursor disappear.',2)
	pygame.mouse.set_visible(False)

	# Init it
	log('Attempting to init pygame.',2)
	pygame.init()
	log('Past pygame.init',2)

	firstIteration = True
	while 1:
		log('Beginning slideshow loop.',2)
		if firstIteration == False:
			log('Waiting.',3)
			for waitTime in range(int(gets('pictureDuration'))*4):
				pygame.time.wait(250)
				nextPic = checkEvents()
				if nextPic:
					log('Next pic.')
					break
		firstIteration = False
		log('Checking for files in ' + gets('storagePath'),2)
		if os.listdir(gets('storagePath')) == []:
			log("No files in " + gets('StoragePath'))
			waitPage('nofiles')
		else:
			fileName = getFilenameFromDB()
			log('Displaying file: ' + fileName,1)
			if os.path.splitext(fileName)[1].lower()[1:] not in gets('picExts').split(','):
				log("skipping " + fileName + ". Not a picture.")
				continue
			if not os.path.exists(fileName):
				log('Database does not match storage Contents: File ' + fileName + ' does not exist on disk.  Please run verify on database contents.')

			# Get the size appropriate for the new pictures for resizing
			# Maintains aspect ratio.
			newSize = getNewSize(fileName)
			log('newSize: ' + repr(newSize))

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

def getFilenameFromDB():
	cur = db.cursor()
	cur.execute('SELECT local_path FROM files ORDER BY RANDOM() LIMIT 1')
	results = cur.fetchall()
	if not results:
		fileName = ""
	else:
		fileName = results[0][0]
	return fileName

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

def checkEvents(fileName=None):
	nextPic = False
	for e in pygame.event.get():
		if e.type == pygame.KEYDOWN:
			if e.key == pygame.K_SPACE:
				log('Advancing slideshow manually.',2)
				nextPic = True
			if e.key == pygame.K_x or e.key == pygame.K_BACKSPACE or e.key == pygame.K_DELETE:
				blacklistPic(fileName)
				nextPic = True
			if e.key == pygame.K_q:
				log('Q key pressed.  Exiting application.')
				pygame.quit()
				sys.exit()
	return nextPic

def blacklistPic(fileName):
	log('in blacklistPic(' + fileName + ')',2)
	db.cursor().execute('UPDATE files SET blacklisted = 1 WHERE local_path = (?)',(fileName,))
	db.commit()
	return

def getImgCenterCoords(img):
	width = img.get_rect().size[0]
	imgCenterHoriz = int(width / 2)

	height = img.get_rect().size[1]
	imgCenterVert = int(height / 2)

	centerHoriz = True

	imgRatio = width / height
	screenResolution = getResolution()
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

def getImgSize(fileName):
	return Image.open(fileName).size

def getNewSize(fileName, newWidth=None, newHeight=None):
	log('getNewSize() entered',3)
	imageSize = getImgSize(fileName)
	if newWidth:
		useWidth = newWidth
	else:
		useWidth = getResolution()[0]
	if newHeight:
		useHeight = newHeight
	else:
		useHeight = getResolution()[1]
	
	ratioWidth = useWidth / imageSize[0]
	ratioHeight = useHeight / imageSize[1]

	useRatio = min(useWidth / imageSize[0], useHeight / imageSize[1])

	width = int(math.floor(imageSize[0] * useRatio))
	height = int(math.floor(imageSize[1] * useRatio))

	log('getNewSize() returns ' + str(width) + 'x' + str(height) + 'as tuple.')
	return (width, height)

def copyExif(source, destination):
	# Get source metadata
	srcmeta = pyexiv2.ImageMetadata(source)
	srcmeta.read()

	# Get Destination metadata
	destmeta = pyexiv2.ImageMetadata(destination)
	destmeta.read()

	# Copy metadata to new file
	srcmeta.copy(destmeta)
	destmeta.write()
	return

def log(msg, debugLevel=0):
	if int(gets('debug')) >= debugLevel:
		if debugLevel > 0:
			debugMsg = ' - DEBUG' + str(debugLevel)
		else:
			debugMsg = ' - INFO  '
		newMsg = stamp() + debugMsg + ' - ' + msg
		f=open(gets('picpidir') + '/picpi.log', 'aw')
		if not slideshowMode:
			print(newMsg)
		print(newMsg,file=f)
		f.close()
	return

def refreshFiles():
	times['refresh'] = time.time()
	resolution = ""

	log("Checking for new files.")
	getNewFiles()

	return

if __name__ == "__main__":
	main()


