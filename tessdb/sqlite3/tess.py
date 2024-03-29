# -*- coding: utf-8 -*-

# ----------------------------------------------------------------------
# Copyright (c) 2014 Rafael Gonzalez.
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
# 
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
# LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
# WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
# ----------------------------------------------------------------------

#--------------------
# System wide imports
# -------------------

import os
import datetime

# ---------------
# Twisted imports
# ---------------

from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.internet.threads import deferToThread
from twisted.logger         import Logger

#--------------
# local imports
# -------------

# -- beware of absolute_import in Python 3 when doing import utils
import utils
from .utils import Table, fromJSON
from ..error import ReadingKeyError, ReadingTypeError

# ----------------
# Module Constants
# ----------------

# No pre-registerd instruments by default
DEFAULT_INSTRUMENT = []

# No predefined deployment of TESS instruments to Loacations
DEFAULT_DEPLOYMENT = []

# -----------------------
# Module Global Variables
# -----------------------

log = Logger(namespace='dbase')


# ------------------------
# Module Utility Functions
# ------------------------

def _populateRepl(transaction, rows):
    '''Dimension initial data loading (replace flavour)'''
    transaction.executemany(
        '''INSERT OR REPLACE INTO tess_t (
            tess_id,
            name,
            mac_address,
            calibration_k,
            calibrated_since,
            calibrated_until,
            calibrated_state,
            location_id
        ) VALUES (
            :tess_id,
            :name,
            :mac_address,
            :calibration_k,
            :calibrated_since,
            :calibrated_until,
            :calibrated_state,
            :location_id
        )
        ''', rows)

        
def _populateIgn(transaction, rows):
    '''Dimension initial data loading (ignore flavour)'''
    transaction.executemany(
        '''INSERT OR IGNORE INTO tess_t (
            tess_id,
            name,
            mac_address,
            calibration_k,
            calibrated_since,
            calibrated_until,
            calibrated_state,
            location_id
        ) VALUES (
            :tess_id,
            :name,
            :mac_address,
            :calibration_k,
            :calibrated_since,
            :calibrated_until,
            :calibrated_state,
            :location_id
        )
        ''', rows)


def _deployInstr(transaction, rows):
    '''Update location id of given TESS instruments'''
    transaction.executemany(
        '''UPDATE tess_t SET location_id = (
            SELECT location_id FROM location_t
            WHERE  location_t.site == :site
           )
           WHERE name == :name
        ''', rows)


def _updateCalibration(cursor, row):
    '''
    Updates Instrument calibration constant keeping its history
    row is a dictionary with at least the following keys: 'name', 'mac', 'calib'
    Returns a Deferred.
    '''
    row['eff_date']      = datetime.datetime.utcnow().strftime(utils.TSTAMP_FORMAT)
    row['exp_date']      = utils.INFINITE_TIME
    row['calib_expired'] = utils.EXPIRED
    row['calib_flag']    = utils.CURRENT

    cursor.execute(
        '''
        UPDATE tess_t SET calibrated_until = :eff_date, calibrated_state = :calib_expired
        WHERE mac_address == :mac AND calibrated_state == :calib_flag
        ''', row)
    cursor.execute(
        '''
        INSERT INTO tess_t (
            name,
            mac_address, 
            calibration_k,
            calibrated_since,
            calibrated_until,
            calibrated_state
        ) VALUES (
            :name,
            :mac,
            :calib,
            :eff_date,
            :exp_date,
            :calib_flag
        )
        ''',  row)

def _createIndices(cursor):
    '''
    Create table Indices
    '''
    cursor.execute("CREATE INDEX IF NOT EXISTS tess_name_i ON tess_t(name);")
    cursor.execute("CREATE INDEX IF NOT EXISTS tess_mac_i ON tess_t(mac_address);")


def _createViews(cursor):
    '''
    Create Views
    '''
    # This is the  outrigger to Location dimension
    cursor.execute(
        '''
        CREATE VIEW IF NOT EXISTS tess_v 
        AS SELECT
            tess_t.tess_id,
            tess_t.name,
            tess_t.mac_address,
            tess_t.calibration_k,
            tess_t.calibrated_since,
            tess_t.calibrated_until,
            tess_t.calibrated_state,
            location_t.contact_email,
            location_t.site,
            location_t.longitude,
            location_t.latitude,
            location_t.elevation,
            location_t.zipcode,
            location_t.location,
            location_t.province,
            location_t.country
        FROM tess_t JOIN location_t USING (location_id);
        '''
        )


# ============================================================================ #
#                              TESS INSTRUMENT TABLE (DIMENSION)
# ============================================================================ #

class TESS(Table):

    DEPL_FILE = 'tess_location.json'

    def __init__(self, pool, validate=False):
        Table.__init__(self, pool)
        self.resetCounters()

    def table(self):
        '''
        Create the SQLite Units table.
        Returns a Deferred
        '''
        log.info("Creating tess_t Table if not exists")
        return self.pool.runOperation(
            '''
            CREATE TABLE IF NOT EXISTS tess_t
            (
            tess_id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name               TEXT,
            mac_address        TEXT, 
            calibration_k      REAL,
            calibrated_since   TEXT,
            calibrated_until   TEXT,
            calibrated_state   TEXT,
            location_id     INTEGER NOT NULL DEFAULT -1 REFERENCES location_t(location_id)
            );
            '''
        )

    def indices(self):
        '''
        Create indices to SQLite Units table.
        Returns a Deferred
        '''
        log.info("Creating tess_t Indexes if not exists")
        return self.pool.runInteraction(_createIndices)

    def views(self):
        '''
        Create Views associated to this dimension.
        Returns a Deferred
        '''
        log.info("Creating tess_t Views if not exists")
        return self.pool.runInteraction(_createViews)


    @inlineCallbacks
    def populate(self, json_dir, replace):
        '''
        Populate the SQLite Instruments Table.
        Returns a Deferred
        '''
        log.info("Assigning locations to instruments")
        read_rows = yield deferToThread(fromJSON, os.path.join(json_dir, TESS.DEPL_FILE), DEFAULT_DEPLOYMENT)
        yield self.pool.runInteraction( _deployInstr, read_rows )


    # -------------
    # log stats API
    # -------------

    def resetCounters(self):
        '''Resets stat counters'''
        self.nregister = 0
        self.nCreation = 0
        self.nUpdNameChange  = 0
        self.nUpdCalibChange = 0 
        self.rejUpdDupName   = 0
        self.rejCreaDupName  = 0 
    

    def getCounters(self):
        '''get stat counters'''
        return [ 
                self.nregister, 
                self.nCreation,
                self.nUpdNameChange, 
                self.nUpdCalibChange, 
                self.rejUpdDupName,
                self.rejCreaDupName, 
                ]

    # =======
    # OPERATIONAL API
    # =======

    # -----------------------
    # Instrument registration
    # -----------------------

    @inlineCallbacks
    def register(self, row):
        '''
        Registers an instrument given its MAC address, friendly name and calibration constant
        Returns a Deferred.
        '''

        self.nregister += 1
        instrument = yield self.findMAC(row)
        # if  instrument with that MAC already exists, may be update it ...
        if len(instrument):
            instrument = instrument[0]  # Keep only the first row
            # If the new name is not equal to the old one, change it
            if row['name']  != instrument[0]:
            # unless the new name is already being used by another instrument
                instrument2 = yield self.findName(row)
                if not len(instrument2):
                    self.nUpdNameChange += 1
                    yield self.updateName(row)
                    log.info("Changed instrument name to {name}", name=row['name'])
                else:
                    self.rejUpdDupName += 1

            # If the new calibration constant is not equal to the old one, change it
            if row['calib'] != instrument[2]:
                yield self.updateCalibration(row)
                self.nUpdCalibChange += 1
                log.info("Changed instrument calibration data to {calib}", calib=row['calib'])
        else:
            # Find other posible existing instruments with the same name
            # We require the names to be unique as wellocation_t.
            # If that condition is met, we add a new instrument
            instrument = yield self.findName(row) 
            if len(instrument):
                log.info("Another instrument already registered with the same name: {name}", name=row['name']) 
                self.rejCreaDupName += 1
            else:
                yield self.addNew(row)
                self.nCreation += 1
                log.info("Brand new instrument registered: {name}", name=row['name'])
        


    def findMAC(self, row):
        '''
        Look up instrument parameters given its MAC address
        row is a dictionary with at least the following keys: 'mac'
        Returns a Deferred.
        '''
        row['calib_flag'] = utils.CURRENT
        return self.pool.runQuery(
            '''
            SELECT name, mac_address, calibration_k 
            FROM tess_t 
            WHERE mac_address == :mac
            AND calibrated_state == :calib_flag
            ''', row)


    def findName(self, row):
        '''
        Look up instrument parameters given its name
        row is a dictionary with at least the following keys: 'name'
        Returns a Deferred.
        '''
        row['calib_flag'] = utils.CURRENT
        return self.pool.runQuery(
            '''
            SELECT tess_id, mac_address, calibration_k, location_id 
            FROM tess_t 
            WHERE name == :name
            AND calibrated_state == :calib_flag 
            ''', row)



    def addNew(self, row):
        '''
        Adds a brand new instrument given its registration parameters.
        row is a dictionary with the following keys: 'name', 'mac', 'calib'
        Returns a Deferred.
        '''
        row['eff_date']   = datetime.datetime.utcnow().strftime(utils.TSTAMP_FORMAT)
        row['exp_date']   = utils.INFINITE_TIME
        row['calib_flag'] = utils.CURRENT
        return self.pool.runOperation( 
            '''
            INSERT INTO tess_t (
                name,
                mac_address,
                calibration_k,
                calibrated_since,
                calibrated_until,
                calibrated_state
            ) VALUES (
                :name,
                :mac,
                :calib,
                :eff_date,
                :exp_date,
                :calib_flag
            )
            ''', row)

   
    def updateName(self, row):
        '''
        Changes all instrument name records with the same MAC
        row is a dictionary with at least the following keys: 'mac' , 'name'
        Returns a Deferred.
        '''
        return self.pool.runOperation( 
            '''
            UPDATE tess_t SET name=:name
            WHERE mac_address == :mac 
            ''', row)


    def updateLocation(self, row):
        '''
        Changes all instrument location records with the same MAC
        row is a dictionary with at least the following keys: 'mac' , 'loc_id'
        Returns a Deferred.
        '''
        return self.pool.runOperation( 
            '''
            UPDATE tess_t SET location_id=:loc_id
            WHERE mac_address == :mac 
            ''', row )


    def updateCalibration(self, row):
        '''Updates Instrument calibration constant keeping its history'''
        return self.pool.runInteraction( _updateCalibration, row )
      