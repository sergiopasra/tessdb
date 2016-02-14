# ----------------------------------------------------------------------
# Copyright (c) 2014 Rafael Gonzalez.
#
# See the LICENSE file for details
# ----------------------------------------------------------------------

#--------------------
# System wide imports
# -------------------

import os
import errno
import sys
import datetime
import json

# ---------------
# Twisted imports
# ---------------

from twisted.logger import Logger, LogLevel
from twisted.internet import reactor
from twisted.application.service import Service
from twisted.internet.defer import inlineCallbacks, returnValue

#--------------
# local imports
# -------------

from .logger import setLogLevel

# ----------------
# Module constants
# ----------------

# -----------------------
# Module global variables
# -----------------------

log = Logger(namespace='dbase')

class DBaseService(Service):


    def __init__(self, parent, options, **kargs):
        Service.__init__(self)
        self.parent   = parent
        self.options  = options
        self.paused   = False
        setLogLevel(namespace='dbase', levelStr=options['log_level'])
      
    #------------
    # Service API
    # ------------

    @inlineCallbacks
    def startService(self):
        if self.options['type'] == "sqlite3":
            from .sqlite3 import DBase
        else:
            msg = "No database driver found for '{0}'".format(self.options['type'])
            raise ImportError( msg )
        log.info("starting DBase Service")
        self.dbase    = DBase(self.options['connection_string'])
        yield self.dbase.schema(
            json_dir=self.options['json_dir'], 
            date_fmt=self.options['date_fmt'], 
            year_start=self.options['year_start'], 
            year_end=self.options['year_end'], 
            replace=True)
        Service.startService(self)
        log.info("Database operational.")
        self.later = reactor.callLater(2, self.writter)

    def stopService(self):
        self.dbase.pool.close()
        Service.stopService()
        log.info("Database stopped.")

    #---------------------
    # Extended Service API
    # --------------------

    def reloadService(self, new_options):
        setLogLevel(namespace='dbase', levelStr=new_options['log_level'])
        log.info("new log level is {lvl}", lvl=new_options['log_level'])

    def pauseService(self):
        log.info('TESS database writer paused')
        self.paused = True

    def resumeService(self):
        log.info('TESS database writer resumed')
        self.paused = False

    # --------------
    # Helper methods
    # ---------------
   
    @inlineCallbacks
    def writter(self):
        '''
        Periodic task that takes rows from the queues
        and update them to database
        '''
        if not self.paused:
            while len(self.parent.queue['tess_register']):
                row = self.parent.queue['tess_register'].popleft()
                yield self.dbase.register(row)
            while len(self.parent.queue['tess_readings']):
                row = self.parent.queue['tess_readings'].popleft()
                yield self.dbase.update(row)
        self.later = reactor.callLater(1,self.writter)
        

