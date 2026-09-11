import unittest

from deye_house.cli import build_parser
from deye_house.client import env_file_path


class ParserTests(unittest.TestCase):
    def test_commands(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["status"])
        self.assertEqual(args.command, "status")
        args = parser.parse_args(["apply", "--dry-run"])
        self.assertTrue(args.dry_run)
        args = parser.parse_args(["--villa", "villa431", "status"])
        self.assertEqual(args.villa, "villa431")
        self.assertEqual(args.command, "status")

    def test_villa_env_path(self) -> None:
        self.assertEqual(env_file_path("villa431", None), ".env.villa431")
        self.assertEqual(env_file_path(None, "secret.env"), "secret.env")
        self.assertEqual(env_file_path(None, None), ".env")
