"""UI test package (marker ``ui``; excluded from the default pytest run).

The ``__init__.py`` makes ``tests/ui`` a package so the relative imports of
``conftest``/``helpers`` in the test modules resolve during collection.
"""
