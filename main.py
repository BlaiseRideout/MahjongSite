#!/usr/bin/env python3

__doc__ = """
Main program to run a web server for a Mahjong club's web site.
Launch this program (with an optional port number argument) on the
web server after configuring the mysettings.py file.  If no scores
database is found, an empty one will be created.  The first user
account will be given admin privileges to configure other options.
The web log is written to standard output (redirect as desired).
"""

import sys
import os.path
import os
import stat
import math
import tornado.httpserver
from tornado.httpclient import AsyncHTTPClient
import tornado.ioloop
import tornado.options
import tornado.web
import tornado.template
import signal
import json
import datetime

from quemail import QueMail
import handler
import util
import db
import settings

import seating
import timers
import login
import admin
import scores
import leaderboard
import playerstats
import players
import ratings
import version

# import and define tornado-y things
from tornado.options import options
cookie_secret = util.randString(32)

class MainHandler(handler.BaseHandler):
    def get(self):
        admin = handler.stringify(self.get_secure_cookie("admin"))

        no_user = False
        with db.getCur() as cur:
            cur.execute("SELECT COUNT(*) FROM Users")
            no_user = cur.fetchone()[0] == 0

        self.render("index.html", admin = admin, no_user = no_user)

class HistoryHandler(handler.BaseHandler):
    def get(self, page):
        if page is None:
            page = 0
        else:
            page = int(page[1:]) - 1
        PERPAGE = 5
        with db.getCur() as cur:
            cur.execute("SELECT DISTINCT Date FROM Scores ORDER BY Date DESC")
            dates = cur.fetchall()
            gamecount = len(dates)
            if gamecount > 0:
                cur.execute("SELECT Scores.GameId,"
                            " strftime('%Y-%m-%d', Scores.Date), Rank,"
                            " Players.Name, Scores.RawScore / 1000.0,"
                            " Scores.Score, Scores.Chombos, Players.Id"
                            " FROM Scores INNER JOIN Players ON"
                            "   Players.Id = Scores.PlayerId"
                            " WHERE Scores.Date BETWEEN ? AND ?;",
                            (dates[min(page * PERPAGE + PERPAGE - 1,
                                       gamecount - 1)][0],
                             dates[min(page * PERPAGE, gamecount - 1)][0]))
                rows = cur.fetchall()
                games = {}
                for row in rows:
                    gID, date, rank, name, rawscore, points, chombos, pID = row
                    if gID not in games:
                        games[gID] = {'date':date, 'scores':[],
                                      'id':gID, 'unusedPoints': 0}
                    if pID == scores.getUnusedPointsPlayerID():
                        games[gID]['unusedPoints'] = rawscore
                    else:
                        games[gID]['scores'].append(
                            (rank, name, rawscore, round(points, 2), chombos))
                maxpage = math.ceil(gamecount * 1.0 / PERPAGE)
                pages = range(max(1, page + 1 - 10), int(min(maxpage, page + 1 + 10) + 1))
                games = sorted(games.values(),
                               key=lambda x: (x['date'], x['id']), reverse=True)
                if page != 0:
                    prev = page
                else:
                    prev = None
                if page + 1 < maxpage:
                    nex = page + 2
                else:
                    nex = None
                self.render("history.html", error=None, games=games,
                            curpage=page + 1, pages=pages, gamecount=gamecount,
                            nex=nex, prev=prev,
                            ChomboPenalty=settings.CHOMBOPENALTY)
            else:
                self.render("message.html", message="No games entered thusfar", title="Game History")

class PlayerHistory(handler.BaseHandler):
    def get(self, player, page):
        if page is None:
            page = 0
        else:
            page = int(page[1:]) - 1
        PERPAGE = 10
        with db.getCur() as cur:
            cur.execute("SELECT Id,Name FROM Players WHERE Id = ? OR Name = ?", (player, player))
            player = cur.fetchone()
            if len(player) == 0:
                self.render("message.html", message="Couldn't find that player",
                            title="User Game History")
                return
            name = player[1]
            player = player[0]
            cur.execute("SELECT DISTINCT GameId FROM Scores WHERE PlayerId = ?"
                        "  ORDER BY Date DESC", (player,))
            games = [i[0] for i in cur.fetchall()]
            gamecount = len(games)
            if gamecount > 0:
                thesegames = games[min(page * PERPAGE, gamecount - 1):
                                   min(page * PERPAGE + PERPAGE, gamecount)]
                placeholder= '?' # For SQLite. See DBAPI paramstyle
                placeholders= ', '.join(placeholder for i in range(len(thesegames)))
                cur.execute(
                    "SELECT Scores.GameId,"
                    " strftime('%Y-%m-%d', Scores.Date), Rank, Players.Name,"
                    " Scores.RawScore / 1000.0, Scores.Score, Scores.Chombos,"
                    " Players.Id"
                    " FROM Scores INNER JOIN Players"
                    "  ON Players.Id = Scores.PlayerId"
                    " WHERE Scores.GameId IN (" + placeholders + ")"
                    " ORDER BY Scores.GameId, Rank ASC;", thesegames)
                rows = cur.fetchall()
                games = {}
                for row in rows:
                    gID, date, rank, name, rawScore, score, chombos, pID = row
                    if gID not in games:
                        games[gID] = {'date':date, 'scores':[],
                                      'id':gID, 'unusedPoints': 0}
                    if pID == scores.getUnusedPointsPlayerID():
                        games[gID]['unusedPoints'] = rawScore
                    else:
                        games[gID]['scores'].append(
                            (rank, name, rawScore, round(score, 2), chombos))
                maxpage = math.ceil(gamecount * 1.0 / PERPAGE)
                pages = range(max(1, page + 1 - 10),
                              int(min(maxpage, page + 1 + 10) + 1))
                games = sorted(games.values(),
                               key=lambda x: (x["date"], x["id"]), reverse=True)
                if page != 0:
                    prev = page
                else:
                    prev = None
                if page + 1 < maxpage:
                    nex = page + 2
                else:
                    nex = None
                self.render("userhistory.html",
                            error=None,
                            games=games,
                            curpage=page + 1,
                            pages=pages,
                            gamecount=gamecount,
                            ChomboPenalty=settings.CHOMBOPENALTY,
                            nex = nex,
                            prev = prev,
                            user = name,
                            player = player)
            else:
                self.render("message.html", message="No games entered thusfar", title="Game History", user = name)

class PointCalculator(handler.BaseHandler):
    def get(self):
        self.render("pointcalculator.html")

class Application(tornado.web.Application):
    def __init__(self, force=False):
        db.init(force=force)

        handlers = [
                (r"/", MainHandler),
                (r"/setup", login.SetupHandler),
                (r"/login", login.LoginHandler),
                (r"/logout", login.LogoutHandler),
                (r"/invite", login.InviteHandler),
                (r"/settings", login.SettingsHandler),
                (r"/verify/([^/]+)", login.VerifyHandler),
                (r"/reset", login.ResetPasswordHandler),
                (r"/reset/([^/]+)", login.ResetPasswordLinkHandler),
                (r"/leaderboard(/[^/]*)?", leaderboard.LeaderboardHandler),
                (r"/leaderdata(/[^/]*)?", leaderboard.LeaderDataHandler),
                (r"/ratings", ratings.RatingsHandler),
                (r"/ratingsdata", ratings.RatingsDataHandler),
                (r"/history(/[0-9]+)?", HistoryHandler),
                (r"/playerhistory/(.*?)(/[0-9]+)?", PlayerHistory),
                (r"/playerstats/([^/]+)/?([^/]+)?", playerstats.PlayerStatsHandler),
                (r"/playerstatsdata/([^/]+)/?([^/]+)?", playerstats.PlayerStatsDataHandler),
                (r"/players", players.PlayersHandler),
                (r"/seating", seating.SeatingHandler),
                (r"/seating/regentables", seating.RegenTables),
                (r"/seating/clearcurrentplayers", seating.ClearCurrentPlayers),
                (r"/seating/addcurrentplayer", seating.AddCurrentPlayer),
                (r"/seating/removeplayer", seating.RemovePlayer),
                (r"/seating/prioritizeplayer", seating.PrioritizePlayer),
                (r"/seating/currentplayers.json", seating.CurrentPlayers),
                (r"/seating/currenttables.json", seating.CurrentTables),
                (r"/seating/players.json", seating.PlayersList),
                (r"/seating/meetup", seating.AddMeetupPlayers),
                (r"/seating/meetup/oauth_authorize", seating.MeetupOAuthAuthorize),
                (r"/seating/meetup/oauth_redirect", seating.MeetupOAuthRedirect),
                (r"/addgame", seating.AddGameHandler),
                (r"/pointsettings", scores.PointSettings),
                (r"/timers", timers.TimersHandler),
                (r"/timers.json", timers.GetTimersHandler),
                (r"/timers/add", timers.AddTimer),
                (r"/timers/start", timers.StartTimer),
                (r"/timers/delete", timers.DeleteTimer),
                (r"/pointcalculator", PointCalculator),
                (r"/admin", admin.AdminPanelHandler),
                (r"/admin/users", admin.ManageUsersHandler),
                (r"/admin/editquarter/([^/]*)", admin.EditQuarterHandler),
                (r"/admin/quarters", admin.QuartersHandler),
                (r"/admin/deletequarter/([^/]*)", admin.DeleteQuarterHandler),
                (r"/admin/delete/([0-9]*)", admin.DeleteGameHandler),
                (r"/admin/edit/([0-9]*)", admin.EditGameHandler),
                (r"/admin/promote/([0-9]*)", admin.PromoteUserHandler),
                (r"/admin/demote/([0-9]*)", admin.DemoteUserHandler),
                (r"/version", version.VersionHandler),
        ]
        settings = dict(
                template_path = os.path.join(os.path.dirname(__file__), "templates"),
                static_path = os.path.join(os.path.dirname(__file__), "static"),
                debug = True,
                cookie_secret = cookie_secret,
                login_url = "/login"
        )
        tornado.web.Application.__init__(self, handlers, **settings)

def periodicCleanup():
    with db.getCur() as cur:
        cur.execute("DELETE FROM VerifyLinks WHERE Expires <= datetime('now')")
#        cur.execute("DELETE FROM Players WHERE Id NOT IN (SELECT PlayerId FROM Scores)")

def main():
    default_socket = "/tmp/mahjong.sock"
    socket = None
    force = False
    i = 1
    errors = []
    usage = ["usage: {0} [-f|--force] [tornado-options] [Port|Socket]",
             "positional arguments:",
             "  Port|Socket   Port number or unix socket to listen on",
             "                (default: {0})".format(default_socket),
             "",
             "optional arguments:",
             "  -f|--force    Force database schema updates without prompting",
             "                (default: {0})".format(force),
             "  -h|--help     show help information and exit",
             "",
             "tornado options:",
             ]
    usage = __doc__ + "\n" + "\n".join(usage)
    while i < len(sys.argv):
        if sys.argv[i].isdigit():
            if socket is None:
                socket = int(sys.argv[i])
            else:
                errors.append('Multiple port or socket arguments specified '
                              '"{0}"'.format(sys.argv[i]))
        elif sys.argv[i].startswith('-'):
            if sys.argv[i] in ['-f', '--force']:
                force = True
                del sys.argv[i]
                continue
            elif sys.argv[i] in ['-h', '--help']:
                print(usage)  # and don't exit so tornado help will print
                if sys.argv[i] == '-h':
                    sys.argv[i] = '--help' # tornado doesn't accept -h option
            else:
                pass  # Leave tornado options in place for later parsing
        else:
            if socket is None:
                socket = sys.argv[i]
            else:
                errors.append('Multiple port or socket arguments specified '
                              '"{0}"'.format(sys.argv[i]))
        i += 1

    if socket is None:
        socket = default_socket

    tornado.options.parse_command_line()
    if errors:
        print("\n  ".join(["Errors:"] + errors))
        sys.exit(-1)

    if hasattr(settings, 'EMAILSERVER'):
        qm = QueMail.get_instance()
        qm.init(settings.EMAILSERVER, settings.EMAILUSER,
                settings.EMAILPASSWORD, settings.EMAILPORT, 
                settings.EMAILUSETLS)
        qm.start()

    http_server = tornado.httpserver.HTTPServer(Application(force=force),
                                                max_buffer_size=24*1024**3)
    if isinstance(socket, int):
        http_server.add_sockets(tornado.netutil.bind_sockets(socket))
    else:
        http_server.add_socket(tornado.netutil.bind_unix_socket(socket, mode=stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IWGRP | stat.S_IROTH | stat.S_IWOTH))

    signal.signal(signal.SIGINT, sigint_handler)

    tornado.ioloop.PeriodicCallback(periodicCleanup, 60 * 60 * 1000).start() # run periodicCleanup once an hour
    # start up web server
    tornado.ioloop.IOLoop.instance().start()

    if qm is not None:
        qm.end()


def sigint_handler(signum, frame):
    tornado.ioloop.IOLoop.instance().stop()

if __name__ == "__main__":
    main()
