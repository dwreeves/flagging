from unittest.mock import patch
from functools import wraps
from flagging_site.data import Boathouse
from flagging_site.twitter import compose_tweet

import pytest

from flagging_site.data import database


@pytest.fixture
def mock_update_db():
    with patch.object(database, 'update_db') as mocked_func:
        yield mocked_func


@pytest.mark.parametrize('cmd', ['update-db', 'update-website'])
def test_update_runs(cmd, app, cli_runner, mock_update_db, mock_send_tweet):
    res = cli_runner.invoke(app.cli, [cmd])

    assert res.exit_code == 0
    assert mock_update_db.call_count == 1

    if cmd == 'update-db':
        assert mock_send_tweet.call_count == 0
    elif cmd == 'update-website':
        assert mock_send_tweet.call_count == 1
    else:
        assert False


def test_shell_runs(app):
    available = app.shell_context_processors[0]()
    assert 'app' in available
    assert 'client' in available
    assert 'db' in available


def tweets_parametrization(func: callable):
    """This decorator creates two new fixtures: overrides and expected_text.
    It performs the work of overriding a number of flags equivalent to the
    `overriddes` amount before the decorated text receives the db_session.
    """
    @pytest.mark.parametrize(
        ('overrides', 'expected_text'),
        [
            (0, 'all boathouses are safe as of'),
            (2, 'some boathouses are unsafe as of'),
            (999, 'all boathouses are unsafe as of'),
        ]
    )
    @wraps(func)
    def _wrap(overrides, expected_text, db_session, *args, **kwargs):
        db_session \
            .query(Boathouse) \
            .filter(Boathouse.id <= overrides) \
            .update({"overridden": True})
        db_session.commit()
        func(overrides, expected_text, db_session, *args, **kwargs)

    return _wrap


@tweets_parametrization
def test_tweet(overrides, expected_text, db_session):
    """Make sure it contains the text"""
    tweet = compose_tweet()
    assert expected_text in tweet


@tweets_parametrization
def test_tweet_chars(overrides, expected_text, db_session):
    """Tweets can have up to 280 characters (URLs are special and always count
    as 23 chars), but we want to be safe anyway, so we'll limit to 240 chars.
    """
    tweet = compose_tweet()
    assert len(tweet) < 240
