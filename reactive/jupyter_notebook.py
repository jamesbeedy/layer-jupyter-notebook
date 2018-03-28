import os
import subprocess

from charmhelpers.core import hookenv, host, templating, unitdata
from charmhelpers.core.host import chownr
from charmhelpers.contrib.python.packages import pip_install
from charms.reactive import when, when_not, set_flag, clear_flag


JUPYTER_DIR = '/opt/jupyter'


@when_not('jupyter-notebook.config.dir.available')
def create_jupyter_config_dir():
    os.makedirs(JUPYTER_DIR, exist_ok=True)
    chownr(JUPYTER_DIR, 'ubuntu', 'ubuntu', chowntopdir=True)
    set_flag('jupyter-notebook.config.dir.available')


@when_not('jupyter-notebook.installed')
def install_jupyter_notebook():
    hookenv.log("Install Jupyter-notebook")
    pip_install('pip', upgrade=True)
    pip_install('jupyter')
    pip_install('toree')
    set_flag('jupyter-notebook.installed')


@when_not('jupyter-notebook.extra.deps.installed')
def install_extra_dependencies():
    deps = hookenv.config()['pip3-dependencies'].split()
    if deps:
        pip_install(" ".join(deps))
        if host.service_running('jupyter-notebook'):
            restart_notebook()
    set_flag('jupyter-notebook.extra.deps.installed')


@when('jupyter-notebook.installed',
      'jupyter-notebook.extra.deps.installed',
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
        target=os.path.join(JUPYTER_DIR, '/jupyter_notebook_config.py'),
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


@when('config.changed.pip3-dependencies',
      'jupyter-notebook.init.available')
def pip3_deps_changed():
    clear_flag('jupyter-notebook.extra.deps.installed')


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
