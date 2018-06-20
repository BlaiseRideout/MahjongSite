#!/usr/bin/env python3

import warnings
import sqlite3
import random
import datetime
import re
import collections
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

schema = collections.OrderedDict({
    'Players': [
        'Id INTEGER PRIMARY KEY AUTOINCREMENT',
        'Name TEXT',
        'MeetupName TEXT'
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
        'unique(name, duration, time)on conflict fail',
        'ChEcK (duration > 0)',
    ],
    'Leaderboards': [
        'Period TEXT',
        'Date TEXT',
        'PlayerId INTEGER',
        'Place INTEGER',
        'AvgScore REAL',
        'GameCount INTEGER',
        'DropGames INTEGER',
        'PRIMARY KEY(Period, Date)',
        'FOREIGN KEY(PlayerId) REFERENCES Players(Id) ON DELETE CASCADE'
    ],
    'Memberships': [
        'PlayerId INTEGER REFERENCES Players(Id) ON DELETE CASCADE',
        'QuarterId TEXT REFERENCES Quarters(Quarter)',
        'UNIQUE(PlayerId, QuarterId)'
        ],
})

def init(force=False, upgrade=True, ordermatters=False, dbfile=settings.DBFILE,
         verbose=0):
    if verbose < 2:
        warnings.filterwarnings('ignore', r"Table '[^']*' already exists")

    global schema
    independent_tables = []
    dependent_tables = []
    for table in schema:
        if len(parent_tables(schema[table])) == 0:
            independent_tables.append(table)
        else:
            dependent_tables.append(table)

    to_check = collections.deque(independent_tables + dependent_tables)
    checked = set()
    max_count = len(independent_tables) + len(dependent_tables) ** 2 / 2
    count = 0
    while count < max_count and len(to_check) > 0:
        table = to_check.popleft()
        # If this table's parents haven't been checked yet, defer it
        if set(parent_tables(table)) - checked:
            to_check.append(table)
        else:
            check_table_schema(
                table, schema[table], ordermatters=ordermatters, 
                upgrade=upgrade, force=force, dbfile=dbfile, verbose=verbose)
            checked.add(table)
        count += 1

def make_backup(dbfile=settings.DBFILE,
                dateformat=settings.DBDATEFORMAT,
                backupdir=settings.DBBACKUPS):
    backupdb = datetime.datetime.now().strftime(dateformat) + "-" + os.path.split(dbfile)[1]
    backupdb = os.path.join(backupdir, backupdb)
    print("Making backup of database {} to {}".format(dbfile, backupdb))
    if not os.path.isdir(backupdir):
        os.mkdir(backupdir)
    shutil.copyfile(dbfile, backupdb)

def check_table_schema(tablename, table_spec,
                       ordermatters=False, force=False, backupname="_backup", 
                       upgrade=True, dbfile=settings.DBFILE, verbose=0):
    """Compare an existing table schema in a given database with that in
    the table_spec and make corrections if upgrade requested.  It will
    prompt to make make changes unless force is requested.

    The algorithm checks for new tables, new fields, new (foreign key)
    constraints, and altered field specificaitons.  If ordermatters is
    true, changes to the order of fields are checked. For schema
    changes beyond just adding fields, it renames the old table to a
    "backup" table, and then copies its content into a freshly built
    new version of the table.  For other "complex" schema changes, it
    moves the old database aside and either build from scratch or
    manually alter it.

    """
    # Table spec starts with column specifications
    table_fields = column_specs(table_spec)
    table_pragmas = []
    for f in table_fields:
        table_pragmas.extend(column_def_or_constraint_to_pragma_records(
            f, tablename=tablename, context=table_pragmas))
    columns = 0
    for c_i, p in enumerate(table_pragmas):
        if isinstance(p, sqlite_column_record):
            if ordermatters:
                table_pragmas[c_i] = p._replace(cid=columns)
            columns += 1

    # After the column specifications come table constraints
    for f in table_spec[len(table_fields):]:
        table_pragmas.extend(column_def_or_constraint_to_pragma_records(
            f, tablename=tablename, context=table_pragmas))

    # Now get the actual database pragma records describing its schema
    actual_pragmas = pragma_records_for_table(tablename, dbfile)
    for p_i, p in enumerate(actual_pragmas): # Force lowercase names
        if 'name' in p._fields:
            actual_pragmas[p_i] = p._replace(name=p.name.lower())
    with getCur(dbfile=dbfile) as cur:
        if len(actual_pragmas) == 0:
            if verbose > 0:
                print("Schema in {} does not have table {}".format(
                    dbfile, tablename))
            if upgrade:
                if verbose > 0:
                    print("Creating empty {} table in {}".format(
                        tablename, dbfile))
                cur.execute("CREATE TABLE IF NOT EXISTS {} ({});".format(
                    tablename, ", ".join(table_spec)))
        else:
            fields_to_add = missing_fields(table_pragmas, actual_pragmas)
            deleted = deleted_fields(table_pragmas, actual_pragmas)
            altered = altered_fields(table_pragmas, actual_pragmas,
                                     ordermatters)
            constraints_to_add = missing_constraints(table_pragmas,
                                                     actual_pragmas)
            constraints_deleted = deleted_constraints(table_pragmas,
                                                      actual_pragmas)
            changed = len(fields_to_add + deleted + altered + 
                          constraints_to_add + constraints_deleted) > 0
            if verbose > 0:
                print('Schema for table {} in {} is {}different'.format(
                    tablename, dbfile, '' if changed else 'not '))
            if changed and verbose > 1:
                if fields_to_add:
                    print('  Adding fields:', [p.name for p in fields_to_add])
                    for p in fields_to_add:
                        print('   ', p)
                if deleted:
                    print('  Deleting fields:', [p.name for p in deleted])
                if altered:
                    for pragma, changes in altered:
                        print('  Field {} changes:'.format(pragma.name))
                        for c in changes:
                            print('   ', c)
                        print('    New definiton: {}'.format(pragma))
                if constraints_to_add:
                    print('  Adding constraints:')
                    for p in constraints_to_add:
                        print('   ', p)
                if constraints_deleted:
                    print('  Deleting constraints:')
                    for p in constraints_deleted:
                        print('   ', p)
            if (upgrade and 
                len(fields_to_add) > 0 and 
                len(deleted + altered + 
                    constraints_to_add + constraints_deleted) == 0):
                # Only new fields to add
                if force or util.prompt(
                        "SCHEMA CHANGE: Add {} to table {}".format(
                            ", ".join(fields_to_add), tablename)):
                    if verbose > 1:
                        print("Adding fields to {}:\n{}".format(
                            tablename, fields_to_add))
                    for field_spec in fields_to_add:
                        sql = "ALTER TABLE {} ADD COLUMN {};".format(
                            tablename, field_spec)
                        if verbose > 2:
                            print('Executing SQL:\n', sql)
                        cur.execute(sql)
            elif upgrade and changed:
                # Fields have changed significantly; try copying old into new
                prompt = "SCHEMA CHANGE: Backup and recreate table {} to ".format(
                    tablename)
                prompt += "add fields {}, ".format(
                    fields_to_add) if fields_to_add else ""
                prompt += "remove fields {}, ".format(
                    deleted) if deleted else ""
                prompt += "alter fields {}, ".format(
                    [a[0] for a in altered]) if altered else ""
                prompt += "impose constraints {}, ".format(
                    constraints_to_add) if constraints_to_add else ""
                prompt += "remove constraints {}, ".format(
                    constraints_deleted) if constraints_deleted else ""
                if force or util.prompt(prompt[:-2]):
                    make_backup()
                    backup = tablename + backupname
                    sql = "ALTER TABLE {} RENAME TO {};".format(
                        tablename, backup)
                    cur.execute(sql)
                    sql = "CREATE TABLE {} ({});".format(
                        tablename, ", ".join(table_spec))
                    if verbose > 2:
                        print('Executing SQL:\n', sql)
                    cur.execute(sql)
                    # Copy all actual fields that have a corresponding field
                    # in the new schema
                    common_fieldnames = [
                        p.name for p in 
                        common_fields(table_pragmas, actual_pragmas)]
                    sql = "INSERT INTO {0} ({1}) SELECT {1} FROM {2};".format(
                        tablename, ", ".join(common_fieldnames), backup)
                    if verbose > 2:
                        print('Executing SQL:\n', sql)
                    cur.execute(sql)
                    sql = "DROP TABLE {};".format(backup)
                    if verbose > 2:
                        print('Executing SQL:\n', sql)
                    cur.execute(sql)

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
        help='Try upgrading the database if differences detected')
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

    if args.verbose > 2:
        print('Checking constraints in schema...')
        for table, desc in schema.items():
            check_constraint_pattern_match(table, desc)
    init(force=args.force, dbfile=args.database,
         upgrade=args.upgrade, ordermatters=args.order_matters,
         verbose=args.verbose)
