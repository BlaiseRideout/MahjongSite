#!/usr/bin/env python3

import warnings
import sqlite3
import random

class getCur():
    con = None
    cur = None
    def __enter__(self):
        self.con = sqlite3.connect("scores.db")
        self.cur = self.con.cursor()
        return self.cur
    def __exit__(self, type, value, traceback):
        if self.cur and self.con and not value:
            self.cur.close()
            self.con.commit()
            self.con.close()

        return False

class getCon():
    con = None
    def __enter__(self):
        self.con = sqlite3.connect("scores.db")
        return self.con
    def __exit__(self, type, value, traceback):
        if self.con and not value:
            self.con.commit()
            self.con.close()

            return False

def init():
    warnings.filterwarnings('ignore', r'Table \'[^\']*\' already exists')

    with getCur() as cur:
        cur.execute("CREATE TABLE IF NOT EXISTS Players(Id INTEGER PRIMARY KEY AUTOINCREMENT, Name TEXT);")

        cur.execute("CREATE TABLE IF NOT EXISTS Scores(Id INTEGER PRIMARY KEY AUTOINCREMENT, GameId INTEGER, PlayerId INTEGER, Rank TINYINT, PlayerCount TINYINT, RawScore INTEGER, Score REAL, Date DATE,\
            FOREIGN KEY(PlayerId) REFERENCES Players(Id) ON DELETE CASCADE);")

        cur.execute("CREATE TABLE IF NOT EXISTS CurrentPlayers(PlayerId INTEGER PRIMARY KEY,\
            FOREIGN KEY(PlayerId) REFERENCES Players(Id) ON DELETE CASCADE)")

        cur.execute("CREATE TABLE IF NOT EXISTS CurrentTables(Id INTEGER PRIMARY KEY AUTOINCREMENT, PlayerId INTEGER,\
            FOREIGN KEY(PlayerId) REFERENCES Players(Id) ON DELETE CASCADE)")

        cur.execute("CREATE TABLE IF NOT EXISTS Users(Id INTEGER PRIMARY KEY AUTOINCREMENT, Email TEXT NOT NULL, Password TEXT NOT NULL,\
            UNIQUE(Email));")

        cur.execute("CREATE TABLE IF NOT EXISTS Admins(Id INTEGER PRIMARY KEY NOT NULL,\
            FOREIGN KEY(Id) REFERENCES Users(Id) ON DELETE CASCADE);")

        cur.execute("CREATE TABLE IF NOT EXISTS VerifyLinks(Id CHAR(32) PRIMARY KEY NOT NULL, Email TEXT NOT NULL, Expires DATETIME)")
