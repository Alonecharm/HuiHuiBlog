# !/usr/bin/env python
# -*- coding:utf-8 -*-
import inspect
import json
import logging
import os

import flask_migrate
import redis
import requests
import shutil

from colorlog import colorlog
from flask import Flask
from flask_principal import identity_loaded
from flask_session import Session
from gunicorn.app.base import Application

from app.cache import cache
from app.database import db
from app.principal import on_identity_loaded, principal_config

log = logging.getLogger(__name__)
__all__ = [
    'init_app',
    'db',
    'read_config'
]


def read_config(module_name: str, config_file=None) -> dict:
    """
    从配置服务器取配置
    :param config_file: 例如conf/config.json
    :param module_name: 例如zeroso.message
    """
    if not config_file:
        config_file = 'conf/config.json'

    mode = os.getenv('MODE', '').lower()
    mode = mode if mode else 'local'

    if mode == 'local':
        if os.getenv('PYCHARM_HOSTED') is None:
            if not input('确定使用本地配置？(Y/N)').lower() == 'y':
                exit(-1)
        log.info('read config from local (conf/config.json)')
        print('read config from local (conf/config.json)')
        if not os.path.isfile(config_file):
            raise FileNotFoundError(config_file)

        with open(config_file)as f:
            return json.load(f)
    elif mode == 'product':
        config_file = 'product_conf_long_dir_name_you_will_not_found/config.json'
        log.info('read product config from local (%s)', config_file)
        print('read product config from local (%s)' % config_file)
        if not os.path.isfile(config_file):
            raise FileNotFoundError(config_file)

        with open(config_file)as f:
            return json.load(f)
    else:
        config_uri = 'http://config.0so.com/{module_name}/{mode}/config.json'.format(
            mode=mode, module_name=module_name
        )

        log.info('read config from %s', config_uri)
        print('read config from %s' % config_uri)

        r = requests.get(config_uri)
        r.raise_for_status()
        return r.json()


def init_app(app):
    init_logger(app)
    log.info('Base Init App')
    db.init_app(app)
    init_redis_session(app)
    # configure_webargs_error_handler(app)
    _configure_principal(app)
    # remote
    # client.init_app(app)
    # _configure_internal_service(app)
    manager.init_app(app, db)
    cache.init_app(app)
    # permission.init_app(app)
    # internal_rpc.init_app(app)


# def _configure_internal_service(app):
#     internal_client.init_app(app)
#     internal_server.init_app(app)


def _configure_principal(app):
    principal_config.init_app(app)
    identity_loaded.connect(on_identity_loaded, app)


def add_to_rules(app, rules, url_prefix=''):
    for rule in rules:
        if len(rule) != 4:
            raise Exception('rule is not correctly defined: %s' % rule)

        if inspect.isclass(rule[2]):
            app.add_url_rule(rule=url_prefix + rule[0], view_func=rule[2].as_view(rule[1]), methods=rule[3])
        else:
            app.add_url_rule(rule=url_prefix + rule[0], endpoint=rule[1], view_func=rule[2], methods=rule[3])


def init_logger(app=None):
    """
    """

    root_logger = logging.root
    root_logger.handlers.clear()
    if app:
        app.logger.handlers.clear()
        app.logger.propagate = 1
    logging.basicConfig()
    root_logger.handlers[0].setFormatter(get_formatter())
    root_logger.setLevel(int(os.getenv('LOG_LEVEL') or 0))
    if app:
        if not app.config.get('SYSLOG_ENABLED', None):
            root_logger.debug('SYSLOG NOT ACTIVE')
            return

    root_logger.info('SYSLOG ACTIVE')
    # syslog_handler.setFormatter(JsonLogFormatter())


def get_formatter():
    return colorlog.ColoredFormatter(
        (
            '%(asctime)s'
            '[%(log_color)s%(levelname).4s%(reset)s] '
            '[%(cyan)s%(name)s%(reset)s] '
            '%(message_log_color)s%(message)s'
        ),
        reset=True,
        log_colors={
            'DEBUG': 'bold_cyan',
            'INFO': 'bold_green',
            'WARNING': 'bold_yellow',
            'ERROR': 'bold_red',
            'CRITICAL': 'bold_red,bg_white',
        },
        secondary_log_colors={
            'message': {
                'DEBUG': 'bold_blue',
                'INFO': 'bold_white',
                'WARNING': 'bold_yellow',
                'ERROR': 'bold_red',
                'CRITICAL': 'bold_red',
            },
        },
        style='%'
    )


def init_redis_session(app):
    if app.config.get('SESSION_TYPE') == 'redis':
        host = app.config['REDIS_HOST']
        port = app.config.get('REDIS_PORT', 6379)
        db = app.config.get('REDIS_DB', 0)
        redis_server = redis.StrictRedis(host=host, port=int(port), db=int(db))
        app.config['SESSION_REDIS'] = redis_server
        Session(app)


class Manager(object):
    def __init__(self):
        self.db = None
        self.migrate = None
        self.app = None
        self.command = None  # type:AppGroup

    def init_app(self, app: Flask, db):
        log.info('Base Init Command')
        self.app = app
        self.db = db
        self.migrate = flask_migrate.Migrate(app, db)

        def command(f):
            app.cli.command()(f)
            return f

        self.command = command
        self.configure_defaul_commands()

    def main(self):
        log.info('启动app')
        return self.app

    def configure_defaul_commands(self):
        conf = {k.upper(): v for k, v in self.app.config.items()}
        app = self.app  # type:Flask
        db = self.db

        @self.command
        def uwsgi():
            uwsgi_bin = 'uwsgi '
            options = ' '.join(conf['UWSGI']['options'])
            arguments = ' '.join(['{} {}'.format(k, v) for k, v in conf['UWSGI']['arguments'].items()])
            command = uwsgi_bin + arguments + ' ' + options
            log.info('uwsgi command:  ' + command)
            os.system(f'exec {command}')

        class MyGunicornApplication(Application):
            def init(self, *args, **kwargs):
                cfg = {}
                for k, v in self.options.items():
                    if k.lower() in self.cfg.settings and v is not None:
                        cfg[k.lower()] = v
                return cfg

            def load(self):
                return app

            def __init__(self, options):
                self.options = options
                super().__init__()

        @self.command
        def gunicorn():
            MyGunicornApplication(
                {
                    'bind': '{app[HOST]}:{app[PORT]}'.format(app=conf['APP']),
                    'worker_class': 'gevent',
                    'reload': True,
                    'workers': 8,
                }).run()

        @manager.command
        def db_fast_upgrade():
            def drop_table(table_name):
                engine = db.engine
                connection = engine.raw_connection()
                cursor = connection.cursor()
                command = "DROP TABLE IF EXISTS {};".format(table_name)
                cursor.execute(command)
                connection.commit()
                cursor.close()

            mode = os.getenv('MODE', '').lower()
            mode = 'local' if not mode else mode
            if mode not in ['test', 'local', 'dev']:
                log.critical('not allow to run ')
                exit()

            try:
                shutil.move('migrations/versions', 'migrations/versions_backup')
            except Exception as e:
                log.warning('move migrations/versions file error')
                shutil.rmtree('migrations/versions', ignore_errors=True)

            drop_table('alembic_version')

            os.makedirs('migrations/versions', exist_ok=True)

            flask_migrate.migrate()
            input('请在其他窗口编辑migrations文件，然后回车继续(Enter)')
            flask_migrate.upgrade()

            shutil.rmtree('migrations/versions', ignore_errors=True)

            try:
                shutil.move('migrations/versions_backup', 'migrations/versions')
            except Exception as e:
                log.warning('migrations/versions_backup file not exist')

            db.session.commit()
            db.session.remove()
            db.engine.dispose()

        @manager.command
        def test():
            import subprocess
            if not os.getenv('MODE', '').lower() in ['test', 'local']:
                log.critical('Not Runing ')
                exit()
            exit(subprocess.call(['nosetests',
                                  '--with-coverage',
                                  '-x',
                                  '--cover-erase',
                                  '--cover-html',
                                  f'--cover-package={app.name}',
                                  ],
                                 stderr=subprocess.STDOUT))


manager = Manager()