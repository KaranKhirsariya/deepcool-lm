"""Shared fixtures. The driver script has no .py extension, so import it
through an explicit SourceFileLoader."""
import importlib.machinery
import importlib.util
import os
import sys

import pytest

_SCRIPT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, 'deepcool-lm'))


@pytest.fixture(scope='session')
def dlm():
    """The deepcool-lm script imported as a module."""
    loader = importlib.machinery.SourceFileLoader('deepcool_lm', _SCRIPT)
    spec = importlib.util.spec_from_loader('deepcool_lm', loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules['deepcool_lm'] = module
    loader.exec_module(module)
    return module
