# -*- coding: utf-8 -*-
# pylint: disable=redefined-outer-name,protected-access,no-member
"""Tests for the :mod:`aiida.orm.nodes.repository` module."""
import pathlib

import pytest

from aiida.common import exceptions
from aiida.common.warnings import AiidaDeprecationWarning
from aiida.engine import ProcessState
from aiida.manage.caching import enable_caching
from aiida.orm import CalcJobNode, Data, load_node
from aiida.repository.backend import DiskObjectStoreRepositoryBackend, SandboxRepositoryBackend
from aiida.repository.common import File, FileType


@pytest.fixture
def cacheable_node():
    """Return a node that can be cached from."""
    node = CalcJobNode(process_type='aiida.calculations:core.arithmetic.add')
    node.set_process_state(ProcessState.FINISHED)
    node.base.repository.put_object_from_bytes(b'content', 'relative/path')
    node.store()
    assert node.is_valid_cache

    return node


@pytest.mark.usefixtures('aiida_profile_clean')
def test_initialization():
    """Test that the repository instance is lazily constructed."""
    node = Data()
    assert node.base.repository.metadata == {}
    assert node.base.repository._repository_instance is None

    # Initialize just by calling the property
    assert isinstance(node.base.repository._repository.backend, SandboxRepositoryBackend)


@pytest.mark.usefixtures('aiida_profile_clean')
def test_unstored():
    """Test the repository for unstored nodes."""
    node = Data()
    node.base.repository.put_object_from_bytes(b'content', 'relative/path')

    assert isinstance(node.base.repository._repository.backend, SandboxRepositoryBackend)
    assert node.base.repository.metadata == {}


@pytest.mark.usefixtures('aiida_profile_clean')
def test_store():
    """Test the repository after storing."""
    node = Data()
    node.base.repository.put_object_from_bytes(b'content', 'relative/path')
    assert node.base.repository.list_object_names() == ['relative']
    assert node.base.repository.list_object_names('relative') == ['path']

    hash_unstored = node.base.repository.hash()
    metadata = node.base.repository.serialize()

    node.store()
    assert isinstance(node.base.repository._repository.backend, DiskObjectStoreRepositoryBackend)
    assert node.base.repository.serialize() != metadata
    assert node.base.repository.hash() == hash_unstored


@pytest.mark.usefixtures('aiida_profile_clean')
def test_load():
    """Test the repository after loading."""
    node = Data()
    node.base.repository.put_object_from_bytes(b'content', 'relative/path')
    node.store()

    hash_stored = node.base.repository.hash()
    metadata = node.base.repository.serialize()

    loaded = load_node(node.uuid)
    assert isinstance(node.base.repository._repository.backend, DiskObjectStoreRepositoryBackend)
    assert node.base.repository.serialize() == metadata
    assert loaded.base.repository.hash() == hash_stored


@pytest.mark.usefixtures('aiida_profile_clean')
def test_load_updated():
    """Test the repository after loading."""
    node = CalcJobNode()
    node.base.repository.put_object_from_bytes(b'content', 'relative/path')
    node.store()

    loaded = load_node(node.uuid)
    assert loaded.base.repository.get_object_content('relative/path', mode='rb') == b'content'


@pytest.mark.usefixtures('aiida_profile_clean')
def test_caching(cacheable_node):
    """Test the repository after a node is stored from the cache."""

    with enable_caching():
        cached = CalcJobNode(process_type='aiida.calculations:core.core.arithmetic.add')
        cached.base.repository.put_object_from_bytes(b'content', 'relative/path')
        cached.store()

    assert cached.is_created_from_cache
    assert cached.get_cache_source() == cacheable_node.uuid
    assert cacheable_node.base.repository.metadata == cached.base.repository.metadata
    assert cacheable_node.base.repository.hash() == cached.base.repository.hash()


@pytest.mark.usefixtures('aiida_profile_clean')
def test_clone():
    """Test the repository after a node is cloned from a stored node."""
    node = Data()
    node.base.repository.put_object_from_bytes(b'content', 'relative/path')
    node.store()

    clone = node.clone()
    assert clone.base.repository.list_object_names('relative') == ['path']
    assert clone.base.repository.get_object_content('relative/path', mode='rb') == b'content'

    clone.store()
    assert clone.base.repository.list_object_names('relative') == ['path']
    assert clone.base.repository.get_object_content('relative/path', mode='rb') == b'content'
    assert clone.base.repository.metadata == node.base.repository.metadata
    assert clone.base.repository.hash() == node.base.repository.hash()


@pytest.mark.usefixtures('aiida_profile_clean')
def test_clone_unstored():
    """Test the repository after a node is cloned from an unstored node."""
    node = Data()
    node.base.repository.put_object_from_bytes(b'content', 'relative/path')

    clone = node.clone()
    assert clone.base.repository.list_object_names('relative') == ['path']
    assert clone.base.repository.get_object_content('relative/path', mode='rb') == b'content'

    clone.store()
    assert clone.base.repository.list_object_names('relative') == ['path']
    assert clone.base.repository.get_object_content('relative/path', mode='rb') == b'content'


@pytest.mark.usefixtures('aiida_profile_clean')
def test_sealed():
    """Test the repository interface for a calculation node before and after it is sealed."""
    node = CalcJobNode()
    node.base.repository.put_object_from_bytes(b'content', 'relative/path')
    node.store()
    node.seal()

    with pytest.raises(exceptions.ModificationNotAllowed):
        node.base.repository.put_object_from_bytes(b'content', 'path')


@pytest.mark.usefixtures('aiida_profile_clean')
def test_get_object_raises():
    """Test the ``NodeRepository.get_object`` method when it is supposed to raise."""
    node = Data()

    with pytest.raises(TypeError, match=r'path `.*` is not a relative path.'):
        node.base.repository.get_object('/absolute/path')

    with pytest.raises(FileNotFoundError, match=r'object with path `.*` does not exist.'):
        node.base.repository.get_object('non_existing_folder/file_a')

    with pytest.raises(FileNotFoundError, match=r'object with path `.*` does not exist.'):
        node.base.repository.get_object('non_existant')


@pytest.mark.usefixtures('aiida_profile_clean')
def test_get_object():
    """Test the ``NodeRepository.get_object`` method."""
    node = CalcJobNode()
    node.base.repository.put_object_from_bytes(b'content', 'relative/file_b')

    file_object = node.base.repository.get_object(None)
    assert isinstance(file_object, File)
    assert file_object.file_type == FileType.DIRECTORY
    assert file_object.is_file() is False
    assert file_object.is_dir() is True

    file_object = node.base.repository.get_object('relative')
    assert isinstance(file_object, File)
    assert file_object.file_type == FileType.DIRECTORY
    assert file_object.name == 'relative'

    file_object = node.base.repository.get_object('relative/file_b')
    assert isinstance(file_object, File)
    assert file_object.file_type == FileType.FILE
    assert file_object.name == 'file_b'
    assert file_object.is_file() is True
    assert file_object.is_dir() is False


@pytest.mark.usefixtures('aiida_profile_clean')
def test_walk():
    """Test the ``NodeRepository.walk`` method."""
    node = Data()
    node.base.repository.put_object_from_bytes(b'content', 'relative/path')

    results = []
    for root, dirnames, filenames in node.base.repository.walk():
        results.append((root, sorted(dirnames), sorted(filenames)))

    assert sorted(results) == [
        (pathlib.Path('.'), ['relative'], []),
        (pathlib.Path('relative'), [], ['path']),
    ]

    # Check that the method still works after storing the node
    node.store()

    results = []
    for root, dirnames, filenames in node.base.repository.walk():
        results.append((root, sorted(dirnames), sorted(filenames)))

    assert sorted(results) == [
        (pathlib.Path('.'), ['relative'], []),
        (pathlib.Path('relative'), [], ['path']),
    ]


@pytest.mark.usefixtures('aiida_profile_clean')
def test_glob():
    """Test the ``NodeRepository.glob`` method."""
    node = Data()
    node.base.repository.put_object_from_bytes(b'content', 'relative/path')

    assert {path.as_posix() for path in node.base.repository.glob()} == {'relative', 'relative/path'}


@pytest.mark.usefixtures('aiida_profile_clean')
def test_copy_tree(tmp_path):
    """Test the ``Repository.copy_tree`` method."""
    node = Data()
    node.base.repository.put_object_from_bytes(b'content', 'relative/path')

    node.base.repository.copy_tree(tmp_path)
    dirpath = pathlib.Path(tmp_path / 'relative')
    filepath = dirpath / 'path'
    assert dirpath.is_dir()
    assert filepath.is_file()
    with node.base.repository.open('relative/path', 'rb') as handle:
        assert filepath.read_bytes() == handle.read()


@pytest.mark.usefixtures('aiida_profile_clean')
def test_deprecated_methods(monkeypatch):
    """Test calling (deprecated) methods, directly from the `Node` instance still works."""
    node = Data()
    monkeypatch.setenv('AIIDA_WARN_v3', 'true')
    for method in node._deprecated_repo_methods:
        with pytest.warns(AiidaDeprecationWarning):
            getattr(node, method)