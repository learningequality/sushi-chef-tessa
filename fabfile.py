import os

from fabric.api import env, task, local, sudo, run, get
from fabric.context_managers import cd, prefix, show, hide, shell_env
from fabric.colors import red, green, blue, yellow
from fabric.utils import puts

env.hosts = [
    'eslgenie.com:1',  # vader runs ssh on port 1
]
env.user = os.environ.get('USER')
env.password = os.environ.get('VADER_PASSWORD')

STUDIO_TOKEN = os.environ.get('STUDIO_TOKEN')



CHEF_USER = 'chef'
CHEF_REPO_URL = 'https://github.com/learningequality/sushi-chef-tessa.git'
GIT_BRANCH = 'master'
CHEFS_DATA_DIR = '/data'
CHEF_PROJECT_SLUG = 'sushi-chef-tessa'
CHEF_DATA_DIR = os.path.join(CHEFS_DATA_DIR, CHEF_PROJECT_SLUG)

CRAWLING_STAGE_OUTPUT_TPL = 'web_resource_tree_{}.json'
SCRAPING_STAGE_OUTPUT_TPL = 'ricecooker_json_tree_{}.json'


@task
def chef_info():
    with cd(CHEF_DATA_DIR):
        sudo("ls")
        sudo("whoami")
        run("ls")
        run("whoami")



# RUN CHEF
################################################################################

@task
def run_tessa():
    for lang in ['sw', 'ar', 'fr', 'en']:
        chef_run(lang)

@task
def chef_run(lang):
    with cd(CHEF_DATA_DIR):
        with prefix('source ' + os.path.join(CHEF_DATA_DIR, 'venv/bin/activate')):
            cmd = './tessa_chef.py  -v --reset --token={}  lang={}'.format(STUDIO_TOKEN, lang)
            sudo(cmd, user=CHEF_USER)



# GET RUN TREE OUTPUTS
################################################################################

@task
def get_trees(lang='all'):
    trees_dir = os.path.join(CHEF_DATA_DIR, 'chefdata', 'trees')
    local_dir = os.path.join('chefdata', 'vader', 'trees')

    if lang == 'all':
        langs = ['sw', 'ar', 'fr', 'en']
    else:
        langs = [lang]

    for lang in langs:
        web_resource_tree_filename = CRAWLING_STAGE_OUTPUT_TPL.format(lang)
        ricecooker_json_tree_filename = SCRAPING_STAGE_OUTPUT_TPL.format(lang)
        get(os.path.join(trees_dir, web_resource_tree_filename),
            os.path.join(local_dir, web_resource_tree_filename))
        # get(os.path.join(trees_dir, ricecooker_json_tree_filename),
        #     os.path.join(local_dir, ricecooker_json_tree_filename))



# SETUP
################################################################################

@task
def setup_chef():
    with cd(CHEFS_DATA_DIR):
        sudo('git clone  --quiet  ' + CHEF_REPO_URL)
        sudo('chown -R {}:{}  {}'.format(CHEF_USER, CHEF_USER, CHEF_DATA_DIR))
        # setup python virtualenv
        with cd(CHEF_DATA_DIR):
            sudo('virtualenv -p python3.5  venv', user=CHEF_USER)
        # install requirements
        activate_sh = os.path.join(CHEF_DATA_DIR, 'venv/bin/activate')
        reqs_filepath = os.path.join(CHEF_DATA_DIR, 'requirements.txt')
        # Nov 23: workaround____ necessary to avoid HOME env var being set wrong
        with prefix('export HOME=/data && source ' + activate_sh):
            sudo('pip install --no-input --quiet -r ' + reqs_filepath, user=CHEF_USER)
        puts(green('Cloned chef code from ' + CHEF_REPO_URL + ' in ' + CHEF_DATA_DIR))

@task
def unsetup_chef():
    sudo('rm -rf  ' + CHEF_DATA_DIR)
    puts(green('Removed chef direcotry ' + CHEF_DATA_DIR))




# GIT-BASED DEPLOYMENT
################################################################################

@task
def git_fetch():
    with cd(CHEF_DATA_DIR):
        sudo('git fetch origin  ' + GIT_BRANCH, user=CHEF_USER)

@task
def update():
    git_fetch()
    with cd(CHEF_DATA_DIR):
        sudo('git checkout ' + GIT_BRANCH, user=CHEF_USER)
        sudo('git reset --hard origin/' + GIT_BRANCH, user=CHEF_USER)
    # update requirements
    activate_sh = os.path.join(CHEF_DATA_DIR, 'venv/bin/activate')
    reqs_filepath = os.path.join(CHEF_DATA_DIR, 'requirements.txt')
    with prefix('export HOME=/data && source ' + activate_sh):
        sudo('pip install -U --no-input --quiet -r ' + reqs_filepath, user=CHEF_USER)

