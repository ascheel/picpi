#!/usr/bin/python

import dropbox

client = dropbox.client.DropboxClient('71DSW28G7IQAAAAAAARG3Bcbq1EGC1Vc4TZrvD0omlbSXUdUMuCvWXzydDLVM02u')
metadata = client.metadata('/media/picpi/2015-09-06.Devils.Tower.Wyoming/IMG_1733.JPG')
print metadata
