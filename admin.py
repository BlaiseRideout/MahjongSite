#!/usr/bin/env python3

import json
import datetime
import os
import sys
import collections

import handler
import db
import util
import settings
import leaderboard
import scores

class AdminPanelHandler(handler.BaseHandler):
    @handler.is_admin
    def get(self):
        self.render("admin.html")

class ManageUsersHandler(handler.BaseHandler):
    @handler.is_admin
    def get(self):
        with db.getCur() as cur:
            cur.execute("SELECT Users.Id, Email, Password, Admins.Id FROM Users LEFT JOIN Admins ON Admins.Id = Users.Id")
            users = []
            for row in cur.fetchall():
                users += [{
                            "Id":row[0],
                            "Email":row[1],
                            "Admin":row[3] is not None,
                        }]
            self.render("users.html", users = users)

class PromoteUserHandler(handler.BaseHandler):
    @handler.is_admin
    def get(self, q):
        with db.getCur() as cur:
            cur.execute("SELECT Email FROM Users WHERE Id = ?", (q,))
            row = cur.fetchone()
            if len(row) == 0:
                self.render("message.html", message = "User not found", title = "Promote User")
            else:
                self.render("promoteuser.html", email = row[0], q = q)
    @handler.is_admin
    def post(self, q):
        with db.getCur() as cur:
            cur.execute("SELECT EXISTS(SELECT * FROM Users WHERE Id = ?)", (q,))
            if cur.fetchone()[0] == 1:
                cur.execute("INSERT INTO Admins(Id) VALUES(?)", (q,))
            self.redirect("/admin/users")

class DemoteUserHandler(handler.BaseHandler):
    @handler.is_admin
    def get(self, q):
        with db.getCur() as cur:
            cur.execute("SELECT Email FROM Users WHERE Id = ?", (q,))
            row = cur.fetchone()
            if len(row) == 0:
                self.render("message.html", message = "User not found", title = "Demote User")
            else:
                self.render("demoteuser.html", email = row[0], q = q)
    @handler.is_admin
    def post(self, q):
        with db.getCur() as cur:
            cur.execute("SELECT EXISTS(SELECT * FROM Users WHERE Id = ?)", (q,))
            if cur.fetchone()[0] == 1:
                cur.execute("DELETE FROM Admins WHERE Id = ?", (q,))
            self.redirect("/admin/users")

class DeleteGameHandler(handler.BaseHandler):
    @handler.is_admin
    def get(self, q):
        game = scores.getScores(q, getNames = True)
        if len(game) == 0:
            self.render("message.html", message = "Game not found", title = "Delete Game")
        else:
            self.render("deletegame.html", id=q, game=game)
    @handler.is_admin
    def post(self, q):
        gamedate = None
        with db.getCur() as cur:
            cur.execute("SELECT Date FROM Scores WHERE GameId = ?", (q,))
            gamedate = cur.fetchone()
            if gamedate is not None:
                gamedate = gamedate[0]
                db.make_backup()
                cur.execute("DELETE FROM Scores WHERE GameId = ?", (q,))
        if gamedate is not None:
            leaderboard.genLeaderboard(gamedate)
            self.redirect("/history")
        else:
            self.render("message.html", message = "Game not found", title = "Delete Game")

class EditGameHandler(handler.BaseHandler):
    @handler.is_admin
    def get(self, q):
        with db.getCur() as cur:
            cur.execute("SELECT Rank, Players.Name, Scores.RawScore, Scores.Chombos, Scores.Date, Players.Id FROM Scores INNER JOIN Players ON Players.Id = Scores.PlayerId WHERE GameId = ? ORDER BY Rank", (q,))
            rows = cur.fetchall()
            if len(rows) == 0:
                self.render("message.html", message = "Game not found", title = "Edit Game")
            else:
                unusedPoints = None
                # UnusedPointsPlayer always sorted last in rank
                if rows[-1][5] == scores.getUnusedPointsPlayerID():
                    unusedPoints = rows[-1][2]
                self.render("editgame.html", id=q,
                            scores=json.dumps(rows).replace("'", "\\'")
                            .replace("\\\"", "\\\\\""),
                            unusedPoints=unusedPoints,
                            unusedPointsIncrement=scores.unusedPointsIncrement(
                                date=rows[0][4]))
    @handler.is_admin_ajax
    def post(self, q):
        gamescores = self.get_argument('scores', None)
        gamedate = self.get_argument('gamedate', None)

        gamescores = json.loads(gamescores)

        with db.getCur() as cur:
            cur.execute("SELECT GameId FROM Scores WHERE GameId = ?", (q,))
            row = cur.fetchone()
            if len(row) == 0:
                self.write('{"status":1, "error":"Game not found"}')
                return
            gameid = row[0]

        db.make_backup()
        self.write(json.dumps(scores.addGame(gamescores, gamedate, gameid)))

quarterFields = [x.split()[0] for x in db.schema['Quarters'] 
                 if not x.startswith('FOREIGN')]
        
class EditQuarterHandler(handler.BaseHandler):
    @handler.is_admin
    def get(self, q):
        settingsDescriptions = getSettingsDescriptions()
        helptext = '<ul>'
        for field in ['DropGameCount'] + quarterFields:
            if field.upper() in settingsDescriptions:
                helptext += '<li><b><em>{}</em></b>'.format(
                    splitCamelCase(field))
                fieldhelp = settingsDescriptions[field.upper()]
                if fieldhelp.startswith(field.upper()):
                    helptext += fieldhelp[len(field):]
                else:
                    helptext += ' - ' + fieldhelp
        helptext += '</ul>'
        with db.getCur() as cur:
            cur.execute(("SELECT {} FROM Quarters WHERE Quarter <= ?"
                         "  ORDER BY Quarter DESC").format(', '.join(
                             quarterFields)),
                        (q,))
            rows = cur.fetchall()
            if len(rows) == 0:
                rows = [(q, settings.DROPGAMECOUNT,
                         settings.UNUSEDPOINTSINCREMENT,
                         settings.QUALIFYINGGAMES,
                         settings.QUALIFYINGDISTINCTDATES)]
            else:
                count = 0
                while count < len(rows) and rows[count][0] == q:
                    count += 1
                if count > 1:
                    self.render(
                        "message.html",
                        message = "Multiple entries in database for Quarter {0}".format(q),
                        title = "Database Error",
                        next = "Manage Quarters",
                        next_url = "/admin/quarters")
                if count == 0:
                    # Use most recent quarter before selected one as default
                    rows = [(q,) + rows[0][1:]] + rows
            self.render("editquarter.html", 
                        quarters=[dict(zip(quarterFields, row)) for row in rows],
                        help=helptext)

    @handler.is_admin
    def post(self, q):
        quarter = q
        values = { 'quarter': q }
        formfields = [name[0].lower() + name[1:] for name in quarterFields]
        for field in formfields[1:]:
            values[field] = self.get_argument(field, None)
        with db.getCur() as cur:
            cur.execute("DELETE FROM Quarters WHERE Quarter = ?;", (quarter,))
            cur.execute("INSERT INTO Quarters ({}) VALUES ({})".format(
                ', '.join(quarterFields),
                ', '.join(['?'] * len(formfields))),
                        [values[f] for f in formfields])

        leaderboard.genLeaderboard(scores.quarterDate(quarter))

        self.render("message.html",
                    message = "Quarter {0} updated".format(quarter),
                    title = "Quarter Updated",
                    next = "Update more quarters",
                    next_url = "/admin/quarters")

class QuartersHandler(handler.BaseHandler):
    @handler.is_admin
    def get(self):
        with db.getCur() as cur:
            cur.execute(
                ("SELECT DISTINCT Scores.Quarter, {} "
                 " FROM Scores LEFT OUTER JOIN Quarters"
                 " ON Scores.Quarter = Quarters.Quarter"
                 " ORDER BY Scores.Quarter DESC").format(
                     ', '.join(quarterFields[1:])))
            rows = cur.fetchall()

            self.render("quarters.html",
                        message = "No quarters found" if len(rows) == 0 else "",
                        quarters=[dict(zip(quarterFields, row)) for row in rows])

class DeleteQuarterHandler(handler.BaseHandler):
    @handler.is_admin
    def get(self, q):
        with db.getCur() as cur:
            cur.execute("SELECT Quarter FROM Quarters WHERE Quarter = ?", (q,))
            rows = cur.fetchall()
        if len(rows) == 0:
            self.render("message.html",
                        message = "Quarter {0} not found".format(q),
                        title = "Quarter Not Found",
                        next = "Manage quarters",
                        next_url = "/admin/quarters")
        elif len(rows) == 1:
            self.render(
                "confirm.html",
                question=("Are you sure you want to delete the {} Quarter?  "
                          "This can impact other parts of the system "
                          "such as membership records, unused points "
                          "settings, qualification criteria, etc.").format(
                              q),
                yesURL=self.request.path, yesMethod="post", yesLabel="Yes",
                noURL="/admin/quarters", noMethod="get", noLabel="No"
            )
        else:
            self.render("quarters.html",
                        message = ("Error: Multiple quarters named {0} "
                                   "found. See Adminstrator.").format(q),
                        quarters=rows)
        
    def post(self, q):
        with db.getCur() as cur:
            cur.execute("SELECT Quarter FROM Quarters WHERE Quarter = ?", (q,))
            rows = cur.fetchall()
        if len(rows) == 0:
            self.render("message.html",
                        message = "Quarter {0} not found".format(q),
                        title = "Quarter Not Found",
                        next = "Manage quarters",
                        next_url = "/admin/quarters")
        elif len(rows) == 1:
            with db.getCur() as cur:
                cur.execute("DELETE FROM Quarters WHERE Quarter = ?", (q,))
            self.render("message.html",
                        message = "Quarter {0} deleted".format(q),
                        title = "Quarter Deleted",
                        next = "Manage quarters",
                        next_url = "/admin/quarters")
            leaderboard.genLeaderboard(scores.quarterDate(quarter))
        else:
            self.render("quarters.html",
                        message = ("Error: Multiple quarters named {0} "
                                   "found. See Adminstrator.").format(q),
                        quarters=rows)

def getSettingsDescriptions():
    descriptions = collections.defaultdict(lambda : '')
    prefix = "#   "
    try:
        defaults = os.path.join(os.path.dirname(sys.argv[0]), 'defaults.py') 
        with open(defaults, 'r') as f:
            in_description = None
            for line in f:
                line.strip()
                if line.startswith(prefix):
                    line = line[len(prefix):]
                    words = line.split()
                    if words and len(words[0]) > 1 and words[0].isupper():
                        in_description = words[0]
                    if in_description:
                        descriptions[in_description] += line.replace('\n', ' ')
                else:
                    in_description = None
    except:
        print('Unable to read {} to get settings descriptions'.format(
            defaults), file=sys.stderr)
    return descriptions

def splitCamelCase(word):
    words = []
    for i in range(len(word)):
        if word[i].isupper() or len(words) == 0:
            words.append('')
        words[-1] += word[i]
    return ' '.join(words)
