# -*- coding: utf-8 -*-

# FOGLAMP_BEGIN
# See: http://foglamp.readthedocs.io/
# FOGLAMP_END

import os
import subprocess
import logging
import asyncio
from aiohttp import web
import aiohttp
import async_timeout
import tarfile
import shutil
import hashlib

from foglamp.common import logger
from foglamp.common.common import _FOGLAMP_ROOT


__author__ = "Ashish Jabble"
__copyright__ = "Copyright (c) 2019 Dianomic Systems"
__license__ = "Apache 2.0"
__version__ = "${VERSION}"


_help = """
    -------------------------------------------------------------------------------
    | POST             | /foglamp/plugins                                         |
    -------------------------------------------------------------------------------
"""
TIME_OUT = 120
CHUNK_SIZE = 1024
_LOGGER = logger.setup(__name__, level=logging.INFO)

_PATH = _FOGLAMP_ROOT + '/data/plugins/'


# TODO: Add unit tests
async def add_plugin(request: web.Request) -> web.Response:
    """ add plugin

    :Example:
        curl -X POST http://localhost:8081/foglamp/plugins
        data:
            URL - The URL to pull the plugin file from
            format - the format of the file. One of tar or package
            compressed - option boolean this is used to indicate the package is a compressed gzip image
            checksum - the checksum of the file, used to verify correct upload
    """
    try:
        data = await request.json()
        url = data.get('url', None)
        file_format = data.get('format', None)
        compressed = data.get('compressed', None)
        # TODO: Better if we add plugin type (mandatory)
        _type = data.get('type', None)
        checksum = data.get('checksum', None)
        if not url or not file_format or not _type or not checksum:
            raise TypeError('URL, checksum, plugin type and format are mandatory.')
        # TODO: add later for notification delivery and rules plugins
        if _type not in ['filter', 'north', 'south']:
            raise ValueError("Invalid type you have supplied; Accepted types are filter, north, south")
        if file_format not in ["tar", "deb"]:
            raise ValueError("Invalid format you supplied; Accepted format are tar and deb")
        if compressed:
            if compressed not in ['true', 'false', True, False]:
                raise ValueError('Only "true", "false", true, false are allowed for value of compressed.')
        is_compressed = ((isinstance(compressed, str) and compressed.lower() in ['true']) or (
            (isinstance(compressed, bool) and compressed is True)))

        # All stuff goes into _PATH
        if not os.path.exists(_PATH):
            os.makedirs(_PATH)

        result = await download([url])
        # _LOGGER.info("Result {} ".format(result))
        file_name = result[0].split('Successfully downloaded ')[-1]
        # _LOGGER.info("file_name {} {}".format(file_name, checksum))

        # TODO: only validate with MD5sum. Do we need to validate with SHA1, SHA256, SHA512?
        # if yes then we need to add checksum type attribute in request
        if validate_checksum(checksum, file_name) is False:
            raise ValueError("Checksum is failed.")

        # TODO: tar this downloaded file under _PATH and install plugin FOGLAMP_ROOT
        _LOGGER.info("Found {} format with compressed {}".format(file_format, is_compressed))
        _files = extract_file(file_name, is_compressed)
        _LOGGER.info("Files {} {}".format(_files, type(_files)))
        if file_format == 'tar':
            copy_file_install_requirement(_files, _type)
        else:
            install_debian(_files[0])
    except (TypeError, ValueError) as ex:
        raise web.HTTPBadRequest(reason=str(ex))
    except Exception as ex:
        raise web.HTTPException(reason=str(ex))
    else:
        return web.json_response({"message": "{} and installed".format(result)})


async def get_url(url: str, session: aiohttp.ClientSession) -> str:
    file_name = str(url.split("/")[-1])
    async with async_timeout.timeout(TIME_OUT):
        async with session.get(url) as response:
            with open(_PATH + file_name, 'wb') as fd:
                async for data in response.content.iter_chunked(CHUNK_SIZE):
                    fd.write(data)
    return 'Successfully downloaded ' + file_name


async def download(urls: list) -> asyncio.gather:
    async with aiohttp.ClientSession() as session:
        tasks = [get_url(url, session) for url in urls]
        return await asyncio.gather(*tasks)


def validate_checksum(checksum: str, file_name: str) -> bool:
    original = hashlib.md5(open(_PATH + file_name, 'rb').read()).hexdigest()
    return True if original == checksum else False


def extract_file(file_name: str, is_compressed: bool) -> list:
    mode = "r:gz" if is_compressed else "r"
    tar = tarfile.open(_PATH + file_name, mode)
    _LOGGER.info("Extracted to {}".format(_PATH))
    tar.extractall(_PATH)
    _LOGGER.info("Extraction Done!!")
    # _LOGGER.info(tar.getnames())
    return tar.getnames()


def install_debian(file_name: str):
    # FIXME: Not working seems like we need to manipulate in /etc/sudoers.d/foglamp file
    # subprocess.run(["sudo cp {} /var/cache/apt/archives/.".format(file_name)], shell=True, check=True)
    # subprocess.run(["sudo apt install /var/cache/apt/archives/{}".format(file_name)], shell=True, check=True)
    pass


def copy_file_install_requirement(_file: list, _type: str):
    _py = any(f.endswith(".py") for f in _file)
    _so = any(f.endswith(".so") for f in _file)
    _so_1 = any(f.endswith(".so.1") for f in _file)

    if _py:
        _LOGGER.exception("Python plugin found")

    if _so:
        if _so_1:
            _LOGGER.exception("C plugin found")
        else:
            _LOGGER.exception("Not a valid C plugin")

    if not _py and not _so:
        _LOGGER.exception("Invalid plugin found")
        raise ValueError

    dir = []
    for s in _file:
        print(s)
        dir.append(s.split("/")[-1])

    assert len(dir), "No data found"
    plugin_name = dir[0]
    _LOGGER.exception("plugin name {}  dir {} ".format(plugin_name, dir))

    _plugin_path = "python/foglamp/plugins" if _py else "plugins"
    dest_path = "{}/{}/{}/".format(_FOGLAMP_ROOT, _plugin_path, _type)
    _LOGGER.exception("dest {}".format(dest_path))

    if os.path.exists(dest_path + plugin_name) and os.path.isdir(dest_path + plugin_name):
        shutil.rmtree(dest_path + plugin_name)
    shutil.copytree(_PATH + plugin_name, dest_path + plugin_name)
    _LOGGER.exception("file copied....to {}".format(dest_path))

    if "requirements.sh" in dir:
        _LOGGER.exception("INSTALL PIP Dep.... {}".format(dest_path + plugin_name + "/" + "requirements.sh"))
        subprocess.run(["sh {}".format(dest_path + plugin_name + "/" + "requirements.sh")], shell=True)
