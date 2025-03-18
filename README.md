# MiPi Environment Manager
___

This project provides a standard way to configure and distribute python environments. It is intended to be a simpler
solution than Docker, for when docker is not available or practical. This project creates a series of requirments.txt
files and installer batch files for each. It automatically installs each environment as per the specs of a Yaml configuration file.
This command can be scheduled, so that each requirements.txt file and environment area always up to date with the
correct versions and environment variables.

My team uses this since we do not have docker. Every day this script is scheduled to run and update the environment
installers. Then  every developer's computer is scheduled to install the environments. Our production server does the
same thing so that all environments match, and are up to date.

## Quick Start

### 1. Setup the Yaml file
this file configures each environment's dependencies.

```yml
environments:
  {example-environment-name}:
    setup: (setup for this environment)
      py_version: { your-python-version }
      include_in_master: { boolean-value }
    packages:
      { package-name }:
        source: { where-to-get (github/pypi)}
        version: { semantic-version }
        version_policy: { policy (exact/no_major_increment) }
        path: {github/repo/url (github repos only)}

setup: (local setup for all environments)
  outpath: { path/to/root/folder (where environments management files will be created)}
  environment_variables:
    { environment-key }: { environment-value }
```
#### YAML Options

- example-environment-name:
    - string name of the conda environment
    - you can create more than one environment. each will get its own requirements.txt and install.bat files
- package-name
    - for pypi packages: name of the package to install
    - for github packages: name to install the github release as
- source
    - where to download the package
    - options:
        - "github": install a release from a github repo
        - "pypi": install a pypi package
- version
    - semantic version to install
    - github: strip the "v" from the release tag and downloads that version
    - pypi: version
- version policy
    - options:
        - "exact": install the exact version of a package
        - "no_major_increment": get the version of the package but do not allow for a "major" update
        - (not specified): if this option is not specified. It will get the exact version option. If the exact version is not specified it will grab the latest
- path
    - url to the github repo if applicable

### 2. Configure environment variables for the script
    - GH_TOKEN: personal access token to github. This is used to query the tags for repo releases. This is required
              otherwise github would install the latest commit.
    - MIPI_DEVOPS_PATH: path to where this file is saved locally on the computer

### 3. Run (schedule) the script `mipi publish-envs` #end point not yet implemented

### 4. install any or all environments using batch files

#### Installer file structure

/root_folder contains:
- master_installer.bat: run this to install all environments which used "include_in_master" option. This also creates environment variables
- one directory per environment

/root_folder/environment_folder contains:
- requirments.txt 
- create_env.bat: run this to install the environment. overwrites it if it already exists
- update_env.bat: run this to update the environment without overwriting it. This is much faster

