from models.resource import Resource

def test_resource_version_increments_on_update():
    resource = Resource(id='1', data={'name': 'old'}, version=5)
    resource.update({'name': 'new'})
    assert resource.version == 6
    assert resource.data['name'] == 'new'
