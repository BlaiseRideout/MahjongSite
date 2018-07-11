#!/usr/bin/env python3

import warnings
import sqlite3
import random
import datetime
import re
import shutil
import os
import argparse

import util
import settings
from sqlite_schema import *

class getCur():
    con = None
    cur = None
    def __init__(self, dbfile=settings.DBFILE):
        self.__dbfile = dbfile
    def __enter__(self):
        self.con = sqlite3.connect(self.__dbfile)
        self.cur = self.con.cursor()
        self.cur.execute("PRAGMA foreign_keys = 1;")
        return self.cur
    def __exit__(self, type, value, traceback):
        if self.cur and self.con and not value:
            self.cur.close()
            self.con.commit()
            self.con.close()

        return False

schema = {
    'Players': [
        'Id INTEGER PRIMARY KEY AUTOINCREMENT',
        'Name TEXT UNIQUE',
        'MeetupName TEXT',
    ],
    'Scores': [
        'Id INTEGER PRIMARY KEY AUTOINCREMENT',
        'GameId INTEGER',
        'PlayerId INTEGER',
        'Rank TINYINT',
        'PlayerCount TINYINT',
        'RawScore INTEGER',
        'Score REAL',
        'Date DATE',
        'Chombos INTEGER',
        'Quarter TEXT',
        'DeltaRating REAL',
        'FOREIGN KEY(PlayerId) REFERENCES Players(Id) ON DELETE CASCADE'
    ],
    'CurrentPlayers': [
        'PlayerId INTEGER PRIMARY KEY',
        'Priority TINYINT',
        'FOREIGN KEY(PlayerId) REFERENCES Players(Id) ON DELETE CASCADE'
    ],
    'CurrentTables': [
        'Id INTEGER PRIMARY KEY AUTOINCREMENT',
        'PlayerId INTEGER',
        'FOREIGN KEY(PlayerId) REFERENCES Players(Id) ON DELETE CASCADE'
    ],
    'Users': [
        'Id INTEGER PRIMARY KEY AUTOINCREMENT',
        'Email TEXT NOT NULL',
        'Password TEXT NOT NULL',
        'UNIQUE(Email)'
    ],
    'Admins': [
        'Id INTEGER PRIMARY KEY NOT NULL',
        'FOREIGN KEY(Id) REFERENCES Users(Id) ON DELETE CASCADE'
    ],
    'ResetLinks': [
        'Id CHAR(32) PRIMARY KEY NOT NULL',
        'User INTEGER',
        'Expires DATETIME',
        'FOREIGN KEY(User) REFERENCES Users(Id)'
    ],
    'VerifyLinks': [
        'Id CHAR(32) PRIMARY KEY NOT NULL',
        'Email TEXT NOT NULL',
        'Expires DATETIME'
    ],
    'Quarters': [
        'Quarter TEXT PRIMARY KEY NOT NULL',
        'GameCount INTEGER NOT NULL',
        'UnusedPointsIncrement INTEGER DEFAULT 0'
    ],
    'Settings': [
        'UserId INTEGER',
        'Setting TEXT NOT NULL',
        'Value SETTING NOT NULL',
        'FOREIGN KEY(UserId) REFERENCES Users(Id)'
    ],
    'Timers': [
        'Id INTEGER PRIMARY KEY',
        'Name TEXT',
        'Duration INTEGER',
        'Time DATETIME',
    ],
    'Leaderboards': [
        'Period TEXT',
        'Date TEXT',
        'PlayerId INTEGER',
        'Place INTEGER',
        'AvgScore REAL',
        'GameCount INTEGER',
        'DropGames INTEGER',
        'FOREIGN KEY(PlayerId) REFERENCES Players(Id) ON DELETE CASCADE'
    ],
    'Memberships': [
        'PlayerId INTEGER REFERENCES Players(Id) ON DELETE CASCADE',
        'QuarterId TEXT REFERENCES Quarters(Quarter) ON DELETE CASCADE',
        'UNIQUE(PlayerId, QuarterId)'
        ],
}

def init(force=False, upgrade=True, ordermatters=False, dbfile=settings.DBFILE,
         verbose=0):
    existing_schema = get_sqlite_db_schema(dbfile)
    desired_schema = parse_database_schema(schema)
    if upgrade:
        if not compare_and_prompt_to_upgrade_database(
                desired_schema, existing_schema, dbfile,
                ordermatters=ordermatters, prompt_prefix='SCHEMA CHANGE: ', 
                force_response='y' if force else None, 
                backup_dir=settings.DBBACKUPS, 
                backup_prefix=settings.DBDATEFORMAT + '-', verbose=verbose):
            print('Database upgrade during initialization {}.'.format(
                'failed' if force else 'was either cancelled or failed'))
    else:
        delta = compare_db_schema(desired_schema, existing_schema, 
                                  verbose=verbose, ordermatters=ordermatters)
        if verbose > 0:
            print('Tables whose schema matches the one in {}:'.format(dbfile))
            for table in delta['same']:
                print(' ', table)
            print('New tables:')
            for table in delta['new_tables']:
                print(' ', table)
            print('Dropped tables:')
            for table in delta['dropped_tables']:
                print(' ', table)
            print('Tables with only added fields:')
            for table in delta['add_fields']:
                print(' ', table)
            print('Tables with other differences:')
            for table in delta['different']:
                print(' ', table)

def make_backup():
    backupdb = datetime.datetime.now().strftime(settings.DBDATEFORMAT) + "-" + os.path.split(settings.DBFILE)[1]
    backupdb = os.path.join(settings.DBBACKUPS, backupdb)
    print("Making backup of database {0} to {1}".format(settings.DBFILE, backupdb))
    if not os.path.isdir(settings.DBBACKUPS):
        os.mkdir(settings.DBBACKUPS)
    shutil.copyfile(settings.DBFILE, backupdb)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description="""Mahjong database check and upgrade program.
        This checks that the tables in a database match the schema
        description in this program.  It can alter the schema to
        make it match.
        """,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument(
        'database', default=settings.DBFILE, nargs='?',
        help='SQLite3 database file to check.  This overrides any values '
        'in defaults.py or mysettings.py.')
    parser.add_argument(
        '-u', '--upgrade', default=False, action='store_true',
        help='Try upgrading the database if differences detected. '
        'Use higher verbosity to see differences.')
    parser.add_argument(
        '-o', '--order-matters', default=False, action='store_true',
        help='When comparing database schema, the order of fields in the table '
        'matters if this option is selected.  Otherwise it is ignored.')
    parser.add_argument(
        '-f', '--force', default=False, action='store_true',
        help='Force changes without prompting first')
    parser.add_argument(
        '-v', '--verbose', action='count', default=0,
        help='Add verbose comments')

    args = parser.parse_args()

    init(force=args.force, dbfile=args.database,
         upgrade=args.upgrade, ordermatters=args.order_matters,
         verbose=args.verbose)
