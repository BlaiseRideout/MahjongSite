#!/usr/bin/env python3

import json

import db
import handler
import settings
import scores

columns = ['Period', 'Date', 'PlayerId', 'AvgScore', 'GameCount', 'DropGames']
periods = {
    "annual":{
        "queries":["""SELECT
            'annual',
             {datefmt},
             PlayerId,
             ROUND(SUM(Scores.Score) * 1.0 / COUNT(Scores.Score) * 100)
               / 100 AS AvgScore,
             COUNT(Scores.Score) AS GameCount,
             0
           FROM Scores
           WHERE PlayerId != ?
           AND {datetest}
           GROUP BY {datefmt},PlayerId
           ORDER BY AvgScore DESC;"""],
       "datefmt": "strftime('%Y', {date})",
       },
    "biannual":{
        "queries":["""SELECT
            'biannual',
             {datefmt},
             PlayerId,
             ROUND(SUM(Scores.Score) * 1.0 / COUNT(Scores.Score) * 100)
               / 100 AS AvgScore,
             COUNT(Scores.Score) AS GameCount,
             0
           FROM Scores
           WHERE PlayerId != ?
           AND {datetest}
        GROUP BY {datefmt},PlayerId
        ORDER BY AvgScore DESC;"""],
        "datefmt":"""strftime('%Y', {date}) || ' ' ||
               case ((strftime('%m', {date}) - 1) * 2 / 12)
                   when 0 then '1st'
                   when 1 then '2nd'
                end"""
    },
    "quarter":{
        "queries":["""SELECT
            'quarter',
             {{datefmt}},
             PlayerId,
             ROUND(SUM(Scores.Score) * 1.0 / COUNT(Scores.Score) * 100)
               / 100 AS AvgScore,
             COUNT(Scores.Score) AS GameCount,
             {DROPGAMES}
           FROM Scores
             LEFT OUTER JOIN Quarters ON Scores.Quarter = Quarters.Quarter
           WHERE PlayerId != ? AND Scores.Id NOT IN
             (SELECT Id FROM Scores as s
               WHERE s.PlayerId = Scores.PlayerId AND s.Quarter = Scores.Quarter
               ORDER BY s.Score ASC LIMIT {DROPGAMES})
           AND {{datetest}}
           GROUP BY {{datefmt}},PlayerId
           HAVING COUNT(Scores.Score) + {DROPGAMES} BETWEEN
             COALESCE(Quarters.GameCount,{DEFDROPGAMES}) * {DROPGAMES} AND
             COALESCE(Quarters.GameCount,{DEFDROPGAMES}) * ({DROPGAMES} + 1) - 1
           ORDER BY AvgScore DESC;""".format(
               DROPGAMES=i,DEFDROPGAMES=settings.DROPGAMES)
        for i in range(settings.MAXDROPGAMES + 1)],
        "datefmt": """strftime('%Y', {date}) || ' ' ||
               case ((strftime('%m', {date}) - 1) * 4 / 12)
                   when 0 then '1st'
                   when 1 then '2nd'
                   when 2 then '3rd'
                   when 3 then '4th'
                end"""
        }
}

class LeaderboardHandler(handler.BaseHandler):
    def get(self, period):
        self.render("leaderboard.html")

class LeaderDataHandler(handler.BaseHandler):
    def get(self, period):
        while period.startswith('/'):
            period = period[1:]
        if '/' in period:
            period, rest = period.split('/', 1)
        if period not in periods:
            period = "quarter"

        rows = []
        with db.getCur() as cur:
            displaycols = ['Name', 'Place'] + columns
            cur.execute("SELECT {columns} FROM Leaderboards"
                    " JOIN Players ON PlayerId = Players.Id"
                    " WHERE Period = ? ORDER BY Date DESC, Place ASC".format(
                        columns=",".join(displaycols)
                    ),
                    (period,)
                )
            rows = [dict(zip(displaycols, row)) for row in cur.fetchall()]

        leaderboards = {}
        for row in rows:
            date = row['Date']
            if date not in leaderboards:
                leaderboards[date] = []

            leaderboards[date] += [row]

        leaderboards = sorted(leaderboards.items(), reverse=True)
        leaderboards = [{'Date': date, 'Scores': scores} for date, scores in leaderboards]

        self.write(json.dumps({'leaderboards':list(leaderboards)}))

def genLeaderboard(leaderDate = None):
    """Recalculates the leaderboard for the given datetime object.
    If leaderDate is None, then recalculates all leaderboards."""

    # Get unused points playerID before opening cursor to change leaderboard
    # records to avoid db deadlock if no unused player is yet defined
    unusedPointsPlayerID = scores.getUnusedPointsPlayerID()
    with db.getCur() as cur:
        leadercols = ['Place'] + columns
        leaderrows = []

        for periodname, period in periods.items():
            rows = []
            queries = period['queries']
            datefmt = period['datefmt']
            sql = "DELETE FROM Leaderboards WHERE Period = ? "
            if leaderDate is not None:
                datetest = "(" + datefmt + ") = (" + datefmt.format(date="?") + ")"
                bindings = [leaderDate] * datefmt.count("{date}")
                sql += "AND Date = {datefmt}".format(datefmt=datefmt).format(
                    date="?")
            else:
                datetest = "1"
                bindings = []
            cur.execute(sql, [periodname] + bindings)

            for query in queries:
                sql = query.format(datetest=datetest, datefmt=datefmt).format(
                    date="Scores.Date")
                cur.execute(sql, [unusedPointsPlayerID] + bindings)
                rows += [dict(zip(columns, row)) for row in cur.fetchall()]

            rows.sort(key=lambda row: row['AvgScore'], reverse=True) # sort by score
            places = {}
            for row in rows:
                if row['Date'] not in places:
                    places[row['Date']] = 1
                row['Place'] = places[row['Date']]
                places[row['Date']] += 1

                leaderrow = [row[col] for col in leadercols]
                leaderrows += [leaderrow]

        query = "INSERT INTO Leaderboards({columns}) VALUES({colvals})".format(
                columns=",".join(leadercols),
                colvals=",".join(["?"] * len(leadercols))
            )
        cur.executemany(query, leaderrows)

if __name__ == '__main__':
    import timeit, argparse
    parser = argparse.ArgumentParser(
        description="Generate leaderboards and time execution.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument(
        'date', nargs='*',
        help='Date for which Leaderboards should be recalculated in '
        'the format YYYY-MM-DD, e.g. "2018-02-27".')
    parser.add_argument(
        '-n', '--number', type=int, default=1,
        help='Number of times to repeat calculation for measuring timing')
    args = parser.parse_args()

    if args.date == []:
        args.date = [None]
    for date in args.date:
        elapsed = timeit.timeit('genLeaderboard(date)', number=args.number,
                                globals=globals())
        print('Running genLeaderboard({!r}) {} time{} took {} second{}'.format(
            date, args.number, '' if args.number == 1 else 's',
            elapsed, '' if elapsed == 1 else 's'))
        if args.number > 1:
            print('Average time = {}'.format(elapsed / args.number))
