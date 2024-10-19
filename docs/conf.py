# Configuration file for the Sphinx documentation builder.
#
# This file only contains a selection of the most common options. For a full
# list see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html
#
# Make documentation:
# cd docs && make clean && make html && cd ..

# -- Path setup --------------------------------------------------------------

# If extensions (or modules to document with autodoc) are in another directory,
# add these directories to sys.path here.

import pathlib
import sys


# add sourcecode to path.
src_root_path = pathlib.Path('../src/').resolve()
for submod in ('mas_blender', 'mas_blender/mas_bpy', 'mas_blender/mas_db', 'mas_blender/mas_ops'):
    sys.path.insert(0, src_root_path.joinpath(submod).as_posix())

# -- Project information -----------------------------------------------------

project = 'MAS Blender'
copyright = '2024, [m a s]'
author = '[m a s]'

# The full version, including alpha/beta/rc tags
release = '0.0.1'


# -- General configuration ---------------------------------------------------

autodoc_mock_imports = ['bpy', 'PySide6']

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom
# ones.
extensions = ['sphinx.ext.autodoc', 'sphinx_autodoc_typehints']

# Override html default "contents.rst" to use Sphinx's default "index.rst".
master_doc = 'index'

# Add any paths that contain templates here, relative to this directory.
templates_path = ['_templates']

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
# This pattern also affects html_static_path and html_extra_path.
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']


# -- Options for HTML output -------------------------------------------------

# The theme to use for HTML and HTML Help pages.  See the documentation for
# a list of builtin themes.
#
html_theme = 'sphinx_rtd_theme'

# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
html_static_path = ['_static']

# Exclude search.html for epub format
epub_exclude_files = ['search.html']
