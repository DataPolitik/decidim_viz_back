"""
WSGI config for decidim_viz_analysis project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/4.0/howto/deployment/wsgi/
"""

import os,sys


from django.core.wsgi import get_wsgi_application

sys.path.append('/home/jorge/decidim_vis/decidim_viz_back/decidim_viz_analysis')
os.environ['DJANGO_SETTINGS_MODULE'] = "decidim_viz_analysis.settings"

#os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'decidim_viz_analysis.settings')

os.environ.setdefault("LANG", "en_US.UTF-8")
os.environ.setdefault("LC_ALL", "en_US.UTF-8")

#activamos nuestro virtualenv
activate_this = "/home/jorge/decidim_vis/decidim_viz_back/venv/bin/activate_this.py"
exec(open(activate_this).read(), dict(__file__=activate_this))

#obtenemos la aplicación
from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
