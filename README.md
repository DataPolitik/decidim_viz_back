Note: As future.eu is not longer active, Decidim.viz is not working anymore. Nevertheless, the code can be usted to retrieve data from others Decidim instances.

# Decidim Viz - Back

This repository contains the back-end part of Decidim.viz (http://viz.platoniq.net/). This projects aims to develop a dashboard to extract data from Decidim instances (https://meta.decidim.org/). 

## What is Decidim.viz? 

This repository contains the front-end part of Decidim.viz (http://viz.platoniq.net/). This projects aims to develop a dashboard to extract data from Decidim instances (https://meta.decidim.org/). 

Decidim.viz is a dashboard for an instance of Decidim. The objective of Decidim.viz is to provide useful visualizations, metrics and statistical information to interested people.

Decidim.viz is a project promoted by Tecnopolitica.net (research unit Communication Networks and Social Change of Interdisciplinary Internet Institute group at the Universitat Oberta de Catalunya), with the sponsorship of the Office for Digital and Democratic Innovation of the Barcelona city council, and support of initiatives such as the association Heuristica.barcelona and the Platoniq Foundation, in the context of the D2, Data Space and Democracy, its broader aim is to prototype a tool that may contribute to make democratic participation on the Decidim platform more transparent and reflective. 



## Requirements

This back-end is coded in Python + Django. So you need to install Python in your computer. After that, you need to install Django in a environment (or a virtual environment, please see https://docs.python.org/3/tutorial/venv.html) of Python. 

After Python is installed, you will need to get all the requirements listed in the requirements.txt file.

`pip install -r requirements.txt`

## Configuration

Settings live in `decidim_viz_analysis/decidim_viz_analysis/settings.py` and are read from environment variables, so no secret needs to be committed:

| Variable | Default | Purpose |
|---|---|---|
| `DJANGO_SECRET_KEY` | dev-only key | Required when `DJANGO_DEBUG=0` |
| `DJANGO_DEBUG` | `1` | Set to `0` in production |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated |
| `DJANGO_CORS_ORIGINS` | empty (all origins allowed in debug) | Origin(s) of the front end |
| `DJANGO_DB_PATH` | `db.sqlite3` | SQLite database file |
| `DECIDIM_VIZ_CACHE_DIR` | `stats/cache` | Where the network caches are written |

## Executing

From `decidim_viz_analysis/`:

```
python manage.py migrate
python manage.py load_endorses_from_csv proposals.csv   # Decidim proposals export (";"-separated)
python manage.py load_comments_from_csv comments.csv    # Decidim comments export, after the proposals
python manage.py generate_endorses_cache                # phi networks, see below
python manage.py generate_comments_cache
python manage.py runserver
```

Run `python manage.py test` to run the tests.

## Co-participation networks

`/stats/endorsements/` and `/stats/comments/` return a user-user network: two users are linked when they endorse (or comment on) the same proposals significantly more often than chance.

For users A and B who took part in `a` and `b` of the `n` proposals, sharing `n11` of them, the p-value is `P(X >= n11)` with `X ~ Hypergeometric(n, a, b)`, i.e. a one-sided Fisher exact test. Every pair of active users counts as one test, and the p-values are corrected for multiple testing with `--correction fdr` (Benjamini-Hochberg, the default), `bonferroni` or `none`, at level `--alpha` (default 0.05). Edges are weighted by the phi coefficient `(n*n11 - a*b) / sqrt(a*b*(n-a)*(n-b))`; communities are found with Louvain on those weights (`--seed`, default 42), and the response includes their modularity. `/stats/comments/modularity` and `/stats/endorsements/modularity` return just `{"modularity": ...}`, as the front end's Interactions page expects.

The networks are cached; re-run the `generate_*_cache` commands after importing new data. If no cache exists, the first request computes it.

## About the back-end application

This back-end read the data from a database and then send it to other application by using a REST API. https://github.com/DataPolitik/decidim_viz_front is a front-end application written in Typescript + Angular that we are also developing.


## Can I contribute?

Sure, please, go to the issues section (https://github.com/DataPolitik/decidim_viz_front/issues) to see pending task, if you need inspiration. Also, you can propose new tasks by creating a new issue. Please, feel free to implement your contribution and, then, creating a pull request (https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/proposing-changes-to-your-work-with-pull-requests/creating-a-pull-request). 

Finally, you can take a look to the document "Desarrollo de Decidim.Viz.pdf" to see the current technical status of the project as well as limitations found.
