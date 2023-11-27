# View MRs of interest in gitlab

## Installation
[Install python 3](https://www.python.org/downloads/).

Run the following (maybe you will be asked by pip to enter gitHub credentials)
```shell
pip3 install git+https://github.com/vlanse/pymr.git#egg=pymr
```

## Usage
Create `pymr-config.yaml` like this in your home folder
```yaml
config:
  gitlab: 'https://gitlab.com'
  token: "gitlab private token"
  team: [dev1_login, dev2_login] # team of interest, see show_only_team option below
  robots: [some-robot-account] # automation accounts usernames, to highlight MRs by API clients with special avatar
  groups:
    project-group-1:
      # per-group setting section
      show_only_my: true  # if only MRs authored by current user are needed for some reason, this overrides show_only_team option
      projects:
        my_amazing_repo:
          id: PROJECT_ID

    project-group-2:
      projects:
        another_repo:
          id: PROJECT_ID_2

    project-group-3:
      show_only_team: true # only team's MRs will be shown
      projects:
        another_repo:
          id: PROJECT_ID_2
```

Put gitlab address and access token there, write your projects with their IDs

Run:

```shell
mr
```
Possible result:

<img width="897" alt="mr-result" src="https://user-images.githubusercontent.com/17192647/219855788-44f70d64-1d95-4b96-81e4-8eb1f794a26f.png">

(in some modern terminal emulators like iTerm MRs captions are clickable links)

Symbols meaning in output:

🛑 - MR has unresolved conflicts

💥 - pipeline has failed

🚦 - pipeline has succeeded, no problems detected

⏳ - waiting for some action

💀 - MR is too old (> 10d for now)

🤖 - MR is created by 'robot', see `robots` section in config


To list available options, run:
```shell
mr --help
```

## Installation for development
Install virtualenv package (`pip3 install virtualenv`).

```bash
git clone https://github.com/vlanse/pymr.git && cd pymr
make develop # virtualenv with installed dependencies will be created
```

`mr` script will be installed in virtualenv bin folder
