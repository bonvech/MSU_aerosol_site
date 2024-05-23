import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask

__all__: list = []

load_dotenv()
basedir: Path = Path(os.path.dirname(__file__)).resolve().parent
yadisk_token: str = os.getenv('YADISK_TOKEN', default='FAKE_TOKEN')
upload_folder = 'received_data'
allowed_extensions = {'csv', 'xlsx'}


class Config:
    SECRET_KEY: str = os.getenv(
        'SECRET_KEY',
        default='FAKE_SECRET_KEY',
    )
    SQLALCHEMY_DATABASE_URI: str = 'sqlite:///database.db'
    SESSION_COOKIE_NAME: str = os.getenv(
        'SESSION_COOKIE_NAME',
        default='FAKE_SESSION_COOKIE_NAME',
    )
    STATIC_FOLDER: Path = basedir / 'static'
    SQLALCHEMY_TRACK_MODIFICATIONS: bool = True
    TEMPLATES_AUTO_RELOAD: bool = True


class ProdConfig(Config):
    FLASK_ENV: str = 'production'
    DEBUG: bool = False


class DevConfig(Config):
    FLASK_ENV: str = 'development'
    DEBUG: bool = True


def initialize_flask_app(filename: str) -> Flask:
    app: Flask = Flask(
        filename,
        instance_relative_config=False,
        static_folder=Config.STATIC_FOLDER,
    )
    app.config.from_object(ProdConfig)
    return app
