import os

from fabric.api import env, task, local, sudo, run
from fabric.context_managers import cd, prefix, show, hide, shell_env
from fabric.colors import red, green, blue, yellow
from fabric.utils import puts

env.hosts = [
    'eslgenie.com:1',  # vader runs ssh on port 1
]
env.user = os.environ.get('USER')
env.password = os.environ.get('VADER_PASSWORD')


CHEF_USER = 'chef'
CHEF_REPO_URL = 'https://github.com/learningequality/sushi-chef-tessa.git'
GIT_BRANCH = 'master'
CHEFS_DATA_DIR = '/data'
CHEF_PROJECT_SLUG = 'sushi-chef-tessa'
CHEF_DATA_DIR = os.path.join(CHEFS_DATA_DIR, CHEF_PROJECT_SLUG)


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
def chef_info():
    with cd(CHEF_DATA_DIR):
        sudo("ls", user=CHEF_USER)
        sudo("whoami", user=CHEF_USER)
        run("ls")
        run("whoami")



# SETUP
################################################################################
@task
def setup_chef():
    with cd(CHEFS_DATA_DIR):
        sudo('git clone  --quiet  ' + CHEF_REPO_URL)
        sudo('chown -R {}:{}  {}'.format(CHEF_USER, CHEF_USER, CHEF_DATA_DIR))
        # with prefix("source activate"):
        #     sudo("pip install -r requirements.txt")
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

