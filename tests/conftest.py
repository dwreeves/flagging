import pytest

from unittest.mock import patch

from flagging_site import create_app
from flagging_site.twitter import tweepy_api
from flagging_site.data.database import cache as _cache
from flagging_site.data.database import create_db
from flagging_site.data.database import init_db
from flagging_site.data.database import update_db


@pytest.fixture(scope='session')
def app():
    """Create and configure a new app instance for each test."""
    app = create_app(config='testing')
    with app.app_context():
        create_db(overwrite=True)
        init_db()
        update_db()
        yield app


@pytest.fixture
def live_app(app):
    """This takes the app instance, and temporarily sets `USE_MOCK_DATA` to
    False. We can use this for tests where `USE_MOCK_DATA` needs to be False.
    """
    app.config['USE_MOCK_DATA'], old = False, app.config['USE_MOCK_DATA']
    yield app
    app.config['USE_MOCK_DATA'] = old


@pytest.fixture
def client(app):
    """A test client for the app. You can think of the test like a web browser;
    it retrieves data from the website in a similar way that a browser would.
    """
    return app.test_client()


@pytest.fixture(scope='function', autouse=True)
def cache():
    """After every test, we want to clear the cache."""
    yield _cache
    _cache.clear()


@pytest.fixture(scope='session')
def _db(app):
    """See this:

    https://github.com/jeancochrane/pytest-flask-sqlalchemy

    Basically, this '_db' fixture is required for the above extension to work.
    We use that extension to allow for easy testing of the database.
    """
    from flagging_site.data.database import db
    yield db


@pytest.fixture
def cli_runner(app):
    return app.test_cli_runner()


@pytest.fixture(autouse=True)
def mock_send_tweet():
    with patch.object(tweepy_api, 'update_status') as mocked_func:
        yield mocked_func
