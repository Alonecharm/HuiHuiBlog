import os

from base import read_config

__all__ = ['config']

basedir = os.path.abspath(os.path.dirname(__file__))


INSTANCE_PATH = os.path.abspath(os.path.dirname(__file__))
SETTING_FILE = os.path.join(INSTANCE_PATH, 'conf/config.json')
PROJECT_NAME = 'huihui'

config = read_config(PROJECT_NAME, SETTING_FILE)