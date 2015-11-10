#!/usr/bin/python

"""
Requirements:
Packages:
jhead
sqlite3
python-arrow
python-dateutil (required by arrow)
python-pyexiv2
python-dropbox from https://www.dropbox.com/developers-v1/core/sdks/python
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

VERSION='0.7.0'

def main():
	global db
	global times
	global slideshowMode
	global MAX_RES
	slideshowMode = False
	times = {}

	if len(sys.argv) > 1 and sys.argv[1] == 'config':
		set_config()
	if len(sys.argv) > 1 and sys.argv[1] == 'wipe':
		wipeAll()
		log('Wiped.')
		cleanUp(0)
	if not os.path.isfile(os.path.expanduser('~') + '/.picpi.conf'):
		log('picpi does not appear to be configured.  Please run this first: ' + sys.argv[0] + ' config')
		cleanUp(0)

	#read_config()

	if gets('max_res_x') and gets('max_res_y'):
		MAX_RES = (int(gets('max_res_x')),int(gets('max_res_y')))
	else:
		MAX_RES = (640,480)

	times['program start'] = time.time()

	# Do our directories exist?
	dirList = ('picpiDir','storagePath','inboundpath','tmpPath',)
	for dir in dirList:
		if not os.path.isdir(gets(dir)):
			log('Creating directory: ' + dir,3)
			os.mkdir(gets(dir))

	db = getSQLite3()

	log('Command line arguments: ' + repr(sys.argv))
	if len(sys.argv) > 1 and sys.argv[1] == 'refresh':
		log('Refreshing files.',1)
		refreshFiles()
	elif len(sys.argv) > 1 and sys.argv[1] == 'clear_blacklist':
		resetBlacklist()
		cleanUp()
	else:
		log('Entering slideshow.',1)
		slideshowMode = True
		runSlideShow()

	times['Complete'] = time.time()
	cleanUp()
	return

def cleanUp(status=0):
	for key, value in times.iteritems():
		print(key + ' - ' + str(time.localtime(value)))
	sys.exit(status)
	return

def p():
	log('Entering pdb trace.')
	import pdb
	pdb.set_trace()
	return

def gets(setting):
	c = getc()
	try:
		value = c.get('Main',setting)
	except ConfigParser.NoOptionError:
		value = None
	return value

def getc():
	c = ConfigParser.ConfigParser()
	configFile = os.path.expanduser('~') + '/.picpi.conf'
	c.read(configFile)
	return c

def set_config():
	#log('Entering set_config()',1)
	c = getc()
	configFile = os.path.expanduser('~') + '/.picpi.conf'
	#log('Config file: ' + configFile,2)

	baseDir = os.getcwd()
	print('********************************************************************************')
	print('The Base Directory is the directory which all others are based off of.\nInbound files and resized files will all be stored in this directory.\nThe default is the current directory (' + os.getcwd() + ').\n')
	tmp = raw_input('1)  What Base Directory would you like to use?  <Enter> for default: ')
	if tmp != '':
		baseDir = tmp

	inboundpath = baseDir + '/inbound'
	print('********************************************************************************')
	print('The Inbound File Path stores files as they are pulled from the remote location.\nThe default location is (' + baseDir + '/inbound' + ')\n')
	tmp = raw_input('2)  What Inbound File Path would you like to use?  <Enter> for default: ')
	if tmp != '':
		inboundpath = tmp

	storagePath = baseDir + '/storage'
	print('********************************************************************************')
	print('The Storage Path stores files after they are reduced in size.\nThe default location is(' + baseDir + '/storage' + ')\n')
	tmp = raw_input('3)  What Storage Path would you like to use?  <Enter> for default: ')
	if tmp != '':
		storagePath = tmp

	tmpPath = baseDir + '/tmp'
	print('********************************************************************************')
	print('The Temporary Path stores files temporarily during resizing and rotating.\nThis prevents a partially converted file due to a program interruption from being stored permanently.\n')
	tmp = raw_input('4)  What Temporary Path would you like to use?  <Enter> for default: ')
	if tmp != '':
		tmpPath = tmp

	print('********************************************************************************')
	print('If you don\'t know what this is, please leave it blank.  One will be generated for you.\nIf you have an existing one you\'d like to use, enter it here.\n')
	dropbox_access_token = raw_input('5)  Enter your Dropbox Access Token.  There is no default: ')
	while dropbox_access_token == '':
		app_key = 'xe0mrs40eqfvcsj'
		app_secret = '0tgeubc7ujjlo6t'
		flow = dropbox.client.DropboxOAuth2FlowNoRedirect(app_key, app_secret)
		authURL = flow.start()
		print('')
		print('    a) Copy and paste this URL into a browser:\n       ' + authURL)
		print('    b) Click \'Allow\'.  You may be required to log into your DropBox account, first.')
		authCode = raw_input('    c) Copy and Paste the Authorization Code here: ').strip()
		try:
			dropbox_access_token = flow.finish(authCode)[0]
		except dropbox.rest.ErrorResponse:
			print('')
			print('     **************************************************')
			print('     * Invalid authorization code.  Please try again. *')
			print('     **************************************************')
			dropbox_access_token = ''
			continue
		print('Testing... ',end='')
		try:
			client = dropbox.client.DropboxClient(dropbox_access_token)
			print('SUCCESS!')
		except dropbox.rest.ErrorResponse:
			print('Failed.  Invalid access token.  Please try again.')
			dropbox_access_token = ''

	sys.exit(0)

	if os.path.isfile(configFile) and len(sys.argv) > 1 and sys.argv[1] == 'config':
		log("Config file already exists: " + configFile)
		log("If you really want to reconfigure picpi, please delete the config.")
	if 'Main' not in c.sections():
		c.add_section('Main')
		log('baseDir = ' + baseDir,2)
		c.set('Main','picpiDir',baseDir + '/picpi')
		c.set('Main','storagePath',baseDir + '/picpi/storage')
		c.set('Main','inboundpath',baseDir + '/picpi/inbound')
		c.set('Main','tmpPath',baseDir + '/picpi/tmp')
		c.set('Main','picExts',','.join(('jpg','jpeg','tif','tiff','gif','png','bmp')))
		c.set('Main','vidExts',','.join(('wmv','mpg2','mpg4','mpg','mkv')))
		c.set('Main','pictureDuration',5)
		c.set('Main','resize_width',1920)
		c.set('Main','resize_height',1920)	# Same as width in case someone wants to go vertical with a monitor
		c.set('Main','debug',0)
		c.set('Main','dropbox_access_token','')
		c.set('Main','dropbox_base_dir','/')
		#c.set('Main','max_res_x','640')
		#c.set('Main','max_res_y','480')
		cfg = open(configFile,'w')
		c.write(cfg)
		cfg.close()
		log("picpi configured with default settings.")
		log("If customization is needed, please edit " + configFile)
		cleanUp(0)
	return

def stamp():
	# Our timestamp.  Just making it easy.
	return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))

def getSQLite3():
	log('Entering getSQLite3()',2)
	# Opens the DB, creates if it does not exist.
	dbName = gets('picpiDir') + '/file_list.db'
	db = sqlite3.connect(dbName)
	cur = db.cursor()

	tableName = 'files'
	column_text = 'remote_filename TEXT UNIQUE, inbound_filename TEXT UNIQUE, storage_filename TEXT UNIQUE,revision INTEGER, bytes INTEGER, date_synced REAL, modified TEXT, blacklisted INTEGER'
	cur.execute('CREATE TABLE IF NOT EXISTS {} ({})'.format(tableName, column_text))

	tableName = 'directories'
	column_text = 'remote_dir TEXT UNIQUE, inbound_dir TEXT UNIQUE, storage_dir TEXT, hash TEXT, date_added REAL'
	cur.execute('CREATE TABLE IF NOT EXISTS {} ({})'.format(tableName, column_text))

	db.commit()
	return db

def isAnimatedGif(fileName):
	log('in isAnimatedGif(' + fileName + ')',2)
	gif = Image.open(fileName)
	try:
		gif.seek(1)
	except EOFError:
		animated = False
	else:
		animated = True
	log('animated=' + repr(animated),1)
	return animated

def resizeImage(inboundFilename,tmpName):
	log('in resizeImage(' + inboundFilename + ',' + tmpName + ')',2)
	image = Image.open(inboundFilename)
	log('resizing to ' + gets('resize_width') + 'x' + gets('resize_height'),2)
	image.thumbnail((int(gets('resize_width')),int(gets('resize_height'))), Image.ANTIALIAS)
	image.save(tmpName)

	#Copy exif data
	log('Copying exif data.',2)
	copyExif(inboundFilename,tmpName)
	return
 
def rotateImage(newFName):
	log('in rotateImage(' + newFName + ')',2)
	subprocess.call('jhead -autorot -q \"{}\" >/dev/null 2>&1'.format(newFName), shell=True)
	return

def makePath(pathToCreate):
	pathToCreate = pathToCreate.lstrip('/')
	for x in range(len(pathToCreate.split('/'))):
		path = '/'.join(pathToCreate.split('/')[0:x+1])

		for dirName in ('storagePath', 'inboundpath',):
			if not os.path.exists(gets(dirName) + '/' + path):
				os.mkdir(gets(dirName) + '/' + path)
	return

def stripDoubleSlash(filename):
	while '//' in filename:
		filename = filename.replace('//','/')
	return filename

def processFile(db, remoteFilename):
	log('in processFile(' + repr(db) + ',' + remoteFilename + ')',2)
	ext = os.path.splitext(remoteFilename)[1][1:].lower()
	fileBase = os.path.split(remoteFilename)[1]

	inboundFilename = gets('inboundpath') + '/' + remoteFilename
	inboundFilename = stripDoubleSlash(inboundFilename)

	tmpName = gets('tmpPath') + "/" + os.path.split(remoteFilename)[1]
	tmpName = stripDoubleSlash(tmpName)

	storageFilename = gets('storagePath') + '/' + remoteFilename
	storageFilename = stripDoubleSlash(storageFilename)
	
	makePath(os.path.split(remoteFilename)[0])

	log("Processing:  " + remoteFilename,1)

	processIt = True
	if ext not in gets('picExts').lower().split(','):
		processIt = False
	if ext == 'gif':
		if isAnimatedGif(remoteFilename):
			#We're only resizing and rotating if it's not animated.
			#If it's animated, someone should have already oriented and resized it properly
			ProcessIt = False

	if processIt:
		resizeImage(inboundFilename, tmpName)
		rotateImage(tmpName)
	shutil.move(tmpName,storageFilename)

	return

def getHashFromDB(remoteDir):
	cur = db.cursor()
	cur.execute('SELECT hash FROM directories WHERE remote_dir = ?', (remoteDir,))
	results = cur.fetchall()
	if not results:
		return None
	else:
		return results

def dropboxWalk(client, path, fileList=[], dirList=[]):
	data = client.metadata(path)
	if data['is_dir']:
		dirList.append(data['path'])
		inboundDirname = gets('inboundpath') + '/' + path
		if not os.path.exists(inboundDirname):
			log('Creating directory: ' + inboundDirname)
			os.mkdir(inboundDirname)
			storeDir(path, data)
		for entry in data['contents']:
			dropboxWalk(client, entry['path'], fileList, dirList)
	else:
		fileList.append(data['path'])
		getDropboxFile(client, data['path'])
	return fileList, dirList

def deleteRemoved():
	times['deleteRemoved'] = time.time()
	log('Checking for files no longer on remote side.')
	client = dropbox.client.DropboxClient(gets('dropbox_access_token'))
	for dir in os.walk(gets('inboundpath')):
		for file in dir[2]:
			inboundFilename = dir[0] + '/' + file
			
			log('Checking ' + inboundFilename)
			remoteFilename = db.cursor().execute('SELECT remote_filename FROM files WHERE inbound_filename = (?)',(inboundFilename,)).fetchall()
			if remoteFilename == []:
				print("DANGER WILL ROBINSON!")
			remoteFilename = remoteFilename[0][0]

			log('Checking dropbox for: ' + remoteFilename,3)
			try:
				metadata = client.metadata(remoteFilename)
				if 'is_deleted' in metadata:
					if metadata['is_deleted'] == True:
						log('Deleting file removed from dropbox: ' + inboundFilename)
						deleteFile(inboundFilename)
						continue
			except dropbox.rest.ErrorResponse as e:
				if e.status == 404:
					log('Deleting file not in dropbox: ' + inboundFilename)
					deleteFile(inboundFilename)
	return

def deleteFile(storageFilename):
	os.remove(storageFilename)
	cur = db.cursor()
	cur.execute('DELETE FROM files WHERE storage_filename = (?)',(storageFilename,))
	return

def getDropboxFile(client, remoteFilename):
	for file in os.listdir(gets('tmppath')):
		os.remove(gets('tmppath') + '/' + file)
	inboundFilename = gets('inboundpath') + '/' + remoteFilename
	metadata = client.metadata(remoteFilename)

	log('Database revision: ' + str(metadata['revision']) + ' - ' + str(getRevision(remoteFilename)) + ' :Dropbox revision',2)
	if not os.path.exists(inboundFilename) or metadata['revision'] != getRevision(remoteFilename):
		log('In process if.',3)
		log("Downloading: " + remoteFilename)
		tmpFilename = gets('tmpPath') + '/' + os.path.split(remoteFilename)[1]
		f = client.get_file(remoteFilename)
		save = open(tmpFilename, 'w')
		startTime = int(round(time.time() * 1000))
		save.write(f.read())
		duration = int(round(time.time() * 1000)) - startTime
		save.close()
		shutil.move(tmpFilename, inboundFilename)
		bps = os.path.getsize(inboundFilename) / duration

		# Set modified time to that on Dropbox.  Don't use 'modified'.
		newTime = arrow.get(metadata['client_mtime'].replace('+0000',''),'ddd, D MMM YYYY HH:mm:ss').to('local').timestamp
		os.utime(inboundFilename,(newTime,newTime))

		log("Speed: " + str(round(bps / 1024,2)) + ' MB/s',1)

		processFile(db, remoteFilename)
		storeFile(remoteFilename, metadata)
	else:
		log('Skipping:    ' + remoteFilename + '. File already exists.')
	return

def getRevision(remoteFilename):
	cur = db.cursor()
	cur.execute('SELECT revision FROM files WHERE remote_filename = (?)',(remoteFilename,))
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
	for dir in ('inboundpath', 'storagePath', 'tmpPath',):
		if os.path.isdir(gets(dir)):
			shutil.rmtree(gets(dir),ignore_errors=True)
			log("Directory deleted: " + gets(dir))
	return

def storeFile(remoteFilename, metadata):
	storageFilename = gets('storagepath') + '/' + remoteFilename
	storageFilename = storageFilename.replace('//','/')
	inboundFilename = gets('inboundpath') + '/' + remoteFilename
	inboundFilename = inboundFilename.replace('//','/')

	cur = db.cursor()
	cur.execute('INSERT INTO files VALUES (?, ?, ?, ?, ?, ?, ?, ?)', (remoteFilename, inboundFilename, storageFilename ,metadata['revision'], metadata['bytes'], stamp(), metadata['client_mtime'].replace('+0000',''), 0))
	db.commit()
	return

def storeDir(remote_dir, metadata):
	cur = db.cursor()
	cur.execute('INSERT INTO directories VALUES (?, ?, ?, ?, ?)', (remote_dir, gets('inboundpath') + '/' + remote_dir, gets('storagePath') + '/' + remote_dir, metadata['hash'], stamp()))
	db.commit()
	return

def getRelative(path,base):
	oldPath = path.split('/')
	base_dir = base.split('/')
	relativePath = None
	try:
		while base_dir[0].lower() == oldPath[0].lower():
			del oldPath[0]
			del base_dir[0]
	except IndexError:
		relativePath = '/'.join(oldPath)
	if not relativePath:
		relativePath = path
	return relativePath

def getNewFiles():
	global db
	global times
	times['sync'] = time.time()
	log("Syncing from mothership.")
	
	# Get Dropbox contents
	client = dropbox.client.DropboxClient(gets('dropbox_access_token'))
	baseDir = gets('dropbox_base_dir')
	if not client.metadata(baseDir)['is_dir']:
		log('base Dropbox path is not a directory.')
		cleanUp(1)
	fileList, dirList = dropboxWalk(client, baseDir)
	log("Syncing complete.")
	return

def removeLock(source):
	os.remove(gets('picpiDir') + '/picpi.' + source + '.pid')
	return

def pidLockFile(source):
	pidFileName = gets('picpiDir') + '/picpi.' + source + '.pid'
	if os.path.exists(pidFileName):
		with open(pidFileName) as pidFile:
			storedPid = pidFile.read()
		procFileName = '/proc/' + storedPid + '/cmdline'
		if os.path.isfile(procFileName):
			with open(procFileName) as procFile:
				cmd = procFile.read().split('\x00')
			if len(cmd) >= 2:
				if os.path.basename(cmd[0]) == 'python' and os.path.basename(cmd[1]) == os.path.basename(__file__):
					log('Slideshow already in progress on PID ' + storedPid + '. Exiting.')
					sys.exit(1)
		os.remove(pidFileName)
	with open(pidFileName,'w') as pidFile:
		pidFile.write(str(os.getpid()))
	return

def runSlideShow():
	global MAX_RES
	
	pidLockFile('slideshow')

	#drivers = ('directfb', 'fbcon', 'svgalib')
	drivers = ('directfb', 'fbcon', 'svgalib', 'x11', 'dga', 'ggi', 'vgl', 'aalib')
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

	log('Available resolutions: ' + str(pygame.display.list_modes()),2)
	if pygame.display.mode_ok(pygame.display.list_modes()[0]):
		if os.getenv('DISPLAY') == None:
			log('Setting resolution: ' + str(pygame.display.list_modes()[0]))
			if gets('force_width') and gets('force_height'):
				MAX_RES = (int(gets('force_width')),int(gets('force_height')))
			else:
				MAX_RES = pygame.display.list_modes()[0]
			screen = pygame.display.set_mode(MAX_RES,pygame.FULLSCREEN)
		else:
			log('Setting resolution default: ' + repr(MAX_RES))
			screen = pygame.display.set_mode(MAX_RES)
	else:
		log('Oh crap.  No video modes available.')


	#screenSize = (pygame.display.Info().current_w, pygame.display.Info().current_h)
	#screen = pygame.display.set_mode(screenSize, pygame.FULLSCREEN)

	# Make mouse cursor go away
	log('Making mouse cursor disappear.',2)
	pygame.mouse.set_visible(False)

	# Init it
	log('Attempting to init pygame.',2)
	#pygame.init()
	log('Past pygame.init',2)

	fileName = ''
	firstIteration = True
	global images
	nextPic = False
	images = []
	while 1:
		log('Beginning slideshow loop.',2)
		if firstIteration == False:
			log('Waiting.',3)
			for waitTime in range(int(gets('pictureDuration'))*4):
				pygame.time.wait(250)
				nextPic = checkEvents(fileName)
				if nextPic:
					log('Next pic.')
					break
		firstIteration = False
		log('Checking for files in ' + gets('storagePath'),2)
		if os.listdir(gets('storagePath')) == []:
			log("No files in " + gets('StoragePath'))
			waitPage(screen, 'nofiles')
		else:
			storageFilename = getFilenameFromDB()
			log('Displaying file: ' + storageFilename,1)
			if os.path.splitext(storageFilename)[1].lower()[1:] not in gets('picExts').split(','):
				log("skipping " + storageFilename + ". Not a picture.")
				continue
			if not os.path.exists(storageFilename):
				log('Database does not match storage Contents: File ' + storageFilename + ' does not exist on disk.  Please run verify on database contents.')

			# Get the size appropriate for the new pictures for resizing
			# Maintains aspect ratio.
			newSize = getNewSize(storageFilename)
			log('newSize: ' + repr(newSize))

			img = pygame.image.load(storageFilename).convert()
			img = pygame.transform.scale(img, newSize)
			images.append(img)

			transition(screen, 'fade',images,nextPic)
			if len(images) == 2:
				del images[0]
	return

def resetBlacklist():
	log('Resetting blacklist')
	cur = db.cursor()
	cur.execute('UPDATE files SET blacklisted = 0 WHERE blacklisted = 1')
	cur.commit()
	return

def getFilenameFromDB():
	cur = db.cursor()
	cur.execute('SELECT storage_filename FROM files WHERE blacklisted != 1 ORDER BY RANDOM() LIMIT 1')
	results = cur.fetchall()
	if not results:
		storageFilename = ""
	else:
		storageFilename = results[0][0]
	return storageFilename

def waitPage(screen, status):
	pygame.font.init()
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
			if e.key == pygame.K_BACKSPACE or e.key == pygame.K_DELETE:
				blacklistPic(fileName)
				nextPic = True
			if e.key == pygame.K_q:
				log('Q key pressed.  Exiting application.')
				pygame.quit()
				removeLock('slideshow')
				cleanUp()
	return nextPic

def blacklistPic(storageFilename):
	log('in blacklistPic(' + storageFilename + ')',2)
	db.cursor().execute('UPDATE files SET blacklisted = 1 WHERE storage_filename = (?)',(storageFilename,))
	db.commit()
	return

def transition(screen,transType,images,manualAdvance=False):
	if transType == 'fade':
		MAX_ALPHA = 255
		MIN_ALPHA = 1
		ALPHA_STEP = 5
		FRAME_DURATION = 0
		if manualAdvance:
			ALPHA_STEP = 25
			FRAME_DURATION = 0
		BLACK = (0,0,0)
		if len(images) == 2:
			img2, img1 = images
			for a in range(MIN_ALPHA,MAX_ALPHA,ALPHA_STEP):
				pygame.time.wait(FRAME_DURATION)
				screen.fill(BLACK)
				img1.set_alpha(a)
				img2.set_alpha(MAX_ALPHA-a)
				screen.blit(img1,tl(img1))
				screen.blit(img2,tl(img2))
				pygame.display.update()
		else:
			img=images[0]
			screen.fill((0,0,0))
			screen.blit(img,tl(img))
			pygame.display.update()
	if transType == 'vert_wipe':
		# Yeah...  this is broken.
		img = images[0]
		size = img.get_size()
		num_fade_rows=16
		offset=0
		background_color=(0,0,0)
		fade_factor = int(256/num_fade_rows)
		for i in range(0,(size[1]+num_fade_rows)):
			arr = pygame.surfarray.pixels_alpha(img)
			offset += 1
			for i in range(0,num_fade_rows):
				if((offset - i) < 0):
					continue
				else:
					for j in range(0, (size[0]-1)):
						if (arr[j][offset-i] <= fade_factor):
							arr[j][offset-i]=0
						else:
							arr[j][offset-i] -= fade_factor
			del arr
			display_surface.fill(background_color)
			display_surface.blit(image_surface, (0,64))
			pygame.display.flip()
	return

def tl(img):
	screenW = pygame.display.Info().current_w
	screenH = pygame.display.Info().current_h
	width = img.get_rect().size[0]
	height = img.get_rect().size[1]
	tl_w = int(screenW / 2) - int(width / 2)
	tl_h = int(screenH / 2) - int(height / 2)
	return tl_w, tl_h

def getImgSize(fileName):
	return Image.open(fileName).size

def getNewSize(fileName, newWidth=None, newHeight=None):
	log('getNewSize() entered',3)
	imageSize = getImgSize(fileName)
	if newWidth:
		useWidth = newWidth
	else:
		useWidth = MAX_RES[0]
	if newHeight:
		useHeight = newHeight
	else:
		useHeight = MAX_RES[1]
	
	ratioWidth = useWidth / imageSize[0]
	ratioHeight = useHeight / imageSize[1]

	useRatio = min(useWidth / imageSize[0], useHeight / imageSize[1])

	width = int(math.floor(imageSize[0] * useRatio))
	height = int(math.floor(imageSize[1] * useRatio))

	log('getNewSize() returns ' + str(width) + 'x' + str(height) + ' as tuple.')
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
	pidLockFile('refresh')
	global times
	times['refresh'] = time.time()
	resolution = ""

	log('Checking for new files.')
	getNewFiles()

	log('Deleting removed files.')
	deleteRemoved()

	removeLock('refresh')
	return

if __name__ == "__main__":
	main()


