from sysconfig import get_config_var
from typing import Callable
import pkg_resources as pr
from time import sleep
import subprocess
import itertools
import tempfile
import platform
import tarfile
import urllib3
import shutil
import json
import sys
import os
 


try:
    from pip._internal.operations.install.wheel import install_wheel
    from pip._internal.locations import get_scheme
    import wheel

except ModuleNotFoundError:
    print("\033[91m\nPlease activate the virtual environment to use Packs\n\033[37m")
    sys.exit(0)

try:
    from Packs.Utils.versionControl import (lessThan, moreThan, equals, byteCalc, combine, equalSerie, validVersionPython, notEquals)
    from Packs.Utils.dependenciesControl import addDependencies, openToCreate, removeDependency
    from Packs.Utils.cliControl import listArgsInstall, pureDependency
    from Packs.Utils.logger import Logger
    from Packs.Commands import remove

except (ModuleNotFoundError, ImportError):
    from Utils.versionControl import (lessThan, moreThan, equals, byteCalc, combine, equalSerie, validVersionPython, notEquals)
    from Utils.dependenciesControl import addDependencies, openToCreate, removeDependency
    from Utils.cliControl import listArgsInstall, pureDependency
    from Utils.logger import Logger
    from Commands import remove


class Installer:
    def __init__(self, args:list, cli=False):
        temp = tempfile.gettempdir()
        self.__deps = []
        self.__dev = False
        self.__u = False
        self.__cpythonVersion = None
        
        openToCreate()

        if not os.path.exists(temp + "/packsX"):
            os.mkdir(temp + "/packsX")

        self.__getCpythonVersion()

        if (cli):
            self.run(args[2:])
            
        else:
            self.run(args)


    def __getCpythonVersion(self) -> None:
        """
            Get CPython version and save value on self.__cpythonVersion variable

        """

        number = get_config_var('SOABI')

        if number:
            number = str(get_config_var('SOABI')).split('-')[1]

            self.__cpythonVersion = f"cp{number}"


    def __normalizeVersion(self, version:str, res:dict) -> list:
        """
            Filter supported packages version in the package version list

            Parameters
            ----------
                version : str
                    name of package with your supported version
                res : dict
                    response from a package's Pypi API

            Returns
            -------
            list
                all subversions of a package version

            >>> __normalizeVersion('package==1.2.3', {"name": "package", "releases": [...], ...})
            [{"packagetype": "source", "python_version": "py3", ...}, ...]

        """

        version = version.lower().replace(res['info']['name'].lower(), '')
        releases = res['releases']

        versionControl = {
            "<": lessThan,
            "==": equals,
            '~': equalSerie,
            '>': moreThan,
            '!=': notEquals,
            '!': notEquals,
        }

        if "=" in version or ">" in version or "<" in version or "~=" in version:
            if "==" in version:
                return versionControl['=='](version, releases)

            else:
                vx = version.replace("(", '').replace(")", '').replace(' ', '').split(',')
                l = []

                for i in vx:
                    track = versionControl[i[0]](i, releases)

                    if "msg" in track:
                        return 'ErrorV'

                    l.append(track)

                c = combine(l)

                if len(c) > 0:
                    return c[len(c) - 1]

                return "ErrorR"

        c = releases[res['info']['version']]
        c.append(res['info']['version'])
        
        return c


    def __wheelInstall(self, name:str, filewhl:str) -> bool:
        """
            Install .whl package

            Parameters
            ----------
                name : str
                    name of package
                filewhl : str
                    path of package file

            Returns
            -------
            bool
                whether the package is installed

            >>> __wheelInstall("package", "/tmp/packsX/package.whl")
            False

            >>> __wheelInstall("package", "/tmp/packsX/package.whl")
            True

        """

        try:
            pack = pr.get_distribution(name)

        except Exception:
            scheme = get_scheme(
                name,
                user=False,
                home=None,
                root=None,
                prefix=None,
            )

            install_wheel(
                name,
                filewhl,
                scheme=scheme,
                req_description=name,
                pycompile=True,
            )

            return False

        if self.__u:
            removeDependency(f"{pack.key}=={pack.version}")

            scheme = get_scheme(
                name,
                user=False,
                home=None,
                root=None,
                prefix=None,
            )

            install_wheel(
                name,
                filewhl,
                scheme=scheme,
                req_description=name,
                pycompile=True,
            )

            return False

        return True


    def __tarInstall(self, name:str, filewhl:str) -> bool:
        """
            Install .tar package

            Parameters
            ----------
                name : str
                    name of package
                filewhl : str
                    path of package file

            Returns
            -------
            bool
                whether the package is installed

            >>> __tarInstall("package", "/tmp/packsX/package.tar")
            False

            >>> __tarInstall("package", "/tmp/packsX/package.tar")
            True

        """

        temp = tempfile.gettempdir()
        p = os.getcwd()

        try:
            pack = pr.get_distribution(name)

        except Exception:
            with tarfile.open(filewhl, 'r:gz') as tar:
                tar.extractall(temp + "/packsX")

            os.chdir(filewhl.replace(".tar.gz", ''))

            FNULL = open(os.devnull, 'w')

            subprocess.run(['python', 'setup.py', 'install'], stdout=FNULL, stderr=subprocess.PIPE)

            os.chdir(p)
            return False

        if self.__u:
            removeDependency(f"{pack.key}=={pack.version}")

            with tarfile.open(filewhl, 'r:gz') as tar:
                tar.extractall(temp + "/packsX")

            os.chdir(filewhl.replace(".tar.gz", ''))

            FNULL = open(os.devnull, 'w')

            subprocess.run(['python', 'setup.py', 'install'], stdout=FNULL, stderr=subprocess.PIPE)
            
            os.chdir(p)

            return False

        return True


    def __cpythonChecker(self, vers:list) -> list:
        """
            Find the subversion of a package that supports the installed version of CPython

            Parameters
            ----------
                vers : list
                    List of all subversions of a specific version of a package

            Returns
            -------
            List
                List of Supported subversions

            >>> __cpythonChecker([{"python_version": "cp38"}, {"python_version": "cp37"}, {"python_version": "py3"}])
            [{"python_version": "cp38"}]

            >>> __cpythonChecker([{"python_version": "cp37"}, {"python_version": "py3"}])
            [{"python_version": "py3"}]

        """

        vs = []

        for i in vers:
            if self.__cpythonVersion and i['python_version'].startswith(self.__cpythonVersion):
                vs.append(i)

        if len(vs) == 0:
            for i in vers:
                if i['python_version'] == "py3":
                    vs.append(i)

            if len(vs) == 0:
                return [vers[0]]

        return vs


    def __archAndSystemChecker(self, vers:list, typex:str, arc:str) -> list:
        """
            Finds a subversion compatible with the OS and its respective architecture

            Parameters
            ----------
                vers : list
                    List of all subversions of a specific version of a package

                typex : str
                    OS machine name

                arc : str
                    Processor architecture

            Returns
            -------
            List
                List of Supported subversions

            >>> __archAndSystemChecker([{"filename": "...-win32..."}, {"filename": "...-manylinux2014_x86_64..."}], "-win32", "")
            [{"filename": "...-win32..."}]

            >>> __archAndSystemChecker([{"filename": "...-win32..."}, {"filename": "...-manylinux2014_x86_64..."}], "--manylinux", "x86_64")
            [{"filename": "...-manylinux2014_x86_64..."}]

        """

        vs = []

        for i in vers:
            if typex in i['filename'] and arc in i['filename']:
                vs.append(i)

        return vs


    def  __processerChecker(self, vers:list) -> list:
        """
            Get de OS machine name and processor architecture

            Parameters
            ----------
                vers : list
                    List of all subversions of a specific version of a package

            Returns
            -------
            List
                Returns of __archAndSystemChecker

            >>> __processerChecker([{"filename": "...-win32..."}, {"filename": "...-manylinux2014_x86_64..."}])
            [{"filename": "...-win32..."}]

            >>> __processerChecker([{"filename": "...-win32..."}, {"filename": "...-manylinux2014_x86_64..."}])
            [{"filename": "...-manylinux2014_x86_64..."}]

        """

        system = platform.system()

        if system == "Windows":
            typex = "-win32"
            arc = ""

        elif system == "Linux":
            typex = "-manylinux"
            arc = platform.machine()

        else:
            typex = "-macosx_"
            arc = platform.machine()

        return self.__archAndSystemChecker(vers, typex, arc)


    def __checkTypeInstallation(self, vers:list) -> list:
        """
            Find the best installation file from a list of subversions in a package

            Parameters
            ----------
                vers : list
                    List of all subversions of a specific version of a package

            Returns
            -------
            List
                A list with the data of an installer and its installation function

            >>> ____checkTypeInstallation([{"filename": "package.tar", ...}, {"filename": "package.whl", ...}])
            [{"filename": "package.whl", ...}, self.__wheelInstall]

            >>> ____checkTypeInstallation([{"filename": "package.tar", ...}])
            [{"filename": "package.tar", ...}, self.__tarInstall]
        """

        remote = [i for i in vers if i['url'].endswith('.whl')]

        if len(remote) == 0:
            return [vers[0], self.__tarInstall]

        elif len(remote) == 1:
            return [remote[0], self.__wheelInstall]

        else:
            return [self.__cpythonChecker(self.__processerChecker(vers))[0], self.__wheelInstall]

    
    def __downloadPackage(self, url:str, filew:str, http:urllib3.PoolManager) -> None:
        """
            Download package installation file

            Parameters
            ----------
                url : str
                    Url of installation file

                filew : str
                    Name of installation file

                http : urllib3.PoolManager
                    Urllib PoolManager web connection

            >>> __downloadPackage("https://domain.com/package.whl", "package.whl", urllib3.PoolManager())
            None
        """
        if os.path.exists(filew):
            return

        files = http.request("GET", url)

        with open(filew, "wb") as f:
            f.write(files.data)

    
    def __installPackageDependencies(self, res:dict, http:urllib3.PoolManager, version:str) -> list:
        """
            Find, download and install dependencies package

            Parameters
            ----------
                res : dict
                    response from a package's Pypi API

                filew : str
                    Name of installation file

                http : urllib3.PoolManager
                    Urllib PoolManager web connection

                version : str
                    Package version to be installed

            Returns
            -------
            List
                A list containing the installation result, size and version

        """
        temp = tempfile.gettempdir()

        vers = self.__normalizeVersion(version, res)
        vx = vers.pop()

        if vers == "ErrorR":
            Logger("ERROR there is no version that satisfies the condition", 'red')
            return

        if vers == "ErrorV":
            return
        
        remote = self.__checkTypeInstallation(vers)

        self.__downloadPackage(remote[0]['url'], temp + f"/packsX/{remote[0]['filename']}", http)

        return [remote[1](res['info']['name'], temp + f"/packsX/{remote[0]['filename']}"), remote[0]['size'], vx]
        

    def __installPackage(self, res:dict, http:urllib3.PoolManager, version:str) -> dict:
        """
            Find, download and install package

            Parameters
            ----------
                res : dict
                    response from a package's Pypi API

                filew : str
                    Name of installation file

                http : urllib3.PoolManager
                    Urllib PoolManager web connection

                version : str
                    Package version to be installed

            Returns
            -------
            list
                all subversions of a package version

        """

        temp = tempfile.gettempdir()
        vers = self.__normalizeVersion(version, res)
        v = vers.pop()

        if vers == "ErrorR":
            Logger("ERROR there is no version that satisfies the condition", 'red')
            return

        if vers == "ErrorV":
            return "error"
        
        remote = self.__checkTypeInstallation(vers)

        Logger(f"\nPackage {res['info']['name']} found in version {v} ({byteCalc(remote[0]['size'])})", 'green')

        Logger(f"\nDownloading {res['info']['name']}", 'pink', end='\r')
        self.__downloadPackage(remote[0]['url'], temp + f"/packsX/{remote[0]['filename']}", http)
        Logger(f"{'Download finish':50}", 'green')

        Logger(f"\nInstalling {res['info']['name']}", 'pink', end='\r')

        installed = remote[1](res['info']['name'], temp + f"/packsX/{remote[0]['filename']}")
        
        if not installed:
            addDependencies(f"{res['info']['name']}=={v}", self.__dev)
            Logger(f"{res['info']['name']} was successfully installed", 'green')

        else:
            Logger(f"{res['info']['name']} already installled", 'blue')

        return remote[0]


    def __dependenciesLoop(self, reqs:list, fun:Callable, http:urllib3.PoolManager, spacer:int = 3) -> None:
        """
            Find all dependencies and install

            Parameters
            ----------
                reqs : list
                    List of dependencies

                fun : str
                    Callback

                http : urllib3.PoolManager
                    Urllib PoolManager web connection

                spacer : str
                    number of left spaces
        """

        for i in reqs:
            if '; extra' in i or i.split(' ')[0] in self.__deps or "and extra" in i: 
                continue
            
            if "; python_version" in i and not validVersionPython(i.split("; python_version ")[1].replace('"', '')):
                continue

            i = i.split(" ; ")[0]
            self.__deps.append(i.split(' ')[0])

            Logger(f"{' ' * spacer}{i.split(' ')[0]}", end="\r")
            
            dependencieResult = fun(i, http, spacer)
            
            Logger(f"{' ' * spacer}{dependencieResult[0]}", 'green')

            if len(dependencieResult) > 1:
                dependencieResult[1](*dependencieResult[2])

    
    def __dependencies(self, pack:str, http:urllib3.PoolManager, spacer:int) -> list:
        """
            Download and install package dependencies

            Parameters
            ----------
                pack : list
                    Package name

                http : urllib3.PoolManager
                    Urllib PoolManager web connection

                spacer : str
                    number of left spaces

            Returns
            -------
            list
                a list containing the message for the Logger, if you have subdependencies you will also have __dependenciesLoop and the list of subdependencies
        """

        packinfo = http.request("GET", f"https://pypi.org/pypi/{pack.split(' ')[0]}/json/")

        if packinfo.status == 404:
            return "error"

        packinfo = json.loads(packinfo.data.decode())
        inst = self.__installPackageDependencies(packinfo, http, pack)

        ret = [f"{packinfo['info']['name']}=={inst[2]} ({byteCalc(inst[1])})"]

        if packinfo['info']['requires_dist']:
            ret.append(self.__dependenciesLoop)
            ret.append([packinfo['info']['requires_dist'], self.__dependencies, http, spacer + 3])

        if inst[0]:
            ret[0] = f"\033[94m{packinfo['info']['name']}=={inst[2]} already installled ({byteCalc(inst[1])})"

            return ret 
            
        addDependencies(f"{packinfo['info']['name']}=={inst[2]}", self.__dev)

        return ret
        

    def __remote_package(self, pack:str, http:urllib3.PoolManager) -> dict:
        """
            Searches the API for package data

            Parameters
            ----------
                pack : list
                    Package name

                http : urllib3.PoolManager
                    Urllib PoolManager web connection

            Returns
            -------
            dict
                Package data from API
        """

        packName = pack.replace("=", ' ').replace(">", ' ').replace("<", ' ').replace("~", ' ').replace("!", ' ').split(' ')[0]
    
        packinfo = http.request("GET", f"https://pypi.org/pypi/{packName}/json/")
            
        if packinfo.status == 404:
            Logger(f"Package {packName} not found", 'red')
            return {}

        packinfo = json.loads(packinfo.data.decode())

        if packinfo['urls'] == []:
            Logger(f"Package {packName} don't have a version for install", 'red')
            return {}

        pac = self.__installPackage(packinfo, http, pack)

        if pac == 'error':
            return
                
        if packinfo['info']['requires_dist']:
            Logger(f"\n{packName} dependencies:", 'yellow')

            self.__dependenciesLoop(packinfo['info']['requires_dist'], self.__dependencies, http, 3)
        
        Logger("\n")

        return packinfo


    def run(self, args:list) -> None:
        http = urllib3.PoolManager()
        
        commands = listArgsInstall(args)
        self.__dev = commands[1]
        self.__u = commands[2]

        for i in commands[0]:
            if self.__u:
                remove.Remover([pureDependency(i), '--yes'])
            
            res = self.__remote_package(i, http)

            if res == {}:
                continue