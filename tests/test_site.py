from base64 import b64encode

import pytest

from flagging_site.data import Boathouse


def auth_to_header(auth: str) -> dict:
    if auth is not None:
        auth_encoded = b64encode(auth.encode()).decode('utf-8')
        headers = {'Authorization': f'Basic {auth_encoded}'}
    else:
        headers = {}
    return headers


@pytest.mark.parametrize(
    ('page', 'expected_status_code'),
    [
        ('/', 200),
        ('/about', 200),
        ('/model', 200),
        ('/flags', 200),
        ('/api', 200),
        ('/api/docs', 200),
        ('/api/v1/model', 200),
        ('/api/v1/model?reach=4&hours=20', 200),
        ('/api/v1/boathouses', 200),
        ('/api/v1/model_input_data', 200),
    ]
)
def test_pages(client, page, expected_status_code):
    """Test that pages render without errors. This test is very broad; the
    purpose of this test is to capture any errors that would cause a routing
    function to fail, such as a 404 HTTP error or a 500 HTTP error.

    Although this test is not very specific with what it tests (e.g. a page can
    render without any status code errors but still render incorrectly), it is
    still a good stop-gap.
    """
    assert client.get(page).status_code == expected_status_code


@pytest.mark.parametrize(
    ('page', 'auth', 'expected_status_code'),
    [
        ('/admin/', None, 401),
        ('/admin/', 'bad:credentials', 401),

        ('/admin/boathouses/', None, 401),
        ('/admin/boathouses/', 'bad:credentials', 401),

        ('/admin/livewebsiteoptions/', None, 401),
        ('/admin/livewebsiteoptions/', 'bad:credentials', 401),

        ('/admin/', 'admin:password', 200),
        ('/admin/livewebsiteoptions/', 'admin:password', 302),
        ('/admin/manual_overrides/', 'admin:password', 200),
        ('/admin/boathouses/', 'admin:password', 200),
        ('/admin/db/update/', 'admin:password', 200),
        ('/admin/db/download/', 'admin:password', 200),
    ]
)
def test_admin_pages(client, page, auth, expected_status_code):
    headers = auth_to_header(auth)
    res = client.get(page, headers=headers)

    assert res.status_code == expected_status_code


@pytest.mark.parametrize(
    ('page', 'auth', 'expected_status_code'),
    [
        # Valid
        ('/admin/db/download/csv/hobolink', 'admin:password', 200),
        ('/admin/db/download/csv/usgs', 'admin:password', 200),
        ('/admin/db/download/csv/processed_data', 'admin:password', 200),
        ('/admin/db/download/csv/model_outputs', 'admin:password', 200),
        ('/admin/db/download/csv/boathouses', 'admin:password', 200),
        ('/admin/db/download/csv/override_history', 'admin:password', 200),
        ('/admin/db/download/csv/hobolink_source', 'admin:password', 200),
        ('/admin/db/download/csv/usgs_source', 'admin:password', 200),
        ('/admin/db/download/csv/processed_data_source', 'admin:password', 200),
        ('/admin/db/download/csv/model_outputs_source', 'admin:password', 200),

        # Errors
        ('/admin/db/download/csv/arbitrary_table', 'admin:password', 404),
        ('/admin/db/download/csv/boathouses', 'bad:credentials', 401),
        ('/admin/db/download/csv/hobolink_source', None, 401),
    ]
)
def test_admin_downloads(client, page, auth, expected_status_code):
    headers = auth_to_header(auth)
    res = client.get(page, headers=headers)

    assert res.status_code == expected_status_code

    if res.status_code >= 400:
        assert res.mimetype == 'text/html'
    else:
        assert res.mimetype == 'text/csv'
        # make sure it's returning *something*
        if 'override_history' not in page:
            assert res.data.count(b'\n') >= 5


def test_override_on_home_page(client, db_session, cache):
    """Test to see that manual overrides show up properly on the home page. This
    test assumes that the flag for "Union Boat Club" starts off as blue and not
    overridden.

    This function also tests that the caching works. Basically, updating the
    database model by itself does not update the home page. It is also necessary
    for the cache to be cleared.
    """

    def _get_flag_count():
        res = client.get('/').data
        return {
            'blue': res.count(b'blue_flag.png'),
            'red': res.count(b'red_flag.png')
        }

    # First let's get the home page.
    flags1 = _get_flag_count()

    # Let's clear the cache and get the home page again.
    # Nothing should have changed because the database was not updated.

    cache.clear()
    flags2 = _get_flag_count()

    assert flags2['red'] == flags1['red']
    assert flags2['blue'] == flags1['blue']

    # Now update the entry in the database.

    db_session \
        .query(Boathouse) \
        .filter(Boathouse.boathouse == 'Union Boat Club') \
        .update({"overridden": True})
    db_session.commit()

    # Without clearing the cache, the page should be the exact same, even
    # though we updated the database on the backend.

    flags3 = _get_flag_count()

    assert flags3['red'] == flags1['red']
    assert flags3['blue'] == flags1['blue']

    # Now let's clear the cache. At long last, now the page should change
    # because both the model updated and the cache cleared.

    cache.clear()
    flags4 = _get_flag_count()

    assert flags4['red'] == flags1['red'] + 1
    assert flags4['blue'] == flags1['blue'] - 1
