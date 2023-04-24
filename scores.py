#!/usr/bin/env python3

import json
import handler
import tornado.web
import datetime
import collections

import db
import settings
import leaderboard

umas = {4:[15,5,-5,-15],
        5:[15,5,0,-5,-15]}

dateFormat = "%Y-%m-%d"

def quarterString(time=None, date=None):
    """Return the string for the calendar quarter for the given datetime object.
    Time defaults to current time"""
    if time is None and date is None:
        time = datetime.datetime.now()
    elif time is None:
        time = datetime.datetime.strptime(date, '%Y-%m-%d')
    return time.strftime("%Y ") + ["1st", "2nd", "3rd", "4th"][
        (time.month - 1) * 4 // 12]

def quarterDate(quarter=None):
    """Returns a datetime object for the quarter string passed
    return value defaults to today"""
    if quarter is None:
        return datetime.datetime.now()
    year = int(quarter[0:4])
    month = (int(quarter[5:6]) - 1) * 12 // 4 + 1
    return datetime.datetime(year=year, month=month, day=1)

def dateString(date):
    "Convert a datetime object to a date string (or leave as a string)"
    global dateFormat
    if isinstance(date, (datetime.datetime, datetime.date)):
        return date.strftime(dateFormat)
    elif isinstance(date, str):
        return date
    else:
        raise Exception('Unexpected input type passed to dateString, {}'.format(
            date))

def getPointSettings(quarter=None, date=None):
    """Get the UnusedPointsIncrement and starting ScorePerPlayer value for
    the given quarter.
    The quarter defaults to the most recent quarter in the database
    (but no later than today's date)."""
    if quarter is None:
        quarter = quarterString(date=date)
    try:
        with db.getCur() as cur:
            cur.execute("SELECT COALESCE(UnusedPointsIncrement, ?), "
                        "  COALESCE(ScorePerPlayer, ?) FROM Quarters"
                        "  WHERE Quarter <= ? ORDER BY Quarter DESC"
                        " LIMIT 1",
                        (settings.UNUSEDPOINTSINCREMENT,
                         settings.SCOREPERPLAYER,
                         quarter))
            increment, perPlayer = cur.fetchone()
    except:
        increment, perPlayer = (
            settings.UNUSEDPOINTSINCREMENT, settings.SCOREPERPLAYER)
    return increment, perPlayer

class PointSettings(handler.BaseHandler):
    @tornado.web.authenticated
    def get(self):
        date = self.get_argument("date", None)
        quarter = self.get_argument("quarter", quarterString(date=date))
        increment, perPlayer = getPointSettings(quarter=quarter, date=date)
        result = {"status": 0, "unusedPointsIncrement": increment,
                  "scorePerPlayer": perPlayer}
        self.write(json.dumps(result))

_unusedPointsPlayer = None
unusedPointsPlayerName = '!#*UnusedPointsPlayer*#!'

def getUnusedPointsPlayerID():
    """ Get the ID of the Players table entry that records unused points in
    games.  If an entry doesn't exist, create one."""
    global _unusedPointsPlayer, unusedPointsPlayerName
    if _unusedPointsPlayer:
        return _unusedPointsPlayer
    with db.getCur() as cur:
        cur.execute("SELECT Id from Players WHERE Name = ? AND"
                    " MeetupName IS NULL",
                    (unusedPointsPlayerName,))
        result = cur.fetchall()
        if len(result) > 1:
            raise Exception("More than 1 player defined for unused points")
        elif len(result) == 1:
            _unusedPointsPlayer = result[0][0]
        else:
            cur.execute("INSERT INTO Players (Name, MeetupName) VALUES (?, NULL)",
                        (unusedPointsPlayerName,))
            _unusedPointsPlayer = cur.lastrowid
    return _unusedPointsPlayer

def getScore(score, uma, perPlayer):
    return (score - perPlayer) / 1000.0 + uma

def rankGame(scores, perPlayer, unusedPointsIncr):
    """Calculates rank, point penalties, and umas for a given game.
    Also validates game player names and point totals.
    The scores should be a list of dictionaries.
    Each dictionary should have either a 'PlayerId' or 'Name',
    a 'RawScore', and a 'Chombos' count.
    One of the players may be the UnusedPointsPlayer to represent points
    that were not claimed at the end of play.
    Modifies the scores dictionaries adding the calculated fields.
    Returns a dictionary with a 'status' and a 'message' field.  Status of 0
    means success.
    """
    if scores is None:
        return {"status":1, "error":"Please enter some scores"}

    hasUnusedPoints = False
    unusedPoints = 0
    unusedPointsPlayerID = getUnusedPointsPlayerID()
    total = 0
    uniqueIDs = set()
    pointHistogram = collections.defaultdict(lambda : 0)
    for score in scores:
        isUnusedPlayerId = ('PlayerId' in score and
                            score['PlayerId'] in (-1, unusedPointsPlayerID))
        isUnusedPlayerName = ('Name' in score and
                              score['Name'] == unusedPointsPlayerName)
        score['points'] = score['RawScore'] - (
            settings.CHOMBOPENALTY * score['Chombos'] * 1000)
        if isUnusedPlayerName or isUnusedPlayerId:
            score['PlayerId'] = unusedPointsPlayerID
            score['Name'] = unusedPointsPlayerName
            hasUnusedPoints = True
            unusedPoints = score['RawScore']
        else:
            pointHistogram[score['points']] += 1
        uniqueIDs.add(score['Name'] if 'Name' in score else score['PlayerId'])
        total += score['RawScore']

    realPlayerCount = len(scores) - (1 if hasUnusedPoints else 0)

    if not (4 <= realPlayerCount and realPlayerCount <= 5):
        return {"status":1, "error":"Please enter 4 or 5 scores"}

    if "" in uniqueIDs:
        return {"status":1, "error":"Please enter all player names"}

    if len(uniqueIDs) < len(scores):
        return {"status":1, "error": "All players must be distinct"}

    if hasUnusedPoints and unusedPoints % unusedPointsIncr != 0:
        return {"status":1,
                "error":"Unused points must be a multiple of {0}".format(
                    unusedPointsIncr)}

    targetTotal = realPlayerCount * perPlayer
    if total != targetTotal:
        return {"status": 1,
                "error": "Scores add up to {}, not {}".format(
                    total, targetTotal)}

    # Sort scores for ranking, ensuring unused points player is last, if present
    scores.sort(
        key=lambda x: ('PlayerId' not in x or x['PlayerId'] != unusedPointsPlayerID, x['points']),
        reverse=True)

    rank = 1
    pointHistogram[None] = 0
    last_points = None
    for score in scores:
        if score['points'] != last_points:
            rank += pointHistogram[last_points]
            last_points = score['points']
        score['Rank'] = rank
        score['uma'] = 0
        if score.get('PlayerId', None) != unusedPointsPlayerID:
            for j in range(rank-1, rank-1 + pointHistogram[last_points]):
                score['uma'] += umas[realPlayerCount][j]
            score['uma'] /= pointHistogram[last_points]
            score['Score'] = getScore(score['points'], score['uma'], perPlayer)
        else:
            score['Score'] = 0

    return {"status": 0, "realPlayerCount": realPlayerCount,
            "hasUnusedPoints": hasUnusedPoints}

def addGame(scores, gamedate = None, gameid = None):
    """Add or replace game scores for a particular game in the database.
    The scores should be a list of dictionaries.
    Each dictionary should have either a 'PlayerId' or 'Name',
    a 'RawScore', and a 'Chombos' count.
    One of the players may be the UnusedPointsPlayer to represent points
    that were not claimed at the end of play.
    The gamedate defaults to today.  A new gameid is created if none is given.
    If a player name is not found in database, a new record is created for
    them.
    Returns a dictionary with a 'status' and a 'message' field.  Status of 0
    means success.
    """
    global unusedPointsPlayerName

    if scores is None:
        return {"status":1, "error":"Please enter some scores"}

    if gamedate is None:
        if 'Date' in scores[0]:
            gamedate = scores[0]['Date']
        else:
            gamedate = dateString(datetime.datetime.now())
    if gameid is None:
        if 'GameId' in scores[0]:
            gameid = scores[0]['GameId']

    quarter = quarterString(datetime.datetime.strptime(gamedate, dateFormat))
    unusedPointsIncr, perPlayer = getPointSettings(quarter=quarter)

    status = rankGame(scores, perPlayer, unusedPointsIncr)
    if status['status'] == 0:
        hasUnusedPoints = status['hasUnusedPoints']
        realPlayerCount = status['realPlayerCount']
    elif status['status'] == 1:
        return status

    unusedPointsPlayerID = getUnusedPointsPlayerID()

    with db.getCur() as cur:
        if gameid is None:
            cur.execute("SELECT COALESCE(GameId, 0) FROM Scores ORDER BY GameId DESC LIMIT 1")
            game_row = cur.fetchone()
            if game_row is not None:
                gameid = game_row[0] + 1
            else:
                gameid = 0
            olddate = gamedate
        else:
            cur.execute("SELECT MAX(Date) FROM Scores WHERE GameId = ?"
                        "  GROUP BY GameId", (gameid,))
            result = cur.fetchone()
            if result is not None:
                olddate = result[0]
                cur.execute("DELETE FROM Scores WHERE GameId = ?", (gameid,))

        columns = ["GameId", "PlayerId", "Rank", "PlayerCount",
            "RawScore", "Chombos", "Score", "Date", "Quarter", "DeltaRating"]

        rows = []
        for score in scores:
            if 'PlayerId' not in score:
                cur.execute("SELECT Id FROM Players WHERE Name = ?",
                            (score['Name'],))
                player = cur.fetchone()

                if player is not None and len(player) > 0:
                    score['PlayerId'] = player[0]
                else:
                    cur.execute("INSERT INTO Players(Name) VALUES(?)",
                                (score['Name'],))
                    score['PlayerId'] = cur.lastrowid

            score['GameId'] = gameid
            score['PlayerCount'] = realPlayerCount
            score['Date'] = gamedate
            score['Quarter'] = quarter
            score['DeltaRating'] = deltaRating(scores, score)

            row = [score[col] for col in columns]
            rows += [row]

        query = "INSERT INTO Scores({columns}) VALUES({values})".format(
                columns=",".join(columns),
                values=",".join(["?"] * len(columns)))
        cur.executemany(query, rows)

    leaderboard.genLeaderboard(gamedate)
    if olddate != gamedate:
        leaderboard.genLeaderboard(olddate)
    return {"status":0}

adjEvent = 0.5

def playerRatingBeforeDate(playerId, gamedate):
    with db.getCur() as cur:
        cur.execute("SELECT COALESCE(SUM(DeltaRating), 0) + ? FROM Scores WHERE PlayerId = ? AND Date < ?;", (settings.DEFAULT_RATING, playerId, gamedate))
        return cur.fetchone() [0]
    return settings.DEFAULT_RATING

def deltaRating(scores, player):
    gamedate = scores[0]['Date']
    unusedPointsPlayerID = getUnusedPointsPlayerID()
    if player['PlayerId'] == unusedPointsPlayerID:
        return 0

    totalOppRating = 0
    realPlayerCount = len(scores)
    for score in scores:
        if 'PlayerId' not in score: # score player's first game
            score['Rating'] = settings.DEFAULT_RATING
        elif score['PlayerId'] == unusedPointsPlayerID:
            realPlayerCount -= 1
            continue

        if 'Rating' not in score:
            score['Rating'] = playerRatingBeforeDate(score['PlayerId'], gamedate)

        if 'PlayerId' not in score or score['PlayerId'] != player['PlayerId']:
            totalOppRating += score['Rating']
    avgOppRating = totalOppRating / (realPlayerCount - 1)

    with db.getCur() as cur:
        cur.execute("SELECT COALESCE(COUNT(*), 0) FROM Scores"
                    "  WHERE PlayerId = ? AND Date < ?",
                    (player['PlayerId'], gamedate))
        gameCount = cur.fetchone()[0]
        adjPlayer = max(1 - (gameCount * 0.008), 0.2)

    return (player['uma'] * 2 +
            adjEvent * (avgOppRating - player['Rating'])
            / 40) * adjPlayer

def getScores(gameid, getNames = False, unusedPoints = False):
    with db.getCur() as cur:
        columns = ["Id","PlayerId","GameId","Score","RawScore","Chombos","Date",
                   "DeltaRating","Rank"]
        queryColumns = ["Scores.Id","PlayerId","GameId","Score","RawScore","Chombos","Date",
                   "DeltaRating","Rank"]
        tables = ["Scores"]

        if getNames:
            columns += ['Name']
            queryColumns += ['Name']
            tables += ["JOIN Players ON PlayerId = Players.Id"]

        conditions = ["GameId = ?"]
        bindings = [gameid]

        if not unusedPoints:
            conditions += ["PlayerId != ?"]
            bindings += [getUnusedPointsPlayerID()]

        query = "SELECT {columns} FROM {tables} WHERE {conditions}".format(
            columns=",".join(queryColumns),
            tables=" ".join(tables),
            conditions=" AND ".join(conditions))
        cur.execute(query, bindings)

        scores = [dict(zip(columns, row)) for row in cur.fetchall()]
        return scores
