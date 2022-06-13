#!$BLENDER_PATH/python/bin python

import logging
import pathlib
import pkgutil
import site
import subprocess
import sys


MODULES = {
    'nft_blender': 'git+https://github.com/Masangri/nft-blender.git@main#egg=nft-blender',
    # Dependencies (installed automatically with `nft-blender` module):
    'PySide2': 'PySide2',
    'shiboken2': 'shiboken2',
}


def _ensure_pip():
    """Ensure that `pip` is installed (comes preinstalled for Blender 3.x)."""
    logging.debug('Checking if pip is installed:\n')
    subprocess.call([sys.executable, '-m', 'ensurepip'])


def install_package(module_name: str):
    """"""
    # Retrieve module name and location
    module_location = MODULES.get(module_name)

    # Abort if module info isn't found.
    if not module_location:
        logging.warning(f'`{module_name}` is not a valid option. Aborting!')
        return False

    # Upgrade `pip` if necessary.
    logging.debug('Updating pip')
    subprocess.call([sys.executable, '-m', 'pip', 'install', '--upgrade', 'pip'])

    # Access to Blender's internal site packages might be restricted on Windows.
    # Install package to user's Python site-packages directory instead (same version of Python 3.x recommended).
    user_site = pathlib.Path(site.getusersitepackages())
    if str(user_site) not in site.getsitepackages():
        logging.debug('Adding user\'s `site-packages` directory as potential installation location.')
        site.addsitedir(str(user_site))


    # Install module and dependencies from GitHub repository (branch: `main`), if not already.
    installed_module_names = [mod.name for mod in pkgutil.iter_modules()]
    if module_name not in installed_module_names:
        logging.debug(f'Installing Python module: `{module_name}`')
        subprocess.call([sys.executable, '-m', 'pip', 'install', module_location])

    # Update module.
    logging.debug(f'Updating Python module: `{module_name}`')
    subprocess.call([sys.executable, '-m', 'pip', 'install', module_location, '--upgrade'])

    return True


def uninstall_package(module_name: str):
    """"""
    # Uninstall module and dependencies, if they are installed.
    installed_module_names = [mod.name for mod in pkgutil.iter_modules()]
    if module_name in installed_module_names:
        logging.debug(f'Uninstalling Python module: `{module_name}`')
        subprocess.call([sys.executable, '-m', 'pip', 'uninstall', '-y', module_name])

    return True


if __name__ == '__main__':

    install_package('nft_blender')
