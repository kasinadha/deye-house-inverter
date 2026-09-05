import unittest

from deye_house.cli import build_parser


class ParserTests(unittest.TestCase):
    def test_commands(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["status"])
        self.assertEqual(args.command, "status")
        args = parser.parse_args(["apply", "--dry-run"])
        self.assertTrue(args.dry_run)
