#!/usr/bin/env python
# coding:utf8
"""
作者:刘洋
邮箱:x@icexz.com
微信:475090118
日期:16-10-18
时间:上午11:42
"""
import pickle
from functools import wraps
from logging import getLogger

from flask_sqlalchemy import Model
from redis import StrictRedis
from redlock import Redlock

# from zeroso.base.extensions.internal_rpc import compress
from app.errors import BaseError

logger = getLogger(__name__)


def get_params(kwargs, id_field, available_fields):
    params = {}
    for k in available_fields:
        if k not in kwargs:
            raise Exception('param_fields key error, %s not in kwargs' % k)

        # support args flat
        if k == 'args':
            params.update(kwargs['args'])
        elif k == id_field:
            pass
        else:
            params[k] = kwargs[k]

    return params


class RedisCache(object):
    redis = None
    _instance = None
    _initialized = False
    _is_cached_on = False

    def __init__(self, app=None):
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        self.app = app
        if not self._initialized:
            logger.info('Redis Cache Started')
            url = 'redis://%s:%s/%s' % (app.config['REDIS_HOST'], app.config['REDIS_PORT'], app.config['REDIS_CACHE_DB'])
            self.redis = StrictRedis.from_url(url)
            self._initialized = True
            self._is_cached_on = app.config.get('REDIS_CACHE_ON', False)
            self.lock = Redlock([{'host': app.config['REDIS_HOST'], 'port': app.config['REDIS_PORT'], 'db': app.config['REDIS_CACHE_DB']}])

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(RedisCache, cls).__new__(cls)
        return cls._instance

    @staticmethod
    def _get_sorted_hash_key(resource_type, params):
        if not resource_type:
            raise Exception('Resource Type is not allow none or empty')

        if params is None:
            params = {}
        # pre format params
        params = {str(k): v for k, v in params.items()}
        sorted_params = [(k, params[k]) for k in sorted(params.keys())]
        sorted_params_string = ('?' + '&'.join(['%s=%s' % (_[0], _[1]) for _ in sorted_params])) if sorted_params else ''

        return '%s%s' % (resource_type, sorted_params_string)

    @staticmethod
    def _get_sorted_name(model, oid):
        if not model:
            raise Exception('no model defined!')
        if not oid:
            raise Exception('no oid defined!')
        return '%s:%s' % (model, oid)

    def _set(self, model, oid, resource_type, params=None, value=None):
        name = self._get_sorted_name(model, oid)
        hash_key = self._get_sorted_hash_key(resource_type, params)
        try:
            set_value = pickle.dumps(value)
        except (pickle.PickleError, TypeError, AttributeError):
            logger.exception("pickle dumps data error")
            logger.error(f'缓存dumps出错, value为{value}')
        else:
            self.redis.hset(name, hash_key, set_value)
            logger.debug(f'设置缓存:hash_key:{hash_key},value:{value}')

    def _get(self, model, oid, resource_type, params=None):
        name = self._get_sorted_name(model, oid)
        hash_key = self._get_sorted_hash_key(resource_type, params)
        logger.debug(f'hash_key={hash_key}')
        result = self.redis.hget(name, hash_key)
        logger.debug(result)
        return pickle.loads(result) if result else result

    def _exists(self, model, oid, resource_type, params=None):
        name = self._get_sorted_name(model, oid)
        hash_key = self._get_sorted_hash_key(resource_type, params)
        return self.redis.hexists(name, hash_key)

    def delete(self, model, oid, resource_type=None, params=None):
        if resource_type:
            name = self._get_sorted_name(model, oid)
            hash_key = self._get_sorted_hash_key(resource_type, params)
            self.redis.hdel(name, hash_key)
        elif oid:
            name = self._get_sorted_name(model, oid)
            self.redis.delete(name)
        else:
            # get key list
            self.redis.delete(self.redis.scan('%s:*'))
        logger.debug("删除缓存成功")

    def expire(self, model, oid, time=1):
        if not oid:
            self.redis.delete(self.redis.scan('%s:*'))
        name = self._get_sorted_name(model, oid)

        if self.redis.ttl(name) < 0:
            self.redis.expire(name, time)

        logger.debug(f"设置缓存过期{time}")

    def cache_with_id(self, table_model=None, id_field='oid', param_fields=None, is_grpc=False):
        def decorator(f):
            @wraps(f)
            def wrapper(*args, **kwargs):
                logger.debug(f'args:{args},kwargs:{kwargs}')
                method_name = f.__name__
                if args and isinstance(args[0], Model):
                    oid = args[0].id
                    model = args[0].__tablename__
                else:
                    model = table_model
                    oid = kwargs.get(id_field, None)
                if not oid:
                    return f(*args, **kwargs)
                if param_fields:
                    # if no param_fields defined, use all params except id_field
                    params = get_params(kwargs, id_field, param_fields)
                else:
                    params = get_params(kwargs, id_field, kwargs.keys())

                if not self._exists(model, oid, method_name, params):

                    get_lock_number = 0
                    while get_lock_number < 10:
                        # if cache exist
                        cache_lock = self.lock.lock('redis', 15000)
                        if not cache_lock:
                            get_lock_number += 1
                            logger.debug(f'第{get_lock_number}次获取锁失败')
                            continue
                        logger.debug("获取锁成功")
                        response = f(*args, **kwargs)
                        if is_grpc:
                            raise BaseError('grpc api')
                            # compress(response)
                        # 根据缓存的函数返回值, 写入到缓存中
                        self._set(model, oid, method_name, params, response)
                        self.lock.unlock(cache_lock)

                        logger.debug("释放锁成功")
                        return response

                    raise BaseError("获取锁失败")

                result = self._get(model, oid, method_name, params)

                return result

            return wrapper

        return decorator


cache = RedisCache()
