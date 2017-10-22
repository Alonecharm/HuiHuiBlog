# -*- coding:utf-8 -*-
import hashlib
import itertools
import json
import os
import uuid
import sqlalchemy.sql.schema
import sqlalchemy.sql.sqltypes
import sqlalchemy.orm.properties
from logging import getLogger

from flask_sqlalchemy import SQLAlchemy, _SessionSignalEvents, SignallingSession, before_models_committed
from sqlalchemy import event
from sqlalchemy import inspect
from sqlalchemy import types
from sqlalchemy import text

from sqlalchemy.dialects import mysql
from sqlalchemy.orm import ColumnProperty
from sqlalchemy.orm import object_mapper
from sqlalchemy.orm.session import Session as SessionBase
from sqlalchemy.ext.declarative.base import declared_attr

log = getLogger(__name__)


def import_any_model(module_name):
    log.info('Base load modules')
    import pkgutil
    for m in pkgutil.walk_packages('.'):
        try:
            __import__(m[1])
        except ImportError:
            pass


def sha256sum(string):
    return hashlib.sha256(string.encode('utf-8')).hexdigest()


class JSONEncodedDict(types.TypeDecorator):
    """
    Represents an immutable structure as a json-encoded string.

    Usage::

        database.JSONEncodedDict(255)

    """
    impl = types.TEXT

    def process_bind_param(self, value, dialect):
        if value is not None:
            value = json.dumps(value)
        return value

    def process_result_value(self, value, dialect):
        if value is not None:
            value = json.loads(value)
        return value


class ChoiceType(types.TypeDecorator):
    """
    example::
    choices=(
        ('key1', 'value1'),
        ('key2', 'value2')
    )

    filed::
        db.Column(db.ChoiceType(length=xx, choices=choices))

    """
    impl = types.Integer

    def __init__(self, choices=None, **kw):
        if choices:
            self.choices = dict(choices)
            self.reverse_choices = dict(((value, key) for key, value in choices))
        super(ChoiceType, self).__init__(**kw)

    def process_bind_param(self, value, dialect):
        # TODO: check None should base on field nullable param, and throw exeception here
        if value is None:
            return None
        return self.reverse_choices[value]

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return self.choices[value]


class Password(types.TypeDecorator):
    """
    这是password字段类型。就不需要到处都是加密操作了
    """
    impl = types.CHAR

    def process_bind_param(self, value, dialect):
        return sha256sum(value) if value else None


class AbstractProcessor:
    def process(self, sender, changes):
        raise NotImplementedError


class AbstractBulkEventsProcessor(AbstractProcessor):
    """
    handle model bulks
    """
    Model = None


class AbstractSingleEventsProcessor(AbstractProcessor):
    """
    handle model one by one
    """
    Model = None

    def process(self, sender, change):
        if len(change) == 2:
            obj, method, values_log = change[0], change[1], None
        else:
            obj, method, values_log = change[0], change[1], change[2]

        if method == 'insert':
            self._insert(sender, obj)

        elif method == 'update':
            if values_log:
                self._update(sender, obj, values_log)

        elif method == 'delete':
            self._delete(sender, obj)

        else:
            raise Exception()

    def _insert(self, sender, obj):
        raise NotImplementedError

    def _update(self, sender, obj, values_log):
        """
        only track column which _active_history=True
        """
        raise NotImplementedError

    def _delete(self, sender, obj):
        raise NotImplementedError


class EventsProcessorProxy(object):
    def __init__(self):
        self.bulk_processors_map = {}
        self.single_processors_map = {}

    def process(self, sender, changes):
        if self.bulk_processors_map:
            self.process_bulk_processor(sender, changes)

        if self.single_processors_map:
            self.process_single_processor(sender, changes)

    def process_bulk_processor(self, sender, changes):
        for Model, changes in itertools.groupby(sorted(changes, key=lambda change: type(change[0]).__name__),
                                                lambda change: type(change[0])):
            changes = list(changes)
            processor = self.bulk_processors_map.get(Model)
            self._process(sender, processor, changes)

    def process_single_processor(self, sender, changes):
        if self.single_processors_map:
            for change in changes:
                processor = self.single_processors_map.get(type(change[0]))
                self._process(sender, processor, change)

    @classmethod
    def _process(cls, sender, processor, changes):
        if processor:
            processor.process(sender, changes)

    def add_processors(self, *processors):
        for processor in processors:
            if isinstance(processor, AbstractSingleEventsProcessor):
                self.single_processors_map[processor.Model] = processor

            elif isinstance(processor, AbstractBulkEventsProcessor):
                self.bulk_processors_map[processor.Model] = processor

            else:
                raise Exception('Processor can not add')

    def clear(self):
        self.single_processors_map = {}
        self.bulk_processors_map = {}


class UUID(types.TypeDecorator):
    """Platform-independent GUID type.

    Uses Postgresql's UUID type, otherwise uses CHAR(36), storing as
    stringified hex values.

    This implementation is based on the SQLAlchemy
    `backend-agnostic GUID Type
    <http://www.sqlalchemy.org/docs/core/types.html#backend-agnostic-guid-type>`_
    example.
    """
    impl = types.CHAR

    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql':
            # noinspection PyUnresolvedReferences
            return dialect.type_descriptor(db.postgresql.UUID())
        else:
            return dialect.type_descriptor(types.CHAR(32))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        elif dialect.name == 'postgresql':
            return str(value)
        else:
            if not isinstance(value, uuid.UUID):
                return "%.32x" % uuid.UUID(value).hex
            else:
                # hexstring
                # noinspection PyUnresolvedReferences
                return "%.32x" % value.int

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        else:
            return uuid.UUID(value)


class MyJSON(sqlalchemy.sql.sqltypes.JSON):
    def __init__(self, none_as_null=False):
        super().__init__(none_as_null)

    def result_processor(self, dialect, coltype):
        string_process = self._str_impl.result_processor(dialect, coltype)
        json_deserializer = dialect._json_deserializer or json.loads

        def process(value):
            if value is None:
                return None
            if string_process:
                value = string_process(value)
            return json_deserializer(value, strict=False)

        return process

    def adapt(self, impltype, **kwargs):
        return MyJSON(**kwargs)



class DataBase(SQLAlchemy):
    ChoiceType = ChoiceType
    JSONEncodedDict = JSONEncodedDict
    Password = Password
    UUID = UUID
    JSON = MyJSON

    def __init__(self, *args, **kwargs):
        self.session = None  # type:SessionBase
        self.events_processor = None  # type: EventsProcessorProxy
        super(DataBase, self).__init__(*args, **kwargs)

    def init_app(self, app):
        """需要用到。要不sqlalchemy部分功能无法正常使用"""
        log.info('Base Init DB')
        self.app = app
        super(DataBase, self).init_app(app)
        self.configure_log_sql_echo()
        self.configure_signal_events()

    def configure_log_sql_echo(self):
        if os.getenv('SQL_ECHO') == 'ON':
            log.debug('Base Log SQL ONLINE')

            # noinspection PyUnusedLocal
            @event.listens_for(self.engine, "before_cursor_execute")
            def before_cursor_execute(conn, cursor, statement,
                                      parameters, context, executemany):
                try:
                    log.debug("Start Query: \n%s" % statement % parameters)
                except Exception:
                    log.debug("Start Query2: \n%s, %s" % (statement, parameters))

    def configure_signal_events(self):
        self.events_processor = EventsProcessorProxy()

        @before_models_committed.connect_via(self.app)
        def _before_models_committed(sender, changes):
            db.session.flush()
            self.events_processor.process(sender, changes)

    @staticmethod
    def get_or_create(model, defaults=None, **kwargs):
        """
        获取或者创建对象，模仿django的。
        """
        instance = model.query.filter_by(**kwargs).first()
        defaults = bool(defaults) and defaults or {}
        if instance:
            setattr(instance, 'is_new', False)
        else:
            kwargs.update(defaults)
            instance = model(**kwargs)
            db.session.add(instance)
            db.session.commit()
            setattr(instance, 'is_new', True)
        return instance

    def Column(self, *args, **kwargs):
        # 给pycharm自动提示用的
        if 0:
            kwargs.pop('name')
            kwargs.pop('type')
            kwargs.pop('autoincrement')
            kwargs.pop('default')
            kwargs.pop('doc')
            kwargs.pop('key')
            kwargs.pop('index')
            kwargs.pop('info')
            kwargs.pop('nullable')
            kwargs.pop('onupdate')
            kwargs.pop('primary_key')
            kwargs.pop('server_default')
            kwargs.pop('server_onupdate')
            kwargs.pop('quote')
            kwargs.pop('unique')
            kwargs.pop('system')
            kwargs.pop('comparator_factory')
            kwargs.pop('group')
            kwargs.pop('deferred')
            kwargs.pop('doc')
            kwargs.pop('expire_on_flush')
            kwargs.pop('info')
            kwargs.pop('extension')
        active_history = kwargs.pop('active_history', None)
        if active_history:
            return sqlalchemy.orm.properties.ColumnProperty(sqlalchemy.sql.schema.Column(*args, **kwargs),
                                                            active_history=active_history)
        else:
            return sqlalchemy.sql.schema.Column(*args, **kwargs)

db = DataBase()


class AbstractModel(db.Model):
    __abstract__ = True

    @classmethod
    def _validate_values(cls, values):
        pass

    @classmethod
    def create(cls, values):
        cls._validate_values(values)
        instance = cls(**values)
        db.session.add(instance)
        return instance

    @classmethod
    def delete(cls, oid):
        db.session.delete(cls.query.get(oid))
        return True

    @classmethod
    def update(cls, oid, values):
        cls._validate_values(values)
        obj = cls.query.get(oid)
        obj.update_values(**values)

    def update_values(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class BaseModel(AbstractModel):
    __abstract__ = True

    @declared_attr
    def create_time(self):
        return db.Column(db.TIMESTAMP, server_default=db.text('CURRENT_TIMESTAMP'), nullable=False)

    @declared_attr
    def write_time(self):
        return db.Column(db.TIMESTAMP, server_default=text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP'),
                         nullable=False)


    def __repr__(self):
        return f'<{self.__class__.__name__} {f"(id={self.id})" if hasattr(self,"id") else ""}>'

