> This repository is **ARCHIVED**.
> I used to use NGINX in a jail on my FreeNAS system, but I'm switching to Ubuntu Server with Docker and Traefik as a reverse proxy.
> Traefik can already do what this script does out of the box, so I won't need this script anymore.

# :arrow_right_hook: revprox
Set of scripts to allow for an easy set-up of a reverse proxy with SSL support,
so you can access all your hobby projects running at home without having to
remember all those port numbers.

Based on / uses:
* [NGINX](https://www.nginx.com/)
* [Sewer](https://github.com/komuw/sewer)
* [YAML](http://yaml.org/)

## :warning: Current state
I have been using this for quite some time now in a jail on my FreeNAS system, but I'm still facing some issues with the auto renewal.
Besides that more documentation is probably needed (now there is only an `example-config.yml` and that's pretty much it).

The update script is also not yet added to the crontab automatically.

## Setup
* Create a new, private Git repository. I currently use GitLab, but any other service will probably also work (GitHub, Bitbucket, ...)
* Generate an access token that can read the aforementioned repository (link for [GitLab](https://gitlab.com/profile/personal_access_tokens) / [GitHub](https://github.com/settings/tokens) / [Bitbucket](https://confluence.atlassian.com/bitbucket/app-passwords-828781300.html#Apppasswords-Createanapppassword) )
* Clone/download the repository to the machine running NGINX (I'm assuming it's already installed).
* Run `src/setup.py` and follow the instructions.
* TODO: Add instructions for update script cron as it is not yet in the script itself.
