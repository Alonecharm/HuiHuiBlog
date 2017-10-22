# author = matt.cai(cysnake4713@gmail.com)
import pickle
from enum import Enum

from flask import session
from flask_principal import Principal, Identity, AnonymousIdentity

# from zeroso.base.principal.needs import login_need


class AuthType(Enum):
    FROM_SESSION = 1
    LOGIN = 2
    TEST_CASE = 3


principal_config = Principal(use_sessions=False)


@principal_config.identity_loader
def session_identity_loader():
    if 'identity.id' in session and 'identity.auth_type' in session:
        identity = Identity(session['identity.id'], auth_type=AuthType.FROM_SESSION)
        return identity


@principal_config.identity_saver
def session_identity_saver(identity):
    if isinstance(identity, AnonymousIdentity):
        session.pop('identity.id')
        session.pop('identity.auth_type')
        session.pop('identity.provides')
        session.pop('identity.user')
        session.modified = True
    else:
        # pickle write to redis may slow down the system, must use cpickle to do this
        session['identity.id'] = identity.id
        session['identity.auth_type'] = 'session_load'
        # WARNING: use pickle to save object maybe cause problem
        pickle_string = pickle.dumps(identity.provides)
        session['identity.provides'] = pickle_string
        user_string = pickle.dumps(identity.user)
        session['identity.user'] = user_string
        session.modified = True


def on_identity_loaded(sender, identity):
    if isinstance(identity, AnonymousIdentity):
        pass
    elif identity.auth_type == AuthType.FROM_SESSION:
        provides = session.get('identity.provides', None)
        if provides:
            identity.provides = pickle.loads(provides)
        user = session.get('identity.user')
        if user:
            identity.user = pickle.loads(user)
    elif identity.auth_type == AuthType.LOGIN:
        pass
        # identity.provides.update(login_need.needs)
        # Add User Info
    elif identity.auth_type == AuthType.TEST_CASE:
        pass
        # identity.provides.update(login_need.needs)
