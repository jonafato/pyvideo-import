from importlib.util import spec_from_file_location, module_from_spec
import sys
from types import ModuleType

import argh


def _import_source_file(filename: str) -> ModuleType:
    spec = spec_from_file_location("conferences", filename)
    module = module_from_spec(spec)
    sys.modules["conferences"] = module
    spec.loader.exec_module(module)
    return module


def import_data(conferences_module: str, conference: str, output_directory: str) -> None:
    conferences = _import_source_file(conferences_module)
    conference = getattr(conferences, conference)
    conference.pyvidify(output_directory)


def __main__():
    argh.dispatch_commands([import_data])
