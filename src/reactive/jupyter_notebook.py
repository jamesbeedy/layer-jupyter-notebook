import os
import re
from pathlib import Path
from subprocess import check_call

from charmhelpers.core import hookenv, host, templating, unitdata
from charmhelpers.core.host import chownr
from charms.reactive import (
    endpoint_from_flag,
    when,
    when_not,
    set_flag,
    clear_flag,
)

from charms.layer.conda_api import (
    CONDA_HOME,
    create_conda_venv,
    init_install_conda,
    install_conda_packages,
    install_conda_pip_packages,
)


JUPYTER_WORK_DIR = Path('/home/ubuntu/jupyter')
JUPYTER_CONDA_ENV_NAME = 'jupyter_env'


@when_not('jupyter-notebook.config.dir.available')
def create_jupyter_config_dir():
    JUPYTER_WORK_DIR.mkdir(parents=True, exist_ok=True)
    chownr(str(JUPYTER_WORK_DIR), 'ubuntu', 'ubuntu', chowntopdir=True)
    set_flag('jupyter-notebook.config.dir.available')


@when('spark.base.init.complete')
@when_not('jupyter-notebook.installed')
def install_jupyter_notebook():
    hookenv.log("Install Jupyter-notebook")

    conf = hookenv.config()

    # Download and install conda
    init_install_conda(
        conf.get('conda-installer-url'),
        conf.get('conda-installer-sha256'),
        validate="sha256"
    )

    # Create virtualenv and install jupyter
    create_conda_venv(env_name=JUPYTER_CONDA_ENV_NAME, python_version="3.5",
                      packages=['jupyter', 'nb_conda', 'ipykernel'])

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
    set_flag('jupyter-notebook.installed')


@when('jupyter-notebook.installed')
@when_not('jupyter-notebook.systemd.available')
def render_systemd():
    render_jupyter_systemd_template()
    set_flag('jupyter-notebook.systemd.available')


@when('jupyter-notebook.systemd.available')
@when_not('jupyter-notebook.init.available')
def jupyter_init_available():
    conf = hookenv.config()
    restart_notebook()
    if host.service_running('jupyter-notebook'):
        hookenv.open_port(8888)
        set_flag('jupyter-notebook.init.available')
    else:
        hookenv.status_set('blocked', "Jupyter could not start - Please DEBUG")


@when('conda.available')
@when_not('conda.relation.data.available')
def set_conda_relation_data():
    """Set conda endpoint relation data
    """
    conf = hookenv.config()
    endpoint = endpoint_from_flag('conda.available')

    ctxt = {'url': conf.get('conda-installer-url'),
            'sha': conf.get('conda-installer-sha256')}

    if conf.get('conda-extra-packages'):
        ctxt['conda_extra_packages'] = conf.get('conda-extra-packages')

    if conf.get('conda-extra-pip-packages'):
        ctxt['conda_extra_pip_packages'] = \
            conf.get('conda-extra-pip-packages')

    endpoint.configure(**ctxt)
    set_flag('conda.relation.data.available')


@when('http.available',
      'jupyter-notebook.init.available')
def configure_http():
    conf = hookenv.config()
    endpoint = endpoint_from_flag('http.available')
    endpoint.configure(port=8888)


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
           # 'Ready (Pass: "{}")'.format(unitdata.kv().get('password'))
            'Ready'
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



#def generate_hash(password):
#    from notebook.auth import passwd
#    return passwd(password)


#def generate_password():
#    from xkcdpass import xkcd_password as xp
#    mywords = xp.generate_wordlist()
#    return xp.generate_xkcdpassword(mywords, numwords=4)
