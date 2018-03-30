import os
import subprocess

from charmhelpers.core import hookenv, host, templating, unitdata
from charmhelpers.core.host import chownr
from charmhelpers.fetch.archiveurl import ArchiveUrlFetchHandler
from charms.reactive import endpoint_from_flag, when, when_not, set_flag


JUPYTER_DIR = '/opt/jupyter'


@when_not('notebook.installed')
def install_notebook_dep():
    subprocess.call(['pip3', 'install', 'notebook'])
    set_flag('notebook.installed')


@when_not('jupyter-notebook.config.dir.available')
def create_jupyter_config_dir():
    os.makedirs(JUPYTER_DIR, exist_ok=True)
    chownr(JUPYTER_DIR, 'ubuntu', 'ubuntu', chowntopdir=True)
    set_flag('jupyter-notebook.config.dir.available')


@when_not('jupyter-notebook.installed')
def install_jupyter_notebook():
    conf = hookenv.config()
    aufh = ArchiveUrlFetchHandler()

    hookenv.log("Install Jupyter-notebook")

    # Download and install conda
    conda_installer_path = aufh.download_and_validate(
        conf.get('conda-installer-url'),
        conf.get('conda-installer-sha256'),
        validate="sha256"
    )
    if conda_installer_path:
        subprocess.call(['bash', conda_installer_path, '-b', '-f', '-p',
                         '/home/ubuntu/anaconda'])
        subprocess.call(['/home/ubuntu/anaconda/bin/conda', 'update', '-y',
                         '-n', 'base', 'conda'])

        # Create virtualenv and install jupyter
        subprocess.call(['/home/ubuntu/anaconda/bin/conda', 'create', '-y',
                         '-n', 'jupyter', 'python=3.5', 'jupyter', 'nb_conda'])
        subprocess.call(['/home/ubuntu/anaconda/bin/conda', 'install', '-y',
                         'jupyter'])

        # Install any extra conda packages
        if conf.get('conda-extra-packages'):
            subprocess.call(['/home/ubuntu/anaconda/bin/conda', 'install',
                             '-y', conf.get('conda-extra-packages')])

        # Pip install findspark
        subprocess.call(['/home/ubuntu/anaconda/envs/jupyter/bin/pip',
                         'install', 'findspark'])

        # Install any extra conda pip packages
        if conf.get('conda-extra-pip-packages'):
            subprocess.call(['/home/ubuntu/anaconda/envs/jupyter/bin/pip',
                             'install', conf.get('conda-extra-pip-packages')])
        # Chown the perms to ubuntu
        chownr('/home/ubuntu/anaconda', 'ubuntu', 'ubuntu', chowntopdir=True)

        # Set installed flag
        set_flag('jupyter-notebook.installed')
    else:
        hookenv.status_set('blocked',
                           "Conda could not verify installer, please DEBUG")
        return


@when('notebook.installed',
      'jupyter-notebook.installed',
      'jupyter-notebook.config.dir.available')
@when_not('jupyter-notebook.init.config.available')
def init_configure_jupyter_notebook():

    conf = hookenv.config()
    kv = unitdata.kv()

    if conf.get('jupyter-web-password'):
        kv.set('password', conf.get('jupyter-web-password'))
    else:
        kv.set('password', generate_password())

    ctxt = {
        'port': conf.get('jupyter-web-port'),
        'password_hash': generate_hash(kv.get('password')),
    }

    templating.render(
        source='jupyter_notebook_config.py.j2',
        target=os.path.join(JUPYTER_DIR, 'jupyter_notebook_config.py'),
        context=ctxt,
        owner='ubuntu',
        group='ubuntu',
    )
    set_flag('jupyter-notebook.init.config.available')


@when('jupyter-notebook.init.config.available')
@when_not('jupyter-notebook.systemd.available')
def render_systemd():
    render_api_systemd_template()
    set_flag('jupyter-notebook.systemd.available')


@when('jupyter-notebook.systemd.available')
@when_not('jupyter-notebook.init.available')
def jupyter_init_available():
    conf = hookenv.config()
    restart_notebook()
    if host.service_running('jupyter-notebook'):
        hookenv.open_port(conf.get('jupyter-web-port'))
        set_flag('jupyter-notebook.init.available')
    else:
        hookenv.status_set('blocked', "Jupyter could not start - Please DEBUG")


@when('endpoint.conda.joined')
@when_not('conda.relation.data.available')
def set_conda_relation_data():
    """Set conda endpoint relation data
    """
    conf = hookenv.config()
    endpoint = endpoint_from_flag('endpoint.conda.joined')

    ctxt = {'url': conf.get('conda-installer-url'),
            'sha': conf.get('conda-installer-sha256')}

    if conf.get('conda-extra-packages'):
        ctxt['conda_extra_packages'] = conf.get('conda-extra-packages')

    if conf.get('conda-extra-pip-packages'):
        ctxt['conda_extra_pip_packages'] = \
            conf.get('conda-extra-pip-packages')

    endpoint.configure(**ctxt)
    set_flag('conda.relation.data.available')


@when('endpoint.http.joined',
      'jupyter-notebook.init.available')
def configure_http():
    conf = hookenv.config()
    endpoint = endpoint_from_flag('endpoint.http.joined')
    endpoint.configure(port=conf.get('jupyter-web-port'))


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
            'Ready (Pass: "{}")'.format(unitdata.kv().get('password'))
        )
    else:
        hookenv.status_set(
            'blocked',
            'Could not restart service due to wrong configuration!'
        )


def render_api_systemd_template(context=None):
    if not context:
        context = {}
    templating.render(
        source='jupyter-notebook.service.j2',
        target='/etc/systemd/system/jupyter-notebook.service',
        context=context,
    )
    subprocess.check_call(['systemctl', 'daemon-reload'])


def generate_hash(password):
    from notebook.auth import passwd
    return passwd(password)


def generate_password():
    from xkcdpass import xkcd_password as xp
    mywords = xp.generate_wordlist()
    return xp.generate_xkcdpassword(mywords, numwords=4)
