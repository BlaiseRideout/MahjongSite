#!/usr/bin/env python3

import json

import db
import handler
import leaderboard
from util import *

class PlayerStatsDataHandler(handler.BaseHandler):
    _statquery = """
       SELECT Max(Score),MIN(Score),COUNT(*),
         ROUND(SUM(Score) * 1.0/COUNT(*) * 100) / 100,
         ROUND(SUM(Rank) * 1.0/COUNT(*) * 100) / 100,
         MIN(Rank), MAX(Rank), MIN(Date), MAX(Date),
         MIN(Quarter), MAX(Quarter) {subquery} """
    _statqfields = ['maxscore', 'minscore', 'numgames', 'avgscore',
                    'avgrank', 'maxrank', 'minrank', 'mindate', 'maxdate',
                    'minquarter', 'maxquarter']
    _rankhistogramquery = """
        SELECT Rank, COUNT(*) {subquery} GROUP BY Rank ORDER BY Rank"""
    _rankhfields = ['rank', 'rankcount']

    def populate_queries(self, cur, period_dict):
        cur.execute(self._statquery.format(**period_dict),
                    period_dict['params'])
        period_dict.update(
            dict(zip(self._statqfields,
                     map(lambda x: round(x, 2) if isinstance(x, float) else x,
                         cur.fetchone()))))
        cur.execute(self._rankhistogramquery.format(**period_dict),
                    period_dict['params'])
        rank_histogram = dict([map(int, r) for r in cur.fetchall()])
        rank_histogram_list = [{'rank': i, 'count': rank_histogram.get(i, 0)}
                               for i in range(1, 6)]
        period_dict['rank_histogram'] = rank_histogram_list

    def get(self, player, quarter):
        with db.getCur() as cur:
            name = player
            cur.execute("SELECT Id,Name,MeetupName FROM Players WHERE Id = ? OR Name = ?", (player, player))
            player = cur.fetchone()
            if player is None or len(player) == 0:
                self.write(json.dumps({'status': 1,
                                       'error': "Couldn't find player"}))
                return
            playerID, name, meetupName = player

            N = 5
            # Periods is a list of dicts; one for each stat period.
            # We initialize the dict to describe the period, then call
            # populate_queries to run the stats and histogram queries on
            # the period and add entries to the dictionary for those stats
            periods = [
                {'name': 'All Time Stats',
                 'subquery': "FROM Scores WHERE PlayerId = ?",
                 'params': (playerID,)
                },
            ]
            p0 = periods[0]
            self.populate_queries(cur, p0)
            if p0['numgames'] == 0:
                return self.render("playerstats.html", name=name,
                                   error = "Couldn't find any scores for")

            if (quarter and p0['minquarter'] <= quarter and 
                quarter <= p0['maxquarter']):
                # Quarter provided in URI so just show that quarter
                periods = [ {'name': 'Quarter {0} Stats'.format(quarter),
                             'subquery': "FROM Scores WHERE PlayerId = ? "
                             "AND Quarter = ?",
                             'params': (playerID, quarter)
                } ]
            else:
                if p0['numgames'] > N:
                    periods.append(
                        {'name': 'Last {0} Game Stats'.format(N),
                         'subquery': "FROM (SELECT * FROM Scores "
                         "WHERE PlayerId = ? ORDER BY Date DESC LIMIT ?)",
                         'params': (playerID, N)
                        })
                if p0['minquarter'] < p0['maxquarter']:
                    periods.append(
                        {'name': 'Quarter {0} Stats'.format(p0['maxquarter']),
                         'subquery': "FROM Scores WHERE PlayerId = ? "
                         "AND Quarter = ?",
                         'params': (playerID, p0['maxquarter'])
                        })
                    prevQtr = formatQuarter(prevQuarter(
                        parseQuarter(p0['maxquarter'])))
                    periods.append(
                        {'name': 'Quarter {0} Stats'.format(prevQtr),
                         'subquery': "FROM Scores WHERE PlayerId = ? "
                         "AND Quarter = ?",
                         'params': (playerID, prevQtr)
                        })
            for p in (periods[1:] if len(periods) > 1 else periods):
                self.populate_queries(cur, p)

            self.write(json.dumps({'playerstats': periods, 'status': 0}))


class PlayerStatsHandler(handler.BaseHandler):
    def get(self, player, quarter):
        with db.getCur() as cur:
            name = player
            cur.execute("SELECT Id,Name,MeetupName FROM Players WHERE Id = ? OR Name = ?", (player, player))
            player = cur.fetchone()
            if player is None or len(player) == 0:
                return self.render("playerstats.html", name=name,
                                   error = "Couldn't find player")

            player, name, meetupname = player
            eligible = leaderboard.get_eligible()
            quarterHistory = [
                {'Name': qtr,
                 'Played': eligible[qtr][player]['Played'],
                 'Member': eligible[qtr][player]['Member'],
                 'Eligible': eligible[qtr][player]['Eligible']}
                for qtr in sorted(eligible.keys())[-settings.TIMELINEQUARTERS:]]
            self.render("playerstats.html",
                        error = None,
                        name = name,
                        meetupname = meetupname,
                        quarterHistory=quarterHistory
                )

    def post(self, player):
        name = self.get_argument("name", player)
        meetupname = self.get_argument("meetupname", None)
        if name != player or meetupname is not None:
            args = []
            cols = []
            if name != player:
                cols += ["Name = ?"]
                args += [name]
            if meetupname is not None:
                cols += ["MeetupName = ?"]
                args += [meetupname]
            if len(args) > 0:
                query = "UPDATE Players SET " + ",".join(cols) + " WHERE Id = ? OR Name = ?"
                args += [player, player]
                with db.getCur() as cur:
                    cur.execute(query, args)
            self.redirect("/playerstats/" + name)

quarterSuffixes = {'1': 'st', '2': 'nd', '3': 'rd', '4': 'th'}

def parseQuarter(qstring):
    if not isinstance(qstring, str) or len(qstring) != 8:
        return None
    if not qstring[0:4].isdigit() or not qstring[5] in quarterSuffixes:
        return None
    return (int(qstring[0:4]), int(qstring[5]))

def formatQuarter(qtuple):
    return "{0} {1}{2}".format(qtuple[0], qtuple[1],
                               quarterSuffixes[str(qtuple[1])])

def nextQuarter(qtuple):
    return (qtuple[0] + 1, 1) if qtuple[1] == 4 else (qtuple[0], qtuple[1] + 1)

def prevQuarter(qtuple):
    return (qtuple[0] - 1, 4) if qtuple[1] == 1 else (qtuple[0], qtuple[1] - 1)
