import os
import re
from pathlib import Path
from subprocess import check_call

from charmhelpers.core import (
    hookenv,
    host,
    templating,
    unitdata
)

from charmhelpers.core.host import chownr

from charms.reactive import (
    endpoint_from_flag,
    hook,
    when,
    when_not,
    set_flag,
    clear_flag,
)

from charms.layer.conda_api import (
    CONDA_HOME,
    create_conda_venv,
    remove_conda_venv,
    init_install_conda,
    install_conda_packages,
    install_conda_pip_packages,
)


KV = unitdata.kv()

JUPYTER_WORK_DIR = Path('/srv/jupyter')
JUPYTER_CONDA_ENV_NAME = 'jupyter_env'
JUPYTER_NOTEBOOK_PORT = 8888


@when_not('jupyter.bind.address.available')
def bind_address_available():
    """Get the correct ip address for jupyter to bind.
    """
    ip = network_get('http')['ingress-addresses'][0]
    KV.set('bind_address', ip)
    set_flag('jupyter.bind.address.available')


@when_not('jupyter.work.dir.available')
def create_jupyter_work_dir():
    JUPYTER_WORK_DIR.mkdir(parents=True, exist_ok=True)
    chownr(str(JUPYTER_WORK_DIR), 'ubuntu', 'ubuntu', chowntopdir=True)
    set_flag('jupyter.work.dir.available')


@when('spark.base.init.complete')
@when_not('jupyter-notebook.installed')
def install_jupyter_notebook():
    hookenv.log("Install Jupyter-notebook")

    conf = hookenv.config()

    if not CONDA_HOME.exists():
        # Download and install conda
        init_install_conda(
            conf.get('conda-installer-url'),
            conf.get('conda-installer-sha256'),
            validate="sha256"
        )

    # Remove venv to be sure we are getting a clean install
    remove_conda_venv(env_name=JUPYTER_CONDA_ENV_NAME)

    # Create virtualenv and install jupyter
    create_conda_venv(env_name=JUPYTER_CONDA_ENV_NAME, python_version="3.5",
                      packages=['jupyter', 'nb_conda'])

    # Install any extra conda packages
    if conf.get('conda-extra-packages'):
        install_conda_packages(
            env_name=JUPYTER_CONDA_ENV_NAME,
            conda_packages=conf.get('conda-extra-packages').split())

    # Install any extra conda pip packages
    if conf.get('conda-extra-pip-packages'):
        install_conda_pip_packages(
            env_name=JUPYTER_CONDA_ENV_NAME,
            conda_packages=conf.get('conda-extra-pip-packages').split())

    # Chown the perms to ubuntu
    chownr(str(CONDA_HOME), 'ubuntu', 'ubuntu', chowntopdir=True)

    # Set installed flag
    set_flag('jupyter.installed')


@when('jupyter.installed')
@when_not('jupyter.systemd.available')
def render_systemd():
    render_jupyter_systemd_template()
    set_flag('jupyter.systemd.available')


@when('jupyter.systemd.available',
      'jupyter.bind.address.available')
@when_not('jupyter.init.available')
def jupyter_init_available():
    conf = hookenv.config()
    restart_notebook()
    if host.service_running('jupyter-notebook'):
        hookenv.open_port(JUPYTER_NOTEBOOK_PORT)
        set_flag('jupyter.init.available')
    else:
        hookenv.status_set('blocked', "Jupyter could not start - Please DEBUG")


@when('endpoint.http.available',
      'jupyter.init.available',
      'jupyter.bind.address.available')
def configure_http():
    conf = hookenv.config()
    endpoint = endpoint_from_flag('endpoint.http.available')
    endpoint.configure(
        port=JUPYTER_NOTEBOOK_PORT,
        private_address=KV.get('bind_address'),
        hostname=KV.get('bind_address')
    )


def restart_notebook():
    if host.service_running('jupyter-notebook'):
        host.service_stop('jupyter-notebook')
        import time
        time.sleep(10)
    # service_resume also enables the serivice on startup
    host.service_resume('jupyter-notebook')
    jupyter_status()


def jupyter_status():
    if host.service_running('jupyter-notebook'):
        hookenv.status_set(
            'active',
            'http://{}:{}'.format(
                KV.get('bind_address'),
                JUPYTER_NOTEBOOK_PORT
            )
        )
    else:
        hookenv.status_set(
            'blocked',
            'Could not restart service due to wrong configuration!'
        )


def render_jupyter_systemd_template(ctxt=None):
    """Render Jupyter Systemd template
    """

    if not ctxt:
        ctxt = {}

    ctxt['jupyter_bin'] = \
        str(CONDA_HOME / 'envs' / JUPYTER_CONDA_ENV_NAME / 'bin' / 'jupyter')

    templating.render(
        source='jupyter-notebook.service.j2',
        target='/etc/systemd/system/jupyter-notebook.service',
        context=ctxt,
    )
    check_call(['systemctl', 'daemon-reload'])


@hook('stop')
def clear_jupyter_venv():
    status.maint('Removing Conda Env: {}'.format(JUPYTER_CONDA_ENV_NAME))
    remove_conda_venv(env_name=JUPYTER_CONDA_ENV_NAME)
    status.active('Conda Env: {} removed'.format(JUPYTER_CONDA_ENV_NAME))


# def generate_hash(password):
#     from notebook.auth import passwd
#     return passwd(password)


# def generate_password():
#     from xkcdpass import xkcd_password as xp
#     mywords = xp.generate_wordlist()
#     return xp.generate_xkcdpassword(mywords, numwords=4)
