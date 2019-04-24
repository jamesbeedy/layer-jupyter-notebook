from pathlib import Path
from subprocess import check_call

from charmhelpers.core.templating import render

from charms.layer.conda_api import CONDA_HOME


JUPYTER_WORK_DIR = Path('/srv/jupyter')
JUPYTER_CONDA_ENV_NAME = 'jupyter_env'
JUPYTER_NOTEBOOK_PORT = 8888
JUPYTER_BIN = CONDA_HOME / 'envs' / JUPYTER_CONDA_ENV_NAME / 'bin' / 'jupyter'


def render_jupyter_systemd_template(ctxt=None):
    """Render Jupyter Systemd template
    """

    if not ctxt:
        context = {}
    else:
        context = ctxt

    ctxt['jupyter_bin'] = str(JUPYTER_BIN)

    render(
        source='jupyter-notebook.service.j2',
        target='/etc/systemd/system/jupyter-notebook.service',
        context=context,
    )
    check_call(['systemctl', 'daemon-reload'])


# def generate_hash(password):
#     from notebook.auth import passwd
#     return passwd(password)


# def generate_password():
#     from xkcdpass import xkcd_password as xp
#     mywords = xp.generate_wordlist()
#     return xp.generate_xkcdpassword(mywords, numwords=4)
