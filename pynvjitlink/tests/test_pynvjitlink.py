# Copyright (c) 2023, NVIDIA CORPORATION. All rights reserved.

import os
import pytest

from pynvjitlink import _nvjitlinklib
from pynvjitlink.api import InputType


def read_test_file(filename):
    test_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(test_dir, filename)
    with open(path, 'rb') as f:
        return filename, f.read()


@pytest.fixture
def device_functions_cubin():
    return read_test_file('test_device_functions.cubin')


@pytest.fixture
def device_functions_fatbin():
    return read_test_file('test_device_functions.fatbin')


@pytest.fixture
def device_functions_ltoir():
    return read_test_file('test_device_functions.ltoir')


@pytest.fixture
def device_functions_object():
    return read_test_file('test_device_functions.o')


@pytest.fixture
def device_functions_archive():
    return read_test_file('test_device_functions.a')


@pytest.fixture
def device_functions_ptx():
    return read_test_file('test_device_functions.ptx')


@pytest.fixture
def undefined_extern_cubin():
    return read_test_file('undefined_extern.cubin')


@pytest.mark.skip
def test_create_no_arch_error():
    # nvjitlink expects at least the architecture to be specified.
    with pytest.raises(RuntimeError,
                       match='NVJITLINK_ERROR_MISSING_ARCH error'):
        _nvjitlinklib.create()


@pytest.mark.skip('Causes fatal error and exit(1)')
def test_invalid_arch_error():
    # sm_XX is not a valid architecture
    with pytest.raises(RuntimeError,
                       match='NVJITLINK_ERROR_UNRECOGNIZED_OPTION error'):
        _nvjitlinklib.create('-arch=sm_XX')


@pytest.mark.skip
def test_unrecognized_option_error():
    with pytest.raises(RuntimeError,
                       match='NVJITLINK_ERROR_UNRECOGNIZED_OPTION error'):
        _nvjitlinklib.create('-fictitious_option')


@pytest.mark.skip
def test_invalid_option_type_error():
    with pytest.raises(TypeError,
                       match='Expecting only strings'):
        _nvjitlinklib.create('-arch', 53)


def test_create_and_destroy():
    handle = _nvjitlinklib.create('-arch=sm_53')
    assert handle != 0
    _nvjitlinklib.destroy(handle)


def test_complete_empty():
    handle = _nvjitlinklib.create('-arch=sm_75')
    _nvjitlinklib.complete(handle)
    _nvjitlinklib.destroy(handle)


@pytest.mark.parametrize('input_file,input_type', [
    ('device_functions_cubin', InputType.CUBIN),
    ('device_functions_fatbin', InputType.FATBIN),
    # XXX: LTOIR input type needs debugging - results in
    # NVJITLINK_ERROR_INTERNAL.
    pytest.param('device_functions_ltoir', InputType.LTOIR,
                 marks=pytest.mark.xfail),
    ('device_functions_ptx', InputType.PTX),
    ('device_functions_object', InputType.OBJECT),
    # XXX: Archive type needs debugging - results in a segfault.
    pytest.param('device_functions_archive', InputType.LIBRARY,
                 marks=pytest.mark.skip),
])
def test_add_file(input_file, input_type, request):
    filename, data = request.getfixturevalue(input_file)

    handle = _nvjitlinklib.create('-arch=sm_75')
    _nvjitlinklib.add_data(handle, input_type.value, data, filename)
    _nvjitlinklib.destroy(handle)


@pytest.mark.skip
def test_get_error_log(undefined_extern_cubin):
    handle = _nvjitlinklib.create('-arch=sm_75')
    filename, data = undefined_extern_cubin
    input_type = InputType.CUBIN.value
    _nvjitlinklib.add_data(handle, input_type, data, filename)
    with pytest.raises(RuntimeError):
        _nvjitlinklib.complete(handle)
    error_log = _nvjitlinklib.get_error_log(handle)
    _nvjitlinklib.destroy(handle)
    # XXX: The error message in the log is strange. The actual expected error
    # message appears on the terminal:
    #     error   : Undefined reference to '_Z5undefff' in
    #               'undefined_extern.cubin'
    assert "ERROR 9: finish" in error_log


def test_get_info_log(device_functions_cubin):
    handle = _nvjitlinklib.create('-arch=sm_75')
    filename, data = device_functions_cubin
    input_type = InputType.CUBIN.value
    _nvjitlinklib.add_data(handle, input_type, data, filename)
    _nvjitlinklib.complete(handle)
    info_log = _nvjitlinklib.get_info_log(handle)
    _nvjitlinklib.destroy(handle)
    # Info log is empty
    assert "" == info_log


def test_get_linked_cubin(device_functions_cubin):
    handle = _nvjitlinklib.create('-arch=sm_75')
    filename, data = device_functions_cubin
    input_type = InputType.CUBIN.value
    _nvjitlinklib.add_data(handle, input_type, data, filename)
    _nvjitlinklib.complete(handle)
    cubin = _nvjitlinklib.get_linked_cubin(handle)
    _nvjitlinklib.destroy(handle)

    # Just check we got something that looks like an ELF
    assert cubin[:4] == b'\x7fELF'


def test_get_linked_cubin_link_not_complete_error(device_functions_cubin):
    handle = _nvjitlinklib.create('-arch=sm_75')
    filename, data = device_functions_cubin
    input_type = InputType.CUBIN.value
    _nvjitlinklib.add_data(handle, input_type, data, filename)
    with pytest.raises(RuntimeError,
                       match="NVJITLINK_ERROR_INTERNAL error"):
        _nvjitlinklib.get_linked_cubin(handle)
    _nvjitlinklib.destroy(handle)


def test_get_linked_cubin_from_lto(device_functions_ltoir):
    filename, data = device_functions_ltoir
    # device_functions_ltoir is a host object containing a fatbin containing an
    # LTOIR container, because that is what NVCC produces when LTO is
    # requested. So we need to use the OBJECT input type, and the linker
    # retrieves the LTO IR from it because we passed the -lto flag.
    input_type = InputType.OBJECT.value
    handle = _nvjitlinklib.create('-arch=sm_75', '-lto')
    _nvjitlinklib.add_data(handle, input_type, data, filename)
    _nvjitlinklib.complete(handle)
    cubin = _nvjitlinklib.get_linked_cubin(handle)
    _nvjitlinklib.destroy(handle)

    # Just check we got something that looks like an ELF
    assert cubin[:4] == b'\x7fELF'


def test_get_linked_ptx_from_lto(device_functions_ltoir):
    filename, data = device_functions_ltoir
    # device_functions_ltoir is a host object containing a fatbin containing an
    # LTOIR container, because that is what NVCC produces when LTO is
    # requested. So we need to use the OBJECT input type, and the linker
    # retrieves the LTO IR from it because we passed the -lto flag.
    input_type = InputType.OBJECT.value
    handle = _nvjitlinklib.create('-arch=sm_75', '-lto', '-ptx')
    _nvjitlinklib.add_data(handle, input_type, data, filename)
    _nvjitlinklib.complete(handle)
    _nvjitlinklib.get_linked_ptx(handle)
    _nvjitlinklib.destroy(handle)


def test_get_linked_ptx_link_not_complete_error(device_functions_ltoir):
    handle = _nvjitlinklib.create('-arch=sm_75', '-lto', '-ptx')
    filename, data = device_functions_ltoir
    input_type = InputType.OBJECT.value
    _nvjitlinklib.add_data(handle, input_type, data, filename)
    with pytest.raises(RuntimeError,
                       match="NVJITLINK_ERROR_INTERNAL error"):
        _nvjitlinklib.get_linked_ptx(handle)
    _nvjitlinklib.destroy(handle)
