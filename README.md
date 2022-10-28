# Decidim Viz - Back

This repository contains the back-end part of Decidim.viz (http://viz.platoniq.net/). This projects aims to develop a dashboard to extract data from Decidim instances (https://meta.decidim.org/). 

## Requirements

This back-end is coded in Python + Django. So you need to install Python in your computer. After that, you need to install Django in a environment (or a virtual environment, please see https://docs.python.org/3/tutorial/venv.html) of Python. 

After Python is installed, you will need to get all the requirements listed in the requirements.txt file.

`pip install -r requirements.txt`

## Executing

Run `python manage.py runserver` to run the back-end in your localhost.

## About the back-end application

This back-end read the data from a database and then send it to other application by using a REST API. https://github.com/DataPolitik/decidim_viz_back is a front-end application written in Typescript + Angular that we are also developing.


## Can I contribute?

Sure, please, go to the issues section (https://github.com/DataPolitik/decidim_viz_front/issues) to sse pending task, if you need inspiration. Also, you can propose new tasks by creating a new issue. Please, feel free to implement your contribution and, then, creating a pull request (https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/proposing-changes-to-your-work-with-pull-requests/creating-a-pull-request). 

Finally, you can take a look to the document "Desarrollo de Decidim.Viz.pdf" to see the current technical status of the project as well as limitations found.
