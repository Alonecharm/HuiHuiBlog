import logging

import flask
import os

# from app.database import import_any_model


def base_init_app(app):
    pass


def create_app(conf):
    logging.getLogger('urllib3.connectionpool').setLevel(30)
    logging.getLogger('urllib3.util.retry').setLevel(30)
    app = flask.Flask(__name__)
    if os.getenv('USER') == 'liuyang' and os.getenv('MODE') == 'test':
        conf['db']['DATABASE_NAME'] = 'message'
    uri = 'mysql+mysqlconnector://{DATABASE_USER}:{DATABASE_PWD}@' \
          '{DATABASE_HOST}:{DATABASE_PORT}/{DATABASE_NAME}?charset=utf8mb4'.format(**conf['db'])
    app.debug = conf['app']['DEBUG']
    app.config.from_mapping(conf)
    app.config['INTERNAL_HOSTS'] = conf['internal_hosts']
    app.config['APP'] = conf['app']
    app.config['UWSGI'] = conf['uwsgi']
    app.config.from_mapping(conf['db'])
    app.config.from_mapping(conf['app'])
    app.config.from_mapping(conf['sqlalchemy'])
    app.config.from_mapping(conf['log'])
    app.config.from_mapping(conf['redis'])
    app.config.from_mapping(conf['elastic'])
    app.config.from_mapping(conf['jira'])
    # app.config['CACHE_REDIS_URL'] = conf['CACHE_REDIS_URL']
    app.config['SQLALCHEMY_DATABASE_URI'] = uri
    # import_any_model('message')
    # base_init_app(app)

    # api.add_namespace(mail_api.ns)

    # configure_member_blueprints(app)
    # configure_elastic_search(app)
    # config_model_processors(app)
    # # log.warning(repr(app.url_map))
    return app