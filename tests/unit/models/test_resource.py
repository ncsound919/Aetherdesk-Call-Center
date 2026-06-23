import pytest
from models.resource import Resource


def test_resource_version_increments_on_update():
    resource = Resource(id='1', data={'name': 'old'}, version=5)
    resource.update({'name': 'new'})
    assert resource.version == 6
    assert resource.data['name'] == 'new'


def test_resource_update_accepts_matching_expected_version():
    resource = Resource(id='1', data={'name': 'old'}, version=3)
    # Calling update with the correct expected version should succeed.
    resource.update({'name': 'new'}, expected_version=3)
    assert resource.version == 4
    assert resource.data['name'] == 'new'


def test_resource_update_rejects_stale_expected_version():
    resource = Resource(id='1', data={'name': 'old'}, version=3)
    # Simulates another writer having bumped the version to 5 while
    # this caller still holds a stale snapshot of version 3.
    with pytest.raises(ValueError, match="Version conflict"):
        resource.update({'name': 'new'}, expected_version=5)
    # The version must NOT have been incremented.
    assert resource.version == 3
    assert resource.data['name'] == 'old'


def test_resource_update_without_expected_version_always_succeeds():
    resource = Resource(id='1', data={'name': 'old'}, version=10)
    resource.update({'name': 'new'})
    assert resource.version == 11
    assert resource.data['name'] == 'new'


def test_resource_update_merges_data():
    resource = Resource(id='1', data={'a': 1, 'b': 2}, version=0)
    resource.update({'b': 99, 'c': 3})
    assert resource.data == {'a': 1, 'b': 99, 'c': 3}
    assert resource.version == 1


def test_resource_update_does_not_mutate_input_dict():
    original = {'name': 'new'}
    resource = Resource(id='1', data={'name': 'old'}, version=0)
    resource.update(original)
    # The original dict must remain untouched.
    assert original == {'name': 'new'}
