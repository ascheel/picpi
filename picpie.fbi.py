#!/usr/bin/python

"""
Requirements:
Packages:
python-pythonmagick
jhead
sqlite3
"""

import hashlib
import sqlite3
import sys
import time
import os
import subprocess
import shutil
import PythonMagick as PM
import random
from PIL import Image

def stamp():
	# Our timestamp.  Just making it easy.
	return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))

def getSQLite3():
	# Opens the DB, creates if it does not exist.
	dbName = picpieDir + '/hash_list.db'
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

def setResolution():
	global screenResolution
	#screenResolution = subprocess.check_output("fbset -s | grep '^mode' | sed 's/\"//g' | awk '{ print $2 }'", shell=True).rstrip()
	screenResolution = '1920x1080'	#assume 1080p
	print stamp() + " - Found resolution: " + screenResolution
	return

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
	if debug:
		print ""
		print stamp() + " - Resizing " + currentFile
	image = PM.Image(currentFile)
	image.resize(screenResolution)
	image.write(newFName)
	return

def rotateImage(newFName):
	if debug:
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

def processFile(db, storagePath, inboundFilePath, currentFile):
	global fileCount
	fileName, fileExt = os.path.splitext(currentFile)
	filePath, fileBase = os.path.split(fileName)
	tmpName = tmpPath + "/" + fileBase + fileExt
	newFName = storagePath + "/" + fileBase + fileExt

	if (not hashExistsInDB(db, currentFile) and
		not fileExistsInDB(db,currentFile) and
		getHashFromFile(currentFile) != getHashFromDestination(db, newFName)
		):
		print stamp() + " - Processing " + currentFile,
		if os.path.isfile(newFName):
			newFName = incrementFile(newFName)
		ext = fileExt[1:].lower()
	
		if ext == "jpg" or ext == "jpeg":
			resizeImage(currentFile, tmpName)
			rotateImage(tmpName)
		elif ext == "gif":
			if not animated:
				#We're only resizing and rotating if it's not animated.
				#If it's animated, someone should have already oriented and resized it properly
				resizeImage(currentFile, tmpName)
				rotateImage(tmpName)
		elif ext == "png":
			resizeImage(currentFile, tmpName)
			rotateImage(tmpName)
		elif ext == "tif" or ext == "tiff":
			resizeImage(currentFile, tmpName)
			rotateImage(tmpName)
		elif ext == "bmp":
			resizeImage(currentFile, tmpName)
			rotateImage(tmpName)
		elif ext == "mkv":
			shutil.copy2(currentFile,tmpName)
		else:
			print " - Skipped."
			return
		shutil.move(tmpName,newFName)
		fileCount += 1
		print stamp() + ' - File count: ' + str(fileCount)
	else:
		print stamp() + " - Skipping: " + currentFile
		if debug:
			print stamp() + " - File exists in database: " + newFName

	# Add hash to db
	status = addHash(db, currentFile, newFName)
	if debug:
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
	status = subprocess.call('rsync -av --itemize-changes --delete-before picpie@scheels.dyndns.org:/home/picpie/picpie/ {} >{} 2>&1'.format(inboundFilePath, picpieDir + "/rsync.log"), shell=True)
	print stamp() + " - Syncing complete."
	times['processing'] = time.time()
	if status:
		print stamp() + " - Error syncing files.  Check log file: " + storagePath + "/rsync.log"
	for root, dir, files in os.walk(inboundFilePath):
		for fname in files:
			currentFile = root + "/" + fname
			processFile(db, storagePath, inboundFilePath, currentFile)
	return

def runSlideShow():
	while True:
		if os.listdir(storagePath) == []:
			print stamp() + " - No files in " + storagePath
			time.sleep(1)
		else:
			fileName = random.choice(os.listdir(storagePath))
			ext = os.path.splitext(fileName)[1][1:].lower()
			fullFileName = storagePath + "/" + fileName
			if os.path.isfile(fullFileName):
				print stamp() + " - Displaying: " + fullFileName
				if ext in picExts:
					#fbiCmd = ['sudo','fbi','--noverbose','-T','1','-a','-1','-t',str(sleepDuration + 10),fullFileName]
					fbiCmd = 'sudo fbi -T 1 -a -1 -t {} --noverbose {}'.format(sleepDuration + 10, fullFileName)
					#import pdb ; pdb.set_trace()
					status = subprocess.call(fbiCmd, stdout=None, stderr=None, shell=True)
					print stamp() + "fbi exit status: " + str(status)
					time.sleep(sleepDuration)
				elif ext in vidExts:
					omxCmd = 'omxplayer {}'.format(fullFileName)
	return

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
	setResolution()
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
			if debug:
				print stamp() + " - Cleaning up from missing file: " + filename
			cur.execute('DELETE FROM hashes WHERE old_filename = ?',(filename,))
	return

def checkResized(db):
	times['checkResized'] = time.time()
	exceptions = ('hash_list.db','rsync.log','bin')
	for filename in os.listdir(storagePath):
		if filename not in exceptions:
			filename = storagePath + "/" + filename
			oldFileName = getOldFileName(db,filename)
			if not oldFileName or not os.path.isfile(oldFileName):
				print stamp() + " - Deleting: " + filename
				os.remove(filename)
	return

def countFiles():
	count = 0
	fileList = os.listdir(storagePath)
	if fileList != []:
		for fileName in fileList:
			count += 1
	return count

debug = True
times = {'program start':time.time(),}
picpieDir = "/home/pi/sda1/picpie"
storagePath = picpieDir + "/storage"
inboundFilePath = picpieDir + "/inbound"
tmpPath = picpieDir + "/tmp"
picExts = ('jpg','jpeg','tif','tiff','gif','png','bmp')
vidExts = ('wmv','mpg2','mpg4','mpg')
fileCount = countFiles()

if not os.path.isdir(picpieDir):
	os.mkdir(picpieDir)
if not os.path.isdir(storagePath):
	os.mkdir(storagePath)
if not os.path.isdir(inboundFilePath):
	os.mkdir(inboundFilePath)
if not os.path.isdir(tmpPath):
	os.mkdir(tmpPath)
sleepDuration = 5

if len(sys.argv) > 1 and sys.argv[1] == 'refresh':
	refreshFiles()
else:
	runSlideShow()

times['Complete'] = time.time()
