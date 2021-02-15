MahjongSite
==========

A web site with various utilities for managing a riichi mahjong club's players
and scores.

Getting Started
===============

If you are copying this repository for the first time to set up your own
web site, there are few things you'll need to do to get your test system
up and running. You'll need to be familiar with Linux/Unix command line
operations to do most of this. For customizing the web site, it will be
helpful to understand Python program syntax and how to use text editors.

1. Find a host that can support Python, git, and sqlite3. Linux,
MacOS, and Windows all can support these tools, but you may have to
download some software to run these. Note: on MacOS, a missing low
level function, `sem_getvalue()`, prevents the email manager from
functioning.

1. Ensure you have some kind of `git` tool on your system
(https://git-scm.com/downloads). These can be either command line or
graphical user interface (GUI) based. In our examples below, we show
only the command line methods.

1. Clone this repository on your test system with a command like `git
clone https://github.com/BlaiseRitchie/MahjongSite.git`.

1. Ensure you have a Python 3 interpreter. You can get these from sites like:
    1. https://www.python.org/downloads/
    1. https://www.anaconda.com/distribution/ (anaconda)

1. One of the Python packages requires a C library, libgit2, which in turn
requires Cmake to install.  See
https://libgit2.github.com/ and
https://libgit2.github.com/docs/guides/build-and-link/ and
https://cmake.org/ for the software.
You will need to install cmake, and use it to build libgit2 before you
will be able to build/install pygit2 in the next step.
In MacOS, you can install cmake as a GUI tool with a DMG download.
Launch the GUI tool, and click on the Tools > 'How to install for
command line use' function to get the instructions for making
cmake available as a command line tool.  Follow the instructions
shown in the GUI. Then you can follow the libgit2 instructions on
how to build/install that module from the command line.

1. Ensure you have the extra Python packages needed to run the Mahjong
site code. The packages are listed in the `requirements.txt` file.
These are easy to install using the Python package installer program,
`pip` (see https://pip.pypa.io). Depending on how you installed Python 3,
you may already have `pip`, but if not, you can either install it
separately or use other methods to get the packages. If you use
`pip`, here's the command to install the needed modules.

    ```
    $ pip install -r requirements.txt
    ```

1. Create a `mysettings.py` file. This is where you customize the
parameters for running your local instance of the web site. Assuming
that your cloned repository is in `/path/to/MahjongSite`, run the
following commands:
    ```
    $ cd /path/to/MahjongSite
    $ cp defaults.py mysettings.py
    ```

1. Edit the `mysettings.py` file in the repository directory. You can
use any text editor but make sure you save any changes in plain text
format and are careful not to use a mixture of tabs and space
characters for indenting. Python programs use the indenting of lines
for the structure of the program and do not treat tab and space
characters equivalently. The `mysettings.py` file has only comments
(starting with a pound character, `#`) and assignments that all start
without any indent. Each setting is optional and will use the value
defined in the file `defaults.py` if it is not set in
`mysettings.py`. Change the information in the EMAIL section to point
to your **_outgoing_** email server. You can usually find this
information by looking at the settings of the program you use to
compose emails. You'll need the (smtp) host server name, the 'port'
that the host listens on for mail requests, and the email account name
and password that you use when accessing that server.

    1. Set the `EMAILSERVER` parameter to the server or host name.
       It can be a numeric address like 10.100.1.200, but must be inside
       of quote characters.
    2. Set the `EMAILPORT` to the port the server listens to for requests.
       This should not be inside of quotes.
    3. Set the `EMAILUSER` to an account the server recognizes, and provide
       the password for that account in `EMAILPASSWORD`.  The password
       must be recorded in clear text in this file, so you may need to
       control access of who can read the `mysettings.py` file.
    4. Set the `EMAILFROM` parameter to the alias that you want people to
       see in the emails they receive from the web site.

1. Start up the web server. On your test system, you'll want to run
this on some unused port on the machine. This should be a number
between 1024 and 65535. A common one to use is 8888, but if this port
is in use, you'll need to choose something else. Start the server with
the command `/path/to/MahjongSite/main.py 8888`. If you don't get any
error messages, then the web site should be up and running. If you get
errors like:

    1. "permission denied" - you may have chosen a port number outside
       the range 1024 to 65535. Your account needs elevated
       privileges to use ports below 1024 like the standard http port, 80.
    1. "port already in use" - you have chosen a port that some other
       program is using for network requests. Choose a different port.

1. Once the web server is running, open a browser and enter
`localhost:8888` (or maybe `http://localhost:8888`) in the address.
You will need to change the 8888 to whatever port you chose in the
previous step. If everything is working, you should get a web page
with several buttons including a "SETUP" button near the top and there
should be lines like `[I 170718 11:57:10 web:1971] 200 GET /static/css/style.css?v=23dde61ad8d450a9dfddb112a7d84bc9 (::1) 11.10ms` showing up in command
window where you ran the `main.py` program.

1. The first time the program is run, it will create a `scores.db` file in
the directory where you launched the `main.py` program. This might be
in the `/path/to/MahjongSite` directory or somewhere else if you change
the `DBFILE` parameter in `settings.py` or the current working directory
of the command shell where you launch the program. The `scores.db` is the
full database of the program. It will contain all the accumulated scores,
users, admin settings, etc. In the production system, this file should be
backed up.
The web server will make automatic backup copies of this database
in a folder (named by default 'backups') whenever significant
changes are made to the database.  There can be a lot of these
backup files over time for an active site.

1. The initial `scores.db` is empty. It has no users and no game
history. Clicking the "SETUP" button on the first web page will go to
a page where you can specify the email address for the first user.
After filling in the address and clicking "Invite", the web server
will attempt to send email to that address via the `EMAILSERVER` you
specified in `settings.py`. If everything succeeds, the email will
come through with a link to validate the user account. That account
will automatically be granted admin privileges (which can later be
taken away by any user with admin privileges).

1. When you want to run the web server for a long time and keep the
log in a file such as `web.log`, run `/path/to/MahjongSite/main.py
8888 > web.log 2>&1 &` The `2>&1` near the end puts both the standard
output and standard error text into the same log file. You can look
at the contents of this file with tools like `tail web.log` and `less
web.log` to track server activity and debug issues.


Updates
==========
When you update code, you do it in a fork of the repository and send
a "pull request" to the owners to merge your changes into the
main repo.  If you already know about repo's and forks and pull
requests, that will make sense.  If it's new to you.  You'll
need to spend time learing the intricacies of git.

When you do send pull requests, please run the beautify.sh script
in the main repo directory and commit any changes it makes.  This
runs a tool called `js-beautify` that formats the Javascript files
in a consistent manner.  That helps minimize changes involving
indentation and other whitespace that are hard to review in the
pull request.  The js-beautify tool comes in both Python and
Javascript implementations.  They perform slightly differently.
We prefer the one that works with node.js, the Javascript
interpreter, and that requires installing that tool, using
the node package manager, `npm`, to install js-beautify.


History
==========

This web site was originally developed by Blaise Ritchie for the
Seattle Riichi Mahjong Club. John Canning made contributions.
