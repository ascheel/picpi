#picpi2

from __future__ import print_function
from __future__ import division

import pygame
import os
import sys
import dropbox
import sqlite3
import time
import arrow
import shutil
from PIL import Image
import PIL.ExifTags
import pyexiv2
import random
import signal

if sys.version_info[0] == 2:
	import ConfigParser
if sys.version_info[0] == 3:
	import configparser

"""
Notes:
Requires pyexiv2, dropbox, pygame

Callable from outside of the class:
slideshow()			# Runs slideshow
get_new_files()		# Retrieves new files from remote source
verify_db()			# Verifies current contents of DB to make sure they match remote, inbound, and storage
delete_old()		# Deletes files locally that are no longer present on remote side
wipe()				# Wipes entire setup except for config file.  Deletion of config must be done manually.
print_config()		# Prints out current configuration details.
clear_blacklist()	# Sets all blacklist flags in the database to 0
clear_log()			# Wipe contents of log file.  Need to introduce log rotations.
get_processes()		# See if there are any existing running processes that can conflict
check_integrity()	# Attempt to verify the integrity of images.
"""

def signal_handler(signal, frame):
	print('ctrl-c detected.')
	sys.exit(1)

signal.signal(signal.SIGINT, signal_handler)

class picpi(object):
	PID = os.getpid()
	config_file = os.path.expanduser('~') + '/.picpi.conf'
	APP_KEY = 'xe0mrs40eqfvcsj'
	APP_SECRET = '0tgeubc7ujjlo6t'
	debug = 0
	job = None
	silent = False
	SAFE_PROCESSES = ('status','wipe','reset','clear_log','clear_blacklist','print_config','config')


	def __init__(self, job, config=None):
		self.time_list = {}
		self.time_list['start'] = time.gmtime()
		# Set up the config
		if config != None:
			self.config_file = config

		print('Initializing parser')
		self.config = ConfigParser.ConfigParser()
		print('Initializing parser')
		self.config.read(self.config_file)

		changes_made = False
		if not self.config.has_section('Main'):
			self.config.add_section('Main')
			changes_made = True

		#self.configMain = self.config.items('Main')
		if not self.config.has_option('Main','basedir'):
			print('********************************************************************************')
			print('The Base Directory is the directory which all others are based off of.')
			print('Inbound files and resized files will all be stored in this directory.')
			print('The default is the current directory (' + os.getcwd() + ').\n')
			tmp = raw_input('What Base Directory would you like to use?  <Enter> for default:  ')
			if tmp != '':
				self.basedir = tmp
			else:
				self.basedir = os.getcwd()
			self.config.set('Main','basedir',self.basedir)
			changes_made = True
		else:
			self.basedir = self.config.get('Main','basedir')

		if not self.config.has_option('Main','debug'):
			self.debug = 0
			self.config.set('Main','debug',str(self.debug))
			changes_made = True
		else:
			self.debug = int(self.config.get('Main','debug'))
		self.log('Setting debug: ' + str(self.debug))

		self.log('Setting job: ' + str(job),2)
		self.set_job(job)

		self.inbound_path = self.basedir + '/inbound'
		self.log('Setting inbound path: ' + self.inbound_path)
		self.storage_path = self.basedir + '/storage'
		self.log('Setting storage path: ' + self.storage_path)

		if not self.config.has_option('Main','pic_exts'):
			self.pic_exts = ('jpg','jpeg','tif','tiff','gif','png','bmp')
			self.config.set('Main','pic_exts',','.join(self.pic_exts))
			changes_made = True
		else:
			self.pic_exts = self.config.get('Main','pic_exts').split(',')
		self.log('Setting pic_exts: ' + repr(self.pic_exts))

		if not self.config.has_option('Main','vid_exts'):
			self.vid_exts = ('wmv','mpg2','mpg4','mpg','mkv')
			self.config.set('Main','vid_exts',','.join(self.vid_exts))
			changes_made = True
		else:
			self.vid_exts = self.config.get('Main','vid_exts').split(',')
		self.log('Setting vid_exts: ' + repr(self.vid_exts))

		if not self.config.has_option('Main','picture_duration'):
			self.picture_duration = 300
			self.config.set('Main','picture_duration',str(self.picture_duration))
			changes_made = True
		else:
			self.picture_duration = int(self.config.get('Main','picture_duration'))
		self.log('Setting picture_duration: ' + repr(self.picture_duration))

		if not self.config.has_option('Main','screen_resolution'):
			self.screen_resolution = self.get_resolution()
			self.config.set('Main','screen_resolution',str(self.screen_resolution[0]) + 'x' + str(self.screen_resolution[1]))
			changes_made = True
		else:
			self.screen_resolution = (int(self.config.get('Main','screen_resolution').split('x')[0]),int(self.config.get('Main','screen_resolution').split('x')[1]))
		self.log('Setting screen_resolution: ' + repr(self.screen_resolution))

		if not self.config.has_option('Main','dropbox_access_token'):
			self.log('No dropbox_access_token')
			self.dropbox_access_token = raw_input('If you have a Dropbox Access Token, enter it here, otherwise just hit <ENTER>: ').strip()
			self.config.set('Main','dropbox_access_token',self.dropbox_access_token)
			while self.config.get('Main','dropbox_access_token') == '':
				flow = dropbox.client.DropboxOAuth2FlowNoRedirect(self.APP_KEY, self.APP_SECRET)
				auth_url = flow.start()
				print('')
				print('Dropbox initialization.')
				print('For this step, you must specifically grant this application access to your Dropbox account.')
				print('This application only reads files from the directory in specified in the \'basedir\' option.')
				print('    a) Copy and paste this URL into a browser:\n       ' + auth_url)
				print('    b) Click \'Allow\'.  You may be required to log into your DropBox account, first.')
				auth_code = raw_input('    c) Copy and Paste the Authorization Code here: ').strip()
				try:
					self.dropbox_access_token = flow.finish(auth_code)[0]
				except dropbox.rest.ErrorResponse:
					print('')
					print('     **************************************************')
					print('     * Invalid authorization code.  Please try again. *')
					print('     **************************************************')
					self.dropbox_access_token = ''
					continue
				try:
					client = dropbox.client.DropboxClient(self.dropbox_access_token)
					print('Successfully obtained access token: ' + self.dropbox_access_token)
					changes_made = True
					self.config.set('Main','dropbox_access_token',self.dropbox_access_token)
				except dropbox.rest.ErrorResponse:
					print('Failed.  Invalid access token.  Please try again.')
					self.dropbox_access_token = None
		else:
			self.dropbox_access_token = self.config.get('Main','dropbox_access_token')
		self.log('Setting dropbox_access_token: <redacted>')

		if not self.config.has_option('Main','dropbox_base_dir'):
			self.dropbox_base_dir = '/'
			self.config.set('Main','dropbox_base_dir',self.dropbox_base_dir)
			changes_made = True
		else:
			self.dropbox_base_dir = self.config.get('Main','dropbox_base_dir')
		self.log('Setting dropbox_base_dir: ' + repr(self.dropbox_base_dir))

		if not self.config.has_option('Main','transition_duration'):
			self.transition_duration = 10
			self.config.set('Main','transition_duration',str(self.transition_duration))
			changes_made = True
		else:
			self.transition_duration = self.config.getint('Main','transition_duration')
		self.log('Setting transition_duration: ' + str(self.transition_duration))

		if changes_made:
			self.log('Writing changes to log file: ' + self.config_file)
			with open(self.config_file, 'w') as configwrite:
				self.config.write(configwrite)

		# Prep and/or open the database
		self.dbfile = self.basedir + '/picpi.db'
		self.log('Opening sqlite3 database file: ' + self.dbfile)
		self.db = sqlite3.connect(self.dbfile)
		self.dbox = dropbox.client.DropboxClient(self.dropbox_access_token)
		self.cur = self.db.cursor()

		tableName = 'files'
		column_text = 'remote_filename TEXT UNIQUE, inbound_filename TEXT UNIQUE, storage_filename TEXT UNIQUE,revision INTEGER, bytes INTEGER, date_synced REAL, modified TEXT, blacklisted INTEGER, corrupt INTEGER'
		self.cur.execute('CREATE TABLE IF NOT EXISTS {} ({})'.format(tableName, column_text))
		self.log('Creating table \'files\'.')

		tableName = 'directories'
		column_text = 'remote_dir TEXT UNIQUE, inbound_dir TEXT UNIQUE, storage_dir TEXT, hash TEXT, date_added REAL'
		self.cur.execute('CREATE TABLE IF NOT EXISTS {} ({})'.format(tableName, column_text))
		self.log('Creating table \'directories\'')

		self.db.commit()
		self.log('Committing.')

		# Create directories if they do not exist.
		for path in (self.inbound_path, self.storage_path):
			if not os.path.isdir(path):
				self.log('Creating directory: ' + repr(path))
				os.makedirs(path)

	def __del__(self):
		self.time_list['end'] = time.gmtime()
		if self.job not in self.SAFE_PROCESSES:
			self.remove_lock()
		self.show_times()

	def delete_old(self):
		self.log('Checking for deleted files.')
		self.time_list['delete_old'] = time.gmtime()
		for dir in os.walk(self.inbound_path):
			for filename in dir[2]:
				inboundFilename = dir[0] + '/' + filename

				self.log('Checking: ' + inboundFilename,1)
				remoteFilename = self.db.cursor().execute('SELECT remote_filename FROM files WHERE inbound_filename = (?)',(inboundFilename,)).fetchall()
				if remoteFilename == []:
					self.log('File: ' + inboundFilename + ' does not exist in database.  You\'ll probably want to figure out why.')
					continue
				remoteFilename = remoteFilename[0][0]

				self.log('Verifying: ' + remoteFilename,1)
				try:
					metadata = self.dbox.metadata(remoteFilename,1)
					if 'is_deleted' in metadata:
						if metadata['is_deleted'] == True:
							self.log('Deleting local: ' + remoteFilename,1)
							delete_file(remoteFilename)
						else:
							self.log('Keeping local: ' + remoteFilename,2)
				except dropbox.rest.ErrorResponse as e:
					if e.status == 404:
						self.log('Deleting local: ' + remoteFilename,1)
						delete_file(remoteFilename)
					else:
						self.log('Keeping local: ' + remoteFilename,2)

	def verify_db(self):
		self.log('Retrieving full file list.')
		self.time_list['verify_db'] = time.gmtime()
		self.cur.execute('SELECT remote_filename, inbound_filename, storage_filename FROM files')
		filelist = self.cur.fetchall()
		for remote_filename, inbound_filename, storage_filename in filelist:
			delete_it = False
			if remote_filename:
				self.log('Checking Dropbox for: ' + remote_filename,1)
				try:
					metadata = self.dbox.metadata(remote_filename, include_deleted=True)
					if 'is_deleted' in metadata:
						if metadata['is_deleted'] == True:
							if os.path.isfile(inbound_filename) or os.path.isfile(storage_filename):
								self.delete_file(remote_filename)
				except dropbox.rest.ErrorResponse as e:
					if e.status == 404:
						if os.path.isfile(inbound_filename):
							delete_file(remote_filename)
				
	def delete_file(self, remote_filename):
		self.cur.execute('SELECT inbound_filename, storage_filename FROM files WHERE remote_filename = (?)',(remote_filename))
		inbound_filename, storage_filename = self.cur.fetchall()
		if inbound_filename and os.path.isfile(inbound_filename):
			self.log('Deleting removed file: ' + inbound_filename,1)
			os.remove(inbound_filename)
		if storage_filename and os.path.isfile(storage_filename):
			self.log('Deleting removed file: ' + storage_filename,1)
			os.remove(storage_filename)
		self.cur.execute('DELETE FROM files WHERE remote_filename = (?)',(remote_filename,))
		self.db.commit()

	def get_new_files(self):
		self.log('Syncing from mothership.')
		self.time_list['get_new_files'] = time.gmtime()
		if not self.dbox.metadata(self.dropbox_base_dir)['is_dir']:
			self.log('Dropbox base dir is not a directory.')
			clean_up(1)
		self.file_count = self.get_dbox_file_count()
		self.dropboxWalk(self.dropbox_base_dir)
		self.log('Syncing complete.')

	def dropboxWalk(self, path, current_count=0):
		try:
			data = self.dbox.metadata(path)
		except dropbox.rest.ErrorResponse as e:
			if e.status == 503:
				self.log('Server error: ' + e.reason)
				self.log('Try again later.')
				self.clean_up(1)
		
		if data['is_dir']:
			self.log(data['path'] + ' is a directory',1)
			inboundDirname = str(self.inbound_path + '/' + path.lower()).replace('//','/')
			self.log('inboundDirname: ' + inboundDirname,1)
			if not os.path.exists(inboundDirname):
				self.log('Creating directory: ' + inboundDirname)
				os.makedirs(inboundDirname)
				self.store_dir(path, data)
			for entry in data['contents']:
				current_count = self.dropboxWalk(entry['path'],current_count)
		else:
			tmp = str(self.inbound_path + '/' + data['path']).lower().replace('//','/')
			tmp = os.path.split(tmp)[0]
			if not os.path.exists(tmp):
				self.log('Creating path: ' + repr(tmp),1)
				os.makedirs(tmp)
			self.get_dropbox_file(data['path'].lower())
			if os.path.splitext(data['path'].lower())[1][1:] in self.pic_exts:
				current_count += 1
				remaining = self.file_count - current_count
				self.log('Files remaining to process: ' + str(remaining),1)
		return current_count

	def store_file(self, remoteFilename, metadata):
		storageFilename = self.storage_path + '/' + remoteFilename
		storageFilename = storageFilename.replace('//','/')
		inboundFilename = self.inbound_path + '/' + remoteFilename
		inboundFilename = inboundFilename.replace('//','/')

		self.cur.execute('SELECT * FROM files WHERE remote_filename = (?)',(remoteFilename,))
		tmp = self.cur.fetchall()
		if tmp != []:
			self.cur.execute('DELETE FROM files WHERE remote_filename = (?)',(remoteFilename,))
			self.db.commit()

		self.cur.execute('INSERT INTO files VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)', (remoteFilename, inboundFilename, storageFilename ,metadata['revision'], metadata['bytes'], self.stamp(), metadata['client_mtime'].replace('+0000',''), 0, 0))
		self.db.commit()
		return

	def store_dir(self, remote_dir, metadata):
		self.cur.execute('INSERT INTO directories VALUES (?, ?, ?, ?, ?)', (remote_dir, self.inbound_path + '/' + remote_dir, self.storage_path + '/' + remote_dir, metadata['hash'], self.stamp()))
		self.db.commit()

	def get_revision(self, filename):
		self.cur.execute('SELECT revision FROM files WHERE remote_filename = (?)',(filename,))
		results = self.cur.fetchall()
		if not results:
			return None
		else:
			return results[0][0]

	def process_image(self, remoteFilename):
		self.log('Processing file: ' + remoteFilename, 1)
		ext = os.path.splitext(remoteFilename)[1][1:].lower()
		file_base = os.path.split(remoteFilename)[1]

		inboundFilename = self.strip_double_slash(self.inbound_path + '/' + remoteFilename)
		storageFilename = self.strip_double_slash(self.storage_path + '/' + remoteFilename)

		img = Image.open(inboundFilename)

		self.make_path(os.path.split(remoteFilename)[0])

		animated = False
		if ext in self.pic_exts:
			if ext == 'gif':
				try:
					img.seek(1)
				except EOFError:
					animated = False
				else:
					animated = True
				self.log('animated=' + repr(animated),1)
			if animated == False:
				img = self.rotate_image(img)
				img2 = self.resize_image(img)
				if img2:
					img = img2
					img.save(storageFilename)
					self.copy_metadata(inboundFilename, storageFilename)
				else:
					self.blacklist_pic(inboundFilename)


	def copy_metadata(self,src_file,dest_file):
		self.log('Copying exif data.',2)
		#Get Source metadata
		srcmeta = pyexiv2.ImageMetadata(src_file)
		srcmeta.read()

		#Get Destination metadata
		destmeta = pyexiv2.ImageMetadata(dest_file)
		destmeta.read()

		#Fix Orientation
		key = 'Exif.Image.Orientation'
		value = 1
		srcmeta[key] = pyexiv2.ExifTag(key, value)

		#Copy it
		srcmeta.copy(destmeta)
		destmeta.write()

	def rotate_image(self,img):
		self.log('Rotating image.',2)
		exif = {
			PIL.ExifTags.TAGS[k]: v
			for k, v in img._getexif().items()
			if k in PIL.ExifTags.TAGS
		}
		self.log('EXIF Tags: ' + repr(exif),3)
		if 'Orientation' in exif:
			o = exif['Orientation']
			self.log('Current orientation: ' + str(o),2)
			if o not in (3, 6, 8):
				self.log('Not rotating.',1)
				return img
			if o == 3:
				rotatedegrees = 180
			if o == 6:
				rotatedegrees = 270
			if o == 8:
				rotatedegrees = 90
			self.log('Rotating ' + str(rotatedegrees) + ' degrees CCW', 1)
			img = img.rotate(rotatedegrees)
		return img

	def resize_image(self, img):
		self.log('Resizing to: ' + repr(self.screen_resolution),2)
		try:
			img.thumbnail((self.screen_resolution[0], self.screen_resolution[1]), Image.ANTIALIAS)
		except IOError:
			return None
		fill_black = True
		if fill_black:
			self.log('Adding black bars.',2)
			black = Image.new('RGB', self.screen_resolution, 'black')
			black.paste(img, self.top_left(img))
		return black
		
	def top_left(self, img):
		top_left_x = int(self.screen_resolution[0] / 2) - int(img.size[0] / 2)
		top_left_y = int(self.screen_resolution[1] / 2) - int(img.size[1] / 2)
		return top_left_x, top_left_y

	def make_path(self,path_to_create):
		path_to_create = path_to_create.lstrip('/')
		for x in range(len(path_to_create.split('/'))):
			path = '/'.join(path_to_create.split('/')[0:x+1])

			if not os.path.exists(self.storage_path + '/' + path):
				self.log('Creating path: ' + repr(self.storage_path + '/' + path))
				os.mkdir(self.storage_path + '/' + path)
			if not os.path.exists(self.inbound_path + '/' + path):
				self.log('Creating path: ' + repr(self.inbound_path + '/' + path))
				os.mkdir(self.inbound_path + '/' + path)
		return

	def strip_double_slash(self,filename):
		while '//' in filename:
			filename = filename.replace('//','/')
		return filename

	def get_dropbox_file(self, remoteFilename):
		self.log('Retrieving file: ' + str(remoteFilename),1)
		inboundFilename = str(self.inbound_path + '/' + remoteFilename).replace('//','/')
		tryagain = True
		while tryagain:
			try:
				metadata = self.dbox.metadata(remoteFilename)
				tryagain = False
			except dropbox.rest.ErrorResponse as e:
				if e.status == 503:
					self.log('Server error.  Trying again.')
					time.sleep(5)
					self.log('Error: ' + repr(e))


		self.log('Database revision: ' + str(self.get_revision(remoteFilename)) + ' - ' + str(metadata['revision']) + ' :Dropbox revision', 2)
		#if '20151014_081417' in inboundFilename:
			#import pdb; pdb.set_trace()
		if not os.path.exists(inboundFilename) or metadata['revision'] != self.get_revision(remoteFilename):
			if os.path.splitext(inboundFilename)[1][1:].lower() not in self.pic_exts:
				self.log('Skipping:    ' + remoteFilename + '. File is not an image.')
				return
			self.log('Downloading: ' + remoteFilename)
			
			tryagain = True
			try_loop_count = 0
			while tryagain:
				try_loop_count += 1
				if try_loop_count >= 5:
					tryagain = False
				try:
					f = self.dbox.get_file(remoteFilename)
					tryagain = False
				except dropbox.rest.ErrorResponse as e:
					if e.status == 500:
						self.log('Attempt ' + str(try_loop_count) + '. Server error.  Retrying after 5 seconds.')
						time.sleep(5)
						self.log('Error: ' + repr(e))

			startTime = int(round(time.time() * 1000))
			self.log('start time: ' + str(startTime),1)
			with open(inboundFilename, 'wb') as save:
				self.log('Copying file.',2)
				save.write(f.read())
				#try:
				#except:
					#import pdb; pdb.set_trace()

			#duration = int(round(time.time() * 1000)) - startTime
			duration = int(round(time.time() * 1000)) - startTime
			if duration == 0:
				duration = 1
			self.log('duration: ' + str(duration) + 'ms',1)
			bps = os.path.getsize(inboundFilename) / duration

			# Set modified time to that on Dropbox.  'modified' time is garbage.
			newTime = arrow.get(metadata['client_mtime'].replace('+0000',''),'ddd, D MMM YYYY HH:mm:ss').to('local').timestamp
			os.utime(inboundFilename,(newTime,newTime))

			self.log('Speed: ' + str(round(bps/1024,2)) + ' MB/s',1)

			self.process_image(remoteFilename)
			self.store_file(remoteFilename, metadata)
		else:
			self.log('Skipping:    ' + remoteFilename + '. File already exists.',1)

	def clean_up(self, status=0):
		if self.job not in self.SAFE_PROCESSES:
			self.remove_lock()
		pygame.quit()
		sys.exit(status)

	def stamp(self):
		return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))

	def log(self, msg, debugLevel=0):
		logfile = self.basedir + '/picpi.log'
		if self.debug >= debugLevel:
			if debugLevel > 0:
				debugMsg = 'DEBUG' + str(debugLevel)
			else:
				debugMsg = 'INFO'
			
			newMsg = '{} - {:5} - {:6} - {:10} - {}'.format(self.stamp(),self.PID,debugMsg,self.job,msg)
			if not self.silent:
				print(newMsg)
			with open(logfile, 'a') as f:
				print(newMsg,file=f)

	def print_config(self):
		print('basedir               ' + str(self.basedir))
		print('inbound_path          ' + str(self.inbound_path))
		print('storage_path          ' + str(self.storage_path))
		if self.dropbox_access_token:
			print('dropbox_access_token  <redacted>')
		else:
			print('dropbox_access_token  None')
		print('screen_resolution     ' + repr(self.screen_resolution))
		print('pic_exts              ' + repr(self.pic_exts))
		print('vid_exts              ' + repr(self.vid_exts))
		print('transition_duration   ' + str(self.transition_duration))
		print('picture_duration      ' + str(self.picture_duration))
		print('dropbox_base_dir      ' + str(self.dropbox_base_dir))
		print('debug                 ' + str(self.debug))

	def get_resolution(self):
		self.available_modes = []
		pygame.init()
		modes = None
		try:
			modes = pygame.display.list_modes()
			for mode in modes:
				if pygame.display.mode_ok(mode):
					self.available_modes.append(mode)
		except pygame.error as e:
			self.log('pygame.error: ' + repr(e.args[0]))
			self.log('Creating modes manually.')
			modes = [
				(1026,576),(1152,648),(1280,720),(1366,768),(1600,900),(1920,1080),(2560,1440),(3840,2160),
				(1280,800),(1440,900),(1680,1050),(1920,1200),(2560,1600),
				(640,480),(800,600),(960,720),(1024,768),(1280,960),(1400,1050),(1440,1080),(1600,1200),(1856,1392),(1920,1440),(2048,1536),
				]
			self.available_modes = modes
		pygame.quit()
		self.log('modes: ' + repr(modes))
		print('Choose a resolution')
		modecount = 0
		for mode in self.available_modes:
			print(str(modecount + 1) + ': ' + str(mode[0]) + 'x' + str(mode[1]))
			modecount += 1
		choice = int(raw_input('Choice: '))
		choice -= 1
		return self.available_modes[choice]

	def wipe(self):
		self.log('Wiping.')
		self.log('Deleting database file: ' + self.dbfile,1)
		os.remove(self.dbfile)
		self.log('Deleting inbound directory: ' + self.inbound_path,1)
		shutil.rmtree(self.inbound_path)
		self.log('Deleting storage directory: ' + self.storage_path,1)
		shutil.rmtree(self.storage_path)

	def check_lock(self):
		lockfile = self.basedir + '/picpi.' + self.job + '.pid'
		self.log('Checking for lock file: ' + lockfile,1)
		if os.path.exists(lockfile):
			with open(lockfile) as pid_file:
				stored_pid = pid_file.read()
			proc_file_name = '/proc/' + stored_pid + '/cmdline'
			if os.path.isfile(proc_file_name):
				with open(proc_file_name) as proc_file:
					cmd = proc_file.read().split('\x00')
				if len(cmd) >= 2:
					if os.path.basename(cmd[0]) == 'python' and os.path.basename(cmd[1]) == os.path.basename(__file__):
						self.log('{} already in progress on PID {}.  Exiting.'.format(self.job,stored_pid))
						clean_up(1)
			os.remove(lockfile)
		with open(lockfile,'w') as pid_file:
			self.log('Creating {} lock file.'.format(self.job))
			pid_file.write(str(os.getpid()))

	def remove_lock(self):
		lockfile = self.basedir + '/picpi.' + self.job + '.pid'
		if os.path.isfile(lockfile):
			self.log('Removing lock file: {}'.format(lockfile),1)
			os.remove(lockfile)
		else:
			self.log('No lock file to remove: {}'.format(lockfile),1)

	def get_processes(self):
		process_list = ('slideshow','wipe','refresh','verify_db','delete_old','config',)
		pid_list = {}
		for process in process_list:
			self.log('Checking for running process \'' + process + '\'.',2)
			lockfile = self.basedir + '/picpi.' + process + '.pid'
			self.log('Lock file: ' + lockfile,2)
			if os.path.exists(lockfile):
				with open(lockfile) as pid_file:
					stored_pid = pid_file.read()
					self.log('stored_pid: ' + repr(stored_pid),2)
				proc_file_name = '/proc/' + stored_pid + '/cmdline'
				self.log('proc_file_name: ' + proc_file_name,2)
				if os.path.isfile(proc_file_name):
					self.log(proc_file_name + ' exists.',2)
					with open(proc_file_name) as proc_file:
						cmd = proc_file.read().split('\x00')
						self.log('cmd: ' + repr(cmd),2)
					if len(cmd) >= 2:
						if os.path.basename(cmd[0]) == 'python':
							got_process = False
							for arg in cmd[2:]:
								self.log('Checking for arg: ' + arg,2)
								if arg == process:
									self.log('arg exists, setting True.',2)
									got_process = True
								else:
									self.log('arg {} != process {}'.format(arg,process),2)
							if got_process:
								#self.log('Process \'{}\' exists on pid {}.'.format(process,stored_pid))
								self.log('Appending ' + process + 'to list.',2)
								pid_list[process] = stored_pid
		for item in pid_list:
			self.log('Process \'{}\' exists on pid {}.'.format(item,pid_list[item]))

	def slideshow(self):
		self.log('Starting slideshow.')
		self.time_list['slideshow'] = time.gmtime()
		drivers = ('directfb','fbcon','svgalib','x11','dga','ggi','vg1','aalib')
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

		if pygame.display.mode_ok(self.screen_resolution):
			if os.getenv('DISPLAY') == None:
				self.log('Setting resolution: ' + repr(self.screen_resolution))
				self.screen = pygame.display.set_mode(self.screen_resolution,pygame.FULLSCREEN)
			else:
				self.log('Setting resolution default: ' + repr(self.screen_resolution))
				self.screen = pygame.display.set_mode(self.screen_resolution)
		else:
			self.log('Oh crap.  No video modes available.')

		self.log('Disappearing the mouse cursor.',2)
		pygame.mouse.set_visible(False)

		# Set black background
		self.screen.fill(pygame.Color(0,0,0))
		pygame.display.update()

		# Loop until forever
		first_iteration = True
		self.log('Starting slideshow')
		while 1:
			imagelist = self.get_rowids()
			storage_filename = None
			# Loop until all images have been viewed (imagelist = 0)
			wait_counter = 0
			while len(imagelist) == 0:
				wait_counter += 1
				if wait_counter > 10:
					break
				self.log('No files to display.  Show placeholder.')
				time_between_event_checks = 250
				self.wait_page('nofiles')
				self.check_events()
				pygame.time.wait(time_between_event_checks)

			while len(imagelist) > 0:
				time_between_event_checks = 250
				self.log('picture duration: ' + str(self.picture_duration),1)
				start_time = time.time()
				current_time = start_time
				while current_time - start_time < self.picture_duration and not first_iteration:
					self.log('Time until next pic: ' + self.timeify(int(self.picture_duration - (current_time - start_time ))),3)
					current_time = time.time()
					for x in range(int(1000 / time_between_event_checks)):
						pygame.time.wait(time_between_event_checks)
						next_pic = self.check_events(self.current_storage_filename)
						if next_pic:
							transition_duration = 3
							start_time = time.time() - self.picture_duration
							self.log(self.picture_duration)
							break
				first_iteration = False

				x = random.randrange(0,len(imagelist))	# Pick random spot in list
				rowid = imagelist[x]					# Get the row id from list
				del imagelist[x]						# Delete image from list so it's only viewed once

				# Get the filename using rowid
				self.cur.execute('SELECT storage_filename FROM files WHERE rowid = {}'.format(str(rowid)))
				self.current_storage_filename = self.cur.fetchall()
				if self.current_storage_filename != []:
					self.current_storage_filename = self.current_storage_filename[0][0]
				self.transition(self.current_storage_filename, 'fade', self.transition_duration)

	def timeify(self,seconds):
		self.log('timeify {} seconds'.format(seconds),3)
		seconds = int(seconds)
		timeified = None
		
		days = int(seconds / 86400)
		seconds %= 86400

		hours = int(seconds / 3600)
		seconds %= 3600

		minutes = int(seconds / 60)
		seconds %= 60
		timeified = '{:0>2}d:{:0>2}h:{:0>2}m:{:0>2}s'.format(days,hours,minutes,seconds)
		return timeified

	def transition(self,storage_filename,transition_type,transition_duration=5):
		self.log('transition: ' + storage_filename + ' for ' + str(transition_duration) + 'sec',1)
		if transition_type == 'fade':
			MAX_ALPHA = 255
			MIN_ALPHA = 0
			start = pygame.time.get_ticks()
			self.log('Opening image: ' + str(storage_filename),2)
			try:
				img = pygame.image.load(storage_filename).convert()
			except:
				self.log('Marking image corrupt.')
				self.corrupt_pic(storage_filename)
				return

			self.log('Starting ticks: ' + str(start),3)
			while True:
				self.log('Checking events.',3)
				self.check_events()
				now = pygame.time.get_ticks()
				self.log('Now ticks: ' + str(now),3)
				pygame.time.wait(250)
				if ((now - start)/1000) > transition_duration:
					self.log('Setting full alpha for final transition frame.',2)
					img.set_alpha(MAX_ALPHA)
					self.screen.blit(img,(0,0))
					pygame.display.update()
					self.log('Breaking because it\'s past duration of ' + str(transition_duration) + 'sec.',1)
					break
				alpha = MIN_ALPHA
				if now - start > 0:
					self.log('Time until next image: ' + repr(round(transition_duration - ((now - start) / 1000),2)),3)
					alpha = int(MAX_ALPHA / ((transition_duration * 1000) / (now - start)))
					self.log('New alpha: ' + str(alpha),2)
				img.set_alpha(alpha)
				self.screen.blit(img,(0,0))
				pygame.display.update()

	def check_events(self, filename=None):
		nextPic = False
		for e in pygame.event.get():
			if e.type == pygame.KEYDOWN:
				if e.key == pygame.K_SPACE:
					self.log('Advancing slideshow manually.',1)
					nextPic = True
				if e.key == pygame.K_BACKSPACE or e.key == pygame.K_DELETE:
					self.blacklist_pic(filename)
					nextPic = True
				if e.key == pygame.K_q:
					self.log('\'Q\' pressed.  Exiting application.')
					self.clean_up()
		return nextPic

	def blacklist_pic(self,storage_filename):
		self.log('Blacklisting: ' + storage_filename)
		self.cur.execute('UPDATE files SET blacklisted = 1 WHERE storage_filename = (?)',(storage_filename,))
		self.db.commit()

	def corrupt_pic(self,storage_filename):
		self.log('Marking corrupt: ' + storage_filename)
		self.cur.execute('UPDATE files SET corrupt = 1 WHERE storage_filename = (?)',(storage_filename,))
		self.db.commit()

	def clear_blacklist(self):
		self.log('Clearing all blacklist marks from database.')
		self.cur.execute('UPDATE files SET blacklisted = 0 WHERE blacklisted = 1')
		self.db.commit()

	def clear_corrupt(self):
		self.log('Clearing corrupt marks from database.')
		self.cur.execute('UPDATE files SET corrupt = 0 WHERE corrupt 0 1')
		self.db.commit()

	def wait_page(self,reason,message=None):
		pygame.font.init()
		if reason == 'nofiles':
			self.screen.convert()
			self.screen.fill((255,255,255))	#Give us some white
			font = pygame.font.Font(None, 36)
			text = font.render('No files to process.', 1, (10, 10, 10))
			textpos = text.get_rect()
			textpos.centerx = self.screen.get_rect().centerx
			textpos.centery = self.screen.get_rect().centery
			self.screen.blit(text, textpos)
			pygame.time.wait(1000)
			pygame.display.flip()

	def set_job(self,new_job):
		if self.job:
			if self.job not in self.SAFE_PROCESSES:
				self.remove_lock()
		self.job = new_job
		if self.job not in self.SAFE_PROCESSES:
			self.check_lock()

	def get_rowids(self):
		self.log('Getting new round of images.')
		self.cur.execute('SELECT rowid FROM files WHERE blacklisted = 0 AND corrupt = 0')
		rowids = self.cur.fetchall()
		rowids = [n for n, in rowids]
		self.log('rowids: ' + repr(rowids),3)
		return rowids

	def clear_log(self):
		os.remove(self.basedir + '/picpi.log')
		self.log('Clearing log file.')

	def check_integrity(self):
		self.log('Checking integrity.')
		self.time_list['check'] = time.gmtime()
		for root, dirs, files in os.walk(self.storage_path):
			self.log('Checking path: ' + repr(root))
			for filename in files:
				full_filename = root + '/' + filename
				self.log('  Testing file: ' + filename,1)
				try:
					img = Image.open(full_filename)
					img.verify()
				except:
					self.log('*** Unable to load file: ' + full_filename + '***')
				else:
					self.log('    File successfully tested.',1)
		self.log('Integrity check complete.')

	def test(self):
		return

	def get_dbox_file_count(self):
		file_count = self.count_dbox_files(self.dropbox_base_dir)		
		self.log('Files on Dropbox: ' + str(file_count),1)
		return file_count

	def count_dbox_files(self,path,file_count=0):
		data = self.dbox.metadata(path)
		
		if data['is_dir']:
			for entry in data['contents']:
				if entry['is_dir']:
					#self.log('Navigating ' + entry['path'] + ' Count: ' + str(file_count),1)
					file_count = self.count_dbox_files(entry['path'], file_count)
				else:
					ext = os.path.splitext(entry['path'])[1][1:].lower()
					if ext in self.pic_exts:
						file_count += 1
						self.log('{: >4} - {}'.format(file_count,entry['path']),2)
		return file_count

	def show_times(self):
		maxlen = 0
		maxdigits = 0
		for label in self.time_list:
			if len(label) > maxlen:
				maxlen = len(label)
		for label in self.time_list:
			time_string = time.strftime('%H:%M:%S',self.time_list[label])
			self.log('{{: <{}}} - {{}}'.format(maxlen).format(label,time_string))

