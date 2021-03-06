# Copyright (c) 2016-present, Facebook, Inc.
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import argparse
import json
import logging
from pathlib import Path

from ..configuration import Configuration
from ..errors import Errors, PartialErrorSuppression
from ..filesystem import LocalMode, add_local_mode, path_exists
from ..repository import Repository
from .command import CommandArguments, ErrorSuppressingCommand


LOG: logging.Logger = logging.getLogger(__name__)


class StrictDefault(ErrorSuppressingCommand):
    def __init__(
        self,
        command_arguments: CommandArguments,
        *,
        repository: Repository,
        local_configuration: Path,
        remove_strict_headers: bool,
        fixme_threshold: int,
    ) -> None:
        super().__init__(command_arguments, repository)
        self._local_configuration: Path = local_configuration
        self._remove_strict_headers: bool = remove_strict_headers
        self._fixme_threshold: int = fixme_threshold

    @staticmethod
    def from_arguments(
        arguments: argparse.Namespace, repository: Repository
    ) -> "StrictDefault":
        command_arguments = CommandArguments.from_arguments(arguments)
        return StrictDefault(
            command_arguments,
            repository=repository,
            local_configuration=arguments.local_configuration,
            remove_strict_headers=arguments.remove_strict_headers,
            fixme_threshold=arguments.fixme_threshold,
        )

    @classmethod
    def add_arguments(cls, parser: argparse.ArgumentParser) -> None:
        super(StrictDefault, cls).add_arguments(parser)
        parser.set_defaults(command=cls.from_arguments)
        parser.add_argument(
            "-l",
            "--local-configuration",
            type=path_exists,
            help="Path to project root with local configuration",
        )
        parser.add_argument(
            # TODO(T53195818): Not implemented
            "--remove-strict-headers",
            action="store_true",
            help="Delete unnecessary `# pyre-strict` headers.",
        )
        parser.add_argument(
            "--fixme-threshold",
            type=int,
            default=0,
            help="Mark file as unsafe if fixme count exceeds threshold.",
        )

    def run(self) -> None:
        project_configuration = Configuration.find_project_configuration()
        local_configuration = self._local_configuration
        if local_configuration:
            configuration_path = local_configuration / ".pyre_configuration.local"
        else:
            configuration_path = project_configuration
        with open(configuration_path) as configuration_file:
            configuration = Configuration(
                configuration_path, json.load(configuration_file)
            )
            LOG.info("Processing %s", configuration.get_directory())
            configuration.add_strict()
            configuration.write()
            all_errors = configuration.get_errors()

            if len(all_errors) == 0:
                return

            for path, errors in all_errors:
                errors = list(errors)
                error_count = len(errors)
                if error_count > self._fixme_threshold:
                    add_local_mode(path, LocalMode.UNSAFE)
                else:
                    try:
                        self._suppress_errors(Errors(errors))
                    except PartialErrorSuppression:
                        LOG.warning(f"Could not suppress all errors in {path}")
                        LOG.info("Run with --unsafe to force suppression anyway.")
                        self._repository.revert_all(remove_untracked=True)

            if self._lint:
                self._repository.format()
