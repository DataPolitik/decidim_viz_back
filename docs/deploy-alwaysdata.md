# Deploying Decidim.viz on alwaysdata (free plan)

This guide puts the whole dashboard (front end and back end) on one alwaysdata
site, `https://<account>.alwaysdata.net`, with the data refreshed weekly from a
Decidim instance's open-data export. `<account>` is your alwaysdata account name
everywhere below.

## Does it fit the free plan?

The free plan gives 1 GB of disk, 256 MB of RAM and ¼ CPU, for non-profit use,
on an `alwaysdata.net` address only (no custom domain). Measured with the data
of meta.decidim.org (2,350 proposals, 4,208 comments):

| | Needed |
|---|---|
| Disk | ~260 MB of Python packages (SciPy ~135 MB, NumPy ~55 MB), 6 MB front end, ~2 MB database, ~20 MB temporary download per refresh |
| RAM | ~135 MB while serving or rebuilding the networks, ~70 MB while importing |
| Time | ~20 s for a full refresh (download, import, networks) |

So one web process fits. Much larger instances (tens of thousands of
participants) may exceed 256 MB while rebuilding the networks; the "Small" paid
plan (1 GB RAM) then has ample room. Idle sites are stopped after 30 minutes,
so the first visit after a pause takes a few seconds while Python loads.

## How it is put together

One **Python WSGI** site runs the Django back end. With
`DECIDIM_VIZ_FRONTEND_DIR` set, Django also serves the built front end (through
WhiteNoise): `/` is the dashboard, `/stats/...` is the API. No second site, no
cross-origin setup.

```
https://<account>.alwaysdata.net/          → front end (static files)
https://<account>.alwaysdata.net/stats/... → Django API
```

Layout in the account's home directory:

```
/home/<account>/decidim_viz_back/   back end (git clone) + venv/
/home/<account>/frontend/           built front end (uploaded)
/home/<account>/data/               db.sqlite3 and the network caches
/home/<account>/decidim_viz.env     settings, shared by the site and the scheduled task
```

## 1. Build the front end (on your computer)

alwaysdata doesn't need Node: build locally and upload only the result.

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
  "host": "https://<account>.alwaysdata.net",
  "port": "443"
}
```

## 2. Open SSH access

In the alwaysdata admin, **Remote access › SSH/SFTP**, enable an SSH user (or
add your key). Then:

```
ssh <account>@ssh-<account>.alwaysdata.net
```

Upload the front end from your computer (SFTP works too):

```
scp -r dist/decidim_viz_front <account>@ssh-<account>.alwaysdata.net:frontend
```

## 3. Install the back end (over SSH)

alwaysdata asks to always use `python` (never `python3`), with the version set
in **Environment › Python** (Decidim.viz is tested with 3.13).

```
cd ~
git clone https://github.com/DataPolitik/decidim_viz_back
cd decidim_viz_back
git checkout v0.6.0.b             # or the release you deploy
python -m venv venv
venv/bin/python -m pip install -r requirements.txt
mkdir -p ~/data/cache
```

## 4. Settings

Keep the Django secret key in a file of its own, so it never appears in the
admin panel:

```
umask 077
venv/bin/python -c "import secrets; print(secrets.token_urlsafe(50))" > ~/.decidim_viz_secret_key
```

Create `~/decidim_viz.env` (one `NAME=value` per line, `chmod 600`):

```
DJANGO_DEBUG=0
DJANGO_SECRET_KEY_FILE=/home/<account>/.decidim_viz_secret_key
DJANGO_ALLOWED_HOSTS=<account>.alwaysdata.net
DJANGO_DB_PATH=/home/<account>/data/db.sqlite3
DECIDIM_VIZ_CACHE_DIR=/home/<account>/data/cache
DECIDIM_VIZ_FRONTEND_DIR=/home/<account>/frontend
OPENBLAS_NUM_THREADS=1
```

`OPENBLAS_NUM_THREADS=1` keeps NumPy/SciPy from reserving memory for many
threads.

## 5. Create the database and load the data

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

## 6. Create the site

In **Web › Sites**, edit the default site of `<account>.alwaysdata.net` (or add
one). The three paths are relative to your home directory: write them without
`/home/<account>/`, or uWSGI looks for `/home/<account>/home/<account>/...` and
the site answers 502.

- **Type:** Python WSGI
- **Addresses:** `<account>.alwaysdata.net`
- **Application path:** `decidim_viz_back/decidim_viz_analysis/decidim_viz_analysis/wsgi.py`
- **Working directory:** `decidim_viz_back/decidim_viz_analysis`
- **Virtualenv directory:** `decidim_viz_back/venv`
- **Python version:** 3.13
- **Environment variables:** the lines of `~/decidim_viz.env` on one line,
  separated by spaces (`DJANGO_DEBUG=0 DJANGO_SECRET_KEY_FILE=... ...`)

Open `https://<account>.alwaysdata.net/`: the bar under the menu should say
"Data from meta.decidim.org". The API answers at
`https://<account>.alwaysdata.net/stats/summary`.

## 7. Refresh the data weekly

In **Advanced › Scheduled tasks**, add a **command** task, for example every
Monday at 04:00 (`0 4 * * 1`; shortcuts like `@weekly` are not accepted):

```
cd /home/<account>/decidim_viz_back/decidim_viz_analysis && set -a && . /home/<account>/decidim_viz.env && set +a && /home/<account>/decidim_viz_back/venv/bin/python manage.py refresh_from_open_data https://meta.decidim.org
```

The site picks up new data on the next request; no restart is needed. The
import adds and updates but never removes: proposals, comments and endorsements
that later disappear from the export (withdrawn, deleted or hidden) stay in the
database. A report
is mailed when the task fails (non-zero exit), if you add an address to it.

## Logs

- Site errors: `/home/<account>/admin/logs/uwsgi/<site id>.log`
- Scheduled tasks: `/home/<account>/admin/logs/jobs/`

## Updating to a new release

```
cd ~/decidim_viz_back && git fetch --tags && git checkout <new tag>
venv/bin/python -m pip install -r requirements.txt
cd decidim_viz_analysis && set -a && . ~/decidim_viz.env && set +a
../venv/bin/python manage.py migrate
../venv/bin/python manage.py refresh_from_open_data https://meta.decidim.org
```

Then click **Restart** on the site (Web › Sites). For a new front end, build it
again (step 1) and replace `~/frontend` (keep your `assets/config.json`).

## Tested

This setup runs at https://decidimviz.alwaysdata.net (free plan, Python 3.13,
data from meta.decidim.org).
