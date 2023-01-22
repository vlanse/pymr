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
  groups:
    project-group-1:
      # per-group setting section
      show_only_my: true  # if only MRs authored by current user are needed for some reason
      projects:
        my_amazing_repo:
          id: PROJECT_ID

    project-group-2:
      projects:
        another_repo:
          id: PROJECT_ID_2
```

Put gitlab address and access token there, write your projects with their IDs

Run:

```shell
mr
```


## Installation for development
Install virtualenv package (`pip3 install virtualenv`).

```bash
git clone https://github.com/vlanse/pymr.git && cd pymr
make develop # virtualenv with installed dependencies will be created
```

`mr` script will be installed in virtualenv bin folder
