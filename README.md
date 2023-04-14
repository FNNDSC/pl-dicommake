# DICOM image make

[![Version](https://img.shields.io/docker/v/fnndsc/pl-dicommake?sort=semver)](https://hub.docker.com/r/fnndsc/pl-dicommake)
[![MIT License](https://img.shields.io/github/license/fnndsc/pl-dicommake)](https://github.com/FNNDSC/pl-dicommake/blob/main/LICENSE)
[![ci](https://github.com/FNNDSC/pl-dicommake/actions/workflows/ci.yml/badge.svg)](https://github.com/FNNDSC/pl-dicommake/actions/workflows/ci.yml)

`pl-dicommake` is a [_ChRIS_](https://chrisproject.org/) _DS_ plugin that _makes_ new DICOM files from existing `DICOM` files and separate image files. Each new `DICOM` is simply the result of packing the existing image file into the corresponding existing `DICOM` base, with necessary updates to the DICOM header. 

## Abstract

Creating new DICOM files requires two fundamental preconditions: an _image_ and _metadata_. For this plugin, inputs are an _image_ and an existing DICOM file. The output is a new DICOM file with the _image_ embedded using most of the _metadata_ from the supplied DICOM. Where required, the new file's DICOM tags are changed to properly describe the image. Note that this plugin can operate over sets of input images -- one set of input `DICOM` files and a corresponding set of input image files. It is a required precondition that the file stem of each file in the `DICOM` set corresponds to a similar file stem in the image set.

## Installation

`pl-dicommake` is a _[ChRIS](https://chrisproject.org/) plugin_, meaning it can run from either within _ChRIS_ or the command-line.

## Preconditions / assumptions

`dicommake` has a few somewhat brittle preconditions on the nature of its `inputdir` space:

* `inputdir` contains _I_ >= 1 _image_ files (typically `png` or `jpg`) -- moreover there is only _one_ type of image file (no mixing of `png` and `jpg`, for example);
* `inputdir` contains _D_ >= 1 `DICOM` files;
* importantly, the number of elements in each set of files is identical, i.e. _D_ = _I_
* sorting the lists of _I_ and _D_ result in matched pairs such that the file _stems_ (names without extensions) of paired image and `DICOM` files are identical:
    * `forEach` _i_ ∈ _I_ `and` _d_ ∈ _D_ : `stem`(_i_) == `stem`(_d_);


## Local Usage

To get started with local command-line usage, use [Apptainer](https://apptainer.org/) (a.k.a. Singularity) to run `pl-dicommake` as a container:

```shell
apptainer exec docker://fnndsc/pl-dicommake dicommake [--args values...] input/ output/
```

Alternatively, create a singularity `sif` file:

```shell
apptainer build pl-dicommake.sif docker://fnndsc/pl-dicommake
```

To print its available options, run:

```shell
apptainer exec docker://fnndsc/pl-dicommake dicommake --help
```

## Examples

`dicommake` requires two positional arguments: a directory containing input data, and a directory where to create output data. First, create the input directory and move input data into it.

```shell
mkdir incoming/ outgoing/
mv image.png file.dcm incoming/
apptainer exec docker://fnndsc/pl-dicommake:latest dicommake --inputImageFilter '**/*png' \
        incoming/ outgoing/
```

## Development

Instructions for developers.

### Building

Build a local container image:

```shell
docker build -t localhost/fnndsc/pl-dicommake .
```

### Running

Mount the source code `dicommake.py` into a container to try out changes without rebuild.

```shell
docker run --rm -it --userns=host -u $(id -u):$(id -g) \
    -v $PWD/dicommake.py:/usr/local/lib/python3.11/site-packages/dicommake.py:ro \
    -v $PWD/in:/incoming:ro -v $PWD/out:/outgoing:rw -w /outgoing \
    localhost/fnndsc/pl-dicommake dicommake /incoming /outgoing
```

### Testing

Run unit tests using `pytest`.
It's recommended to rebuild the image to ensure that sources are up-to-date.
Use the option `--build-arg extras_require=dev` to install extra dependencies for testing.

```shell
docker build -t localhost/fnndsc/pl-dicommake:dev --build-arg extras_require=dev .
docker run --rm -it localhost/fnndsc/pl-dicommake:dev pytest
```

## Release

Steps for release can be automated by [Github Actions](.github/workflows/ci.yml). This section is about how to do those steps manually.

### Increase Version Number

Increase the version number in `setup.py` and commit this file.

### Push Container Image

Build and push an image tagged by the version. For example, for version `1.2.3`:

```
docker build -t docker.io/fnndsc/pl-dicommake:1.2.3 .
docker push docker.io/fnndsc/pl-dicommake:1.2.3
```

### Get JSON Representation

Run [`chris_plugin_info`](https://github.com/FNNDSC/chris_plugin#usage)
to produce a JSON description of this plugin, which can be uploaded to a _ChRIS Store_.

```shell
docker run --rm localhost/fnndsc/pl-dicommake:dev \
    chris_plugin_info > chris_plugin_info.json
```

