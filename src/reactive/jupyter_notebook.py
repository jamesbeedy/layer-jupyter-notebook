from charmhelpers.core import (
    hookenv,
    host,
    unitdata
)

from charmhelpers.core.host import chownr

from charms.reactive import (
    endpoint_from_flag,
    hook,
    when,
    when_not,
    set_flag,
)

from charms.layer import status

from charms.layer.conda_api import (
    CONDA_HOME,
    create_conda_venv,
    remove_conda_venv,
    init_install_conda,
    install_conda_packages,
    install_conda_pip_packages,
)

from charms.layer.spark_base import (
    render_spark_env_sh,
    get_spark_version,
)

from charms.layer.hadoop_base import get_hadoop_version

from charms.layer.jupyter_notebook import (
    JUPYTER_WORK_DIR,
    JUPYTER_CONDA_ENV_NAME,
    JUPYTER_NOTEBOOK_PORT,
    render_jupyter_systemd_template,
)


KV = unitdata.kv()


@when_not('jupyter.bind.address.available')
def bind_address_available():
    """Get the correct ip address for jupyter to bind.
    """
    ip = hookenv.network_get('http')['ingress-addresses'][0]
    KV.set('bind_address', ip)
    set_flag('jupyter.bind.address.available')


@when_not('jupyter.work.dir.available')
def create_jupyter_work_dir():
    JUPYTER_WORK_DIR.mkdir(parents=True, exist_ok=True)
    chownr(str(JUPYTER_WORK_DIR), 'ubuntu', 'ubuntu', chowntopdir=True)
    set_flag('jupyter.work.dir.available')


@when('spark.base.available')
@when_not('spark.env.available')
def write_spark_env():
    render_spark_env_sh(template='spark-env.sh')
    set_flag('spark.env.available')


@when('spark.base.available',
      'hadoop.base.available',
      'spark.env.available')
@when_not('jupyter.installed')
def install_jupyter_notebook():
    status.maint("Installing Jupyter-Notebook")

    conf = hookenv.config()

    if not CONDA_HOME.exists():
        # Download and install conda
        init_install_conda(
            url=conf.get('conda-installer-url'),
            checksum=conf.get('conda-installer-checksum'),
            hash_type=conf.get('conda-installer-hash-type')
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

    # Chown CONDA_HOME to ubuntu:ubuntu
    chownr(str(CONDA_HOME), 'ubuntu', 'ubuntu', chowntopdir=True)

    # Set installed flag
    set_flag('jupyter.installed')


@when('jupyter.installed')
@when_not('jupyter.systemd.available')
def render_jupyter_systemd():
    render_jupyter_systemd_template(
        {
            'hadoop_version': get_hadoop_version(),
            'spark_version': get_spark_version(),
        }
    )
    set_flag('jupyter.systemd.available')


@when('jupyter.systemd.available',
      'jupyter.bind.address.available')
@when_not('jupyter.init.available')
def jupyter_init_available():
    restart_notebook()
    if host.service_running('jupyter-notebook'):
        hookenv.open_port(JUPYTER_NOTEBOOK_PORT)
        set_flag('jupyter.init.available')
    else:
        status.blocked("Jupyter could not start - Please DEBUG")


@when('endpoint.http.available',
      'jupyter.init.available')
def configure_http():
    endpoint = endpoint_from_flag('endpoint.http.available')
    endpoint.configure(
        port=JUPYTER_NOTEBOOK_PORT,
        private_address=KV.get('bind_address'),
        hostname=KV.get('bind_address')
    )


@when('jupyter.init.available')
def persist_status():
    jupyter_status()


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
        status.active(
            'http://{}:{}'.format(
                KV.get('bind_address'),
                JUPYTER_NOTEBOOK_PORT
            )
        )
    else:
        status.blocked(
            'Could not restart service due to wrong configuration!'
        )


@hook('stop')
def clear_jupyter_venv():
    status.maint('Removing Conda Env: {}'.format(JUPYTER_CONDA_ENV_NAME))
    host.service_stop('jupyter-notebook')
    remove_conda_venv(env_name=JUPYTER_CONDA_ENV_NAME)
