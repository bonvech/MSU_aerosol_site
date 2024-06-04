import logging

from flask import Flask
from flask_restful import Api

from msu_aerosol import config
from msu_aerosol.admin import init_admin, init_schedule
from msu_aerosol.commands import create_superuser
from msu_aerosol.models import db
from views.about import About
from views.archive import Archive, DeviceArchive
from views.contacts import Contacts
from views.device import DeviceDownload, DevicePage, DeviceUpload
from views.homepage import Home
from views.users import Login, Logout, Profile, Register

__all__: list = []

# Важнейшие переменные для управления приложением
app: Flask = config.initialize_flask_app(__name__)
api: Api = Api(app)
log = logging.getLogger('werkzeug')

# Настройка приложения
app.cli.add_command(create_superuser)
app.logger.setLevel(logging.INFO)

# Настройка логирования
log.disabled = True
logging.getLogger('apscheduler.executors.default').propagate = False
logging.basicConfig(
    level=logging.INFO,
    filename='download_log.log',
    filemode='w',
)

# Связь URL адресов с классами их представления
app.add_url_rule(
    '/',
    view_func=Home.as_view('home'),
)
app.add_url_rule(
    '/about',
    view_func=About.as_view('about'),
)
app.add_url_rule(
    '/archive',
    view_func=Archive.as_view('archive'),
)
app.add_url_rule(
    '/archive/<int:device_id>',
    view_func=DeviceArchive.as_view('device_archive'),
)
app.add_url_rule(
    '/contacts',
    view_func=Contacts.as_view('contacts'),
)
app.add_url_rule(
    '/devices/<int:device_id>',
    view_func=DevicePage.as_view('device'),
)
app.add_url_rule(
    '/devices/<int:device_id>/download',
    view_func=DeviceDownload.as_view('device_download'),
)
app.add_url_rule(
    '/devices/<int:device_id>/upload',
    view_func=DeviceUpload.as_view('device_upload'),
)
app.add_url_rule(
    '/profile',
    view_func=Profile.as_view('profile'),
)
app.add_url_rule(
    '/login',
    view_func=Login.as_view('login'),
)
app.add_url_rule(
    '/logout',
    view_func=Logout.as_view('logout'),
)
app.add_url_rule(
    '/register',
    view_func=Register.as_view('register'),
)

# Создание БД
with app.app_context():
    db.init_app(app)
    db.create_all()
    init_admin(app)
    init_schedule(None, None, None, app=app)


def main() -> None:
    app.run(use_reloader=False)


if __name__ == '__main__':
    main()
