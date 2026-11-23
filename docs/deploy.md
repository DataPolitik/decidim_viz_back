# Deploying Decidim.viz

This guide puts the whole dashboard (front end and back end) on one site, with
the data refreshed weekly from a Decidim instance's open-data export. It works
on any host that runs Python 3.13 and a WSGI application: a server of your
own, or a hosting service with Python support. `https://viz.example.org` stands
for your site's address below.

## How it is put together

One Django site runs the back end. With `DECIDIM_VIZ_FRONTEND_DIR` set, Django
also serves the built front end (through WhiteNoise): `/` is the dashboard,
`/stats/...` is the API. No second site, no cross-origin setup.

```
https://viz.example.org/          → front end (static files)
https://viz.example.org/stats/... → Django API
```

A scheduled task runs `refresh_from_open_data` once a week to download fresh
data and rebuild the networks.

Suggested layout in the home directory of the user that runs the site:

```
~/decidim_viz_back/   back end + venv/
~/frontend/           built front end
~/data/               db.sqlite3 and the network caches
~/decidim_viz.env     settings, shared by the site and the scheduled task
```

## What it needs

Measured with the data of meta.decidim.org (2,350 proposals, 4,208 comments):

| | Needed |
|---|---|
| Disk | ~260 MB of Python packages (SciPy ~135 MB, NumPy ~55 MB), 6 MB front end, ~2 MB database, ~20 MB temporary download per refresh |
| RAM | ~140 MB while serving or rebuilding the networks, ~70 MB while importing |
| Time | under a minute for a full refresh (download, import, networks) |

One web process with 256 MB of RAM is enough. Much larger instances (tens of
thousands of participants) need more memory while rebuilding the networks. No
Node.js is needed on the server: the front end is built elsewhere and uploaded.

## 1. Build the front end (on your computer)

```
git clone https://github.com/DataPolitik/decidim_viz_front
cd decidim_viz_front
git checkout v0.6.0.f            # or the release you deploy
npm ci --legacy-peer-deps
npx ng build
```

In `dist/decidim_viz_front/assets/config.json`, point the front end at the site
itself (the instance name and its GraphQL API come from the back end):

```json
{
  "host": "https://viz.example.org",
  "port": "443"
}
```

Copy `dist/decidim_viz_front` to `~/frontend` on the server (scp, SFTP, rsync).

## 2. Install the back end

```
cd ~
git clone https://github.com/DataPolitik/decidim_viz_back
cd decidim_viz_back
git checkout v0.6.0.b             # or the release you deploy
python -m venv venv
venv/bin/python -m pip install -r requirements.txt
mkdir -p ~/data/cache
```

## 3. Settings

Keep the Django secret key in a file of its own, so it never appears in an
environment listing or a hosting control panel:

```
umask 077
venv/bin/python -c "import secrets; print(secrets.token_urlsafe(50))" > ~/.decidim_viz_secret_key
```

Create `~/decidim_viz.env` (one `NAME=value` per line, `chmod 600`), with your
home directory in the paths:

```
DJANGO_DEBUG=0
DJANGO_SECRET_KEY_FILE=/home/<user>/.decidim_viz_secret_key
DJANGO_ALLOWED_HOSTS=viz.example.org
DJANGO_DB_PATH=/home/<user>/data/db.sqlite3
DECIDIM_VIZ_CACHE_DIR=/home/<user>/data/cache
DECIDIM_VIZ_FRONTEND_DIR=/home/<user>/frontend
OPENBLAS_NUM_THREADS=1
```

`OPENBLAS_NUM_THREADS=1` keeps NumPy/SciPy from reserving memory for many
threads. The README lists all the settings.

## 4. Create the database and load the data

```
cd ~/decidim_viz_back/decidim_viz_analysis
set -a; . ~/decidim_viz.env; set +a
../venv/bin/python manage.py migrate
../venv/bin/python manage.py refresh_from_open_data https://meta.decidim.org
```

`refresh_from_open_data` downloads the instance's open-data export
(`<instance>/open-data/download`), imports its proposals and comments, and
rebuilds both networks. Replace `https://meta.decidim.org` with the instance
you want to show; it can also take a local zip file.

## 5. Run the site

The WSGI application is `decidim_viz_analysis.wsgi:application` (the file
`decidim_viz_analysis/decidim_viz_analysis/wsgi.py`), run from the working
directory `~/decidim_viz_back/decidim_viz_analysis`, with the virtualenv
`~/decidim_viz_back/venv` and the variables of `~/decidim_viz.env`. One
process is enough.

- **On a hosting service with Python support**, create a Python/WSGI site with
  those values in its form. See the [alwaysdata example](#example-alwaysdata)
  below.
- **On your own server**, run a WSGI server such as gunicorn
  (`venv/bin/python -m pip install gunicorn`):

  ```
  cd ~/decidim_viz_back/decidim_viz_analysis
  set -a; . ~/decidim_viz.env; set +a
  ../venv/bin/gunicorn decidim_viz_analysis.wsgi:application --workers 1 --bind 127.0.0.1:8000
  ```

  Keep it running with your service manager (for systemd, the env file can be
  an `EnvironmentFile=`), and put a web server with HTTPS (nginx, Caddy,
  Apache) in front of it as a reverse proxy to `127.0.0.1:8000`.

Open `https://viz.example.org/`: the bar under the menu should say "Data from
meta.decidim.org". The API answers at `https://viz.example.org/stats/summary`.

The front end can also be hosted apart from the back end (any static host):
then leave `DECIDIM_VIZ_FRONTEND_DIR` unset, point `config.json` at the back
end's address, and set `DJANGO_CORS_ORIGINS` to the front end's origin.

## 6. Refresh the data weekly

Schedule this command, for example every Monday at 04:00 (`0 4 * * 1` in
crontab syntax):

```
cd /home/<user>/decidim_viz_back/decidim_viz_analysis && set -a && . /home/<user>/decidim_viz.env && set +a && /home/<user>/decidim_viz_back/venv/bin/python manage.py refresh_from_open_data https://meta.decidim.org
```

The site picks up new data on the next request; no restart is needed. The data
is as fresh as the instance's export, which Decidim usually regenerates once a
day. The import adds and updates but never removes: proposals, comments and
endorsements that later disappear from the export (withdrawn, deleted or
hidden) stay in the database.

## Updating to a new release

```
cd ~/decidim_viz_back && git fetch --tags && git checkout <new tag>
venv/bin/python -m pip install -r requirements.txt
cd decidim_viz_analysis && set -a && . ~/decidim_viz.env && set +a
../venv/bin/python manage.py migrate
../venv/bin/python manage.py refresh_from_open_data https://meta.decidim.org
```

Then restart the site. For a new front end, build it again (step 1) and replace
`~/frontend` (keep your `assets/config.json`).

## Example: alwaysdata

This setup runs at https://decidimviz.alwaysdata.net on alwaysdata's free plan
(1 GB of disk, 256 MB of RAM, for non-profit use, on an `alwaysdata.net`
address only). What is specific to alwaysdata, with `<account>` your account
name:

- **SSH:** enable it in **Remote access › SSH/SFTP**, then
  `ssh <account>@ssh-<account>.alwaysdata.net`. Always use `python` (never
  `python3`); the version is set in **Environment › Python**.
- **Site:** in **Web › Sites**, edit the default site of
  `<account>.alwaysdata.net` (or add one), type **Python WSGI**. The three
  paths are relative to your home directory: write them without
  `/home/<account>/`, or uWSGI looks for `/home/<account>/home/<account>/...`
  and the site answers 502.
  - **Application path:** `decidim_viz_back/decidim_viz_analysis/decidim_viz_analysis/wsgi.py`
  - **Working directory:** `decidim_viz_back/decidim_viz_analysis`
  - **Virtualenv directory:** `decidim_viz_back/venv`
  - **Python version:** 3.13
  - **Environment variables:** the lines of `~/decidim_viz.env` on one line,
    separated by spaces (`DJANGO_DEBUG=0 DJANGO_SECRET_KEY_FILE=... ...`)
- **Weekly refresh:** **Advanced › Scheduled tasks**, type "Execute the
  command", crontab syntax `0 4 * * 1` (shortcuts like `@weekly` are not
  accepted). A report is mailed when the task fails if you add an address.
- **Restart** after an update: the Restart button in **Web › Sites**.
- **Logs:** `~/admin/logs/uwsgi/<site id>.log` for the site,
  `~/admin/logs/jobs/` for scheduled tasks.
- Idle sites are stopped after 30 minutes, so the first visit after a pause
  takes a few seconds while Python loads.
