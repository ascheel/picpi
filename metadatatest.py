#!/usr/bin/python

import dropbox

client = dropbox.client.DropboxClient(dropbox_access_token)
metadata = client.metadata('/media/picpi/2015-09-06.Devils.Tower.Wyoming/IMG_1733.JPG')
print metadata
