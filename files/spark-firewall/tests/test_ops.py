"""The operations and the helper: what is accepted, which command lines come out, and that
nothing else can get through. The helper runs against a fake runner; no command is executed."""

import io
import json
import unittest

import support
from sparkfirewall import helper, ops

UUID = "5b9c2d4e-1f2a-4c3b-8d9e-0a1b2c3d4e5f"


def run_helper(payload, runner=None):
    runner = runner or support.FakeRun()
    out, err = io.StringIO(), io.StringIO()
    code = helper.apply(payload if isinstance(payload, str) else json.dumps(payload), runner,
                        out, err)
    return code, runner, out.getvalue(), err.getvalue()


def mutating(runner):
    """The calls that are not reads."""
    reads = ("--state", "--get-", "--info-service", "--list-all", "is-enabled")
    return [c for c in runner.calls if not any(r in " ".join(c) for r in reads)]


class Validation(unittest.TestCase):
    def test_a_service_and_a_port(self):
        clean = ops.validate([
            {"op": "service", "zone": "public", "name": "steam-streaming", "add": True},
            {"op": "port", "zone": "home", "port": " 8080/TCP".strip().lower(), "add": False}])
        self.assertEqual(clean[0]["name"], "steam-streaming")
        self.assertEqual(clean[1]["port"], "8080/tcp")

    def test_ports_are_normalised(self):
        self.assertEqual(ops.normalise_port("5000-5010/udp"), "5000-5010/udp")
        self.assertEqual(ops.normalise_port("80-80/tcp"), "80/tcp")

    def test_bad_ports(self):
        for bad in ("0/tcp", "65536/tcp", "80", "80/icmp", "9-1/tcp", "a/tcp", "80/tcp;id", "",
                    "-1/tcp", "80/sctp", None, 80):
            with self.subTest(port=bad):
                with self.assertRaises(ops.OpError):
                    ops.normalise_port(bad)

    def test_names_cannot_become_options_or_shell(self):
        bad_names = ["--reload", "-x", "a b", "a;b", "$(id)", "a/b", "", "x" * 70, "a\nb", None, 5]
        for bad in bad_names:
            for field, op in (("zone", {"op": "default-zone", "zone": bad}),
                              ("service", {"op": "service", "zone": "public", "name": bad,
                                           "add": True})):
                with self.subTest(field=field, value=bad):
                    with self.assertRaises(ops.OpError):
                        ops.validate([op])

    def test_devices_and_connections(self):
        ok = {"op": "network-zone", "device": "eno1", "connection": UUID, "zone": "home"}
        self.assertEqual(ops.validate([ok])[0]["device"], "eno1")
        for field, value in (("device", "--help"), ("device", "a b"), ("connection", "x"),
                             ("connection", UUID + " --x")):
            with self.subTest(field=field):
                with self.assertRaises(ops.OpError):
                    ops.validate([dict(ok, **{field: value})])

    def test_unknown_and_malformed(self):
        for bad in ([], {}, "x", [1], [{"op": "reload"}], [{"op": "rich-rule", "zone": "public"}],
                    [{"op": "service"}] * (ops.MAX_OPS + 1), None):
            with self.subTest(bad=bad):
                with self.assertRaises(ops.OpError):
                    ops.validate(bad)

    def test_power_goes_alone(self):
        with self.assertRaises(ops.OpError):
            ops.validate([{"op": "power", "on": False},
                          {"op": "default-zone", "zone": "public"}])

    def test_loads(self):
        good = json.dumps({"ops": [{"op": "power", "on": True}]})
        self.assertEqual(ops.loads(good), [{"op": "power", "on": True}])
        for bad in ("not json", "{" * 5, "x" * (ops.MAX_BYTES + 1)):
            with self.assertRaises(ops.OpError):
                ops.loads(bad)


class Commands(unittest.TestCase):
    def argv(self, op):
        return [s.argv for s in ops.steps(ops.validate_op(op))]

    def test_service(self):
        self.assertEqual(
            self.argv({"op": "service", "zone": "public", "name": "spark-link", "add": True}),
            [["firewall-cmd", "--permanent", "--zone=public", "--add-service=spark-link"]])
        self.assertEqual(
            self.argv({"op": "service", "zone": "public", "name": "spark-link", "add": False}),
            [["firewall-cmd", "--permanent", "--zone=public", "--remove-service=spark-link"]])

    def test_port(self):
        self.assertEqual(
            self.argv({"op": "port", "zone": "home", "port": "8080/tcp", "add": True}),
            [["firewall-cmd", "--permanent", "--zone=home", "--add-port=8080/tcp"]])

    def test_default_zone_is_live_only(self):
        steps = ops.steps({"op": "default-zone", "zone": "public"})
        self.assertEqual(steps[0].argv, ["firewall-cmd", "--set-default-zone=public"])
        self.assertTrue(steps[0].needs_daemon)

    def test_network_zone_through_network_manager(self):
        steps = ops.steps(ops.validate_op({"op": "network-zone", "device": "eno1",
                                           "connection": UUID, "zone": "public"}))
        self.assertEqual(steps[0].argv, ["nmcli", "connection", "modify", "uuid", UUID,
                                         "connection.zone", "public"])
        self.assertEqual(steps[1].argv, ["firewall-cmd", "--zone=public",
                                         "--change-interface=eno1"])
        self.assertTrue(steps[1].needs_daemon)

    def test_network_zone_without_a_connection(self):
        steps = ops.steps(ops.validate_op({"op": "network-zone", "device": "eno1",
                                           "connection": "", "zone": "home"}))
        self.assertEqual(steps[0].argv, ["firewall-cmd", "--permanent", "--zone=home",
                                         "--change-interface=eno1"])

    def test_power(self):
        self.assertEqual(self.argv({"op": "power", "on": False}),
                         [["systemctl", "disable", "--now", "firewalld.service"]])
        self.assertEqual(self.argv({"op": "power", "on": True}),
                         [["systemctl", "enable", "--now", "firewalld.service"]])

    def test_nothing_goes_through_a_shell(self):
        for op in ({"op": "service", "zone": "public", "name": "ssh", "add": True},
                   {"op": "power", "on": True}):
            for argv in self.argv(op):
                self.assertIsInstance(argv, list)
                self.assertNotIn("sh", argv[0:1])


class Helper(unittest.TestCase):
    def test_adds_a_rule_and_reloads(self):
        code, runner, out, _err = run_helper({"ops": [
            {"op": "service", "zone": "public", "name": "steam-streaming", "add": True}]})
        self.assertEqual(code, 0)
        self.assertEqual(mutating(runner), [
            ["firewall-cmd", "--permanent", "--zone=public", "--add-service=steam-streaming"],
            ["firewall-cmd", "--reload"]])
        self.assertIn("ok reload", out)

    def test_one_reload_for_many_changes(self):
        code, runner, _out, _err = run_helper({"ops": [
            {"op": "service", "zone": "public", "name": "ssh", "add": False},
            {"op": "port", "zone": "public", "port": "8080/tcp", "add": True},
            {"op": "service", "zone": "public", "name": "http", "add": True}]})
        self.assertEqual(code, 0)
        self.assertEqual(sum(1 for c in runner.calls if c[1:] == ["--reload"]), 1)

    def test_changing_a_network_zone_does_not_reload(self):
        code, runner, _out, _err = run_helper({"ops": [
            {"op": "network-zone", "device": "eno1", "connection": UUID, "zone": "public"}]})
        self.assertEqual(code, 0)
        self.assertEqual([c[0] for c in mutating(runner)], ["nmcli", "firewall-cmd"])
        self.assertFalse(any("--reload" in c for c in runner.calls))

    def test_refuses_without_running_anything(self):
        for payload in ("garbage", {"ops": [{"op": "service", "zone": "--x", "name": "ssh",
                                             "add": True}]},
                        {"ops": [{"op": "reload"}]}, {"ops": []}):
            with self.subTest(payload=payload):
                code, runner, _out, err = run_helper(payload)
                self.assertEqual(code, 2)
                self.assertIn("refused", err)
                self.assertEqual(runner.calls, [])

    def test_stops_at_the_first_failure(self):
        runner = support.FakeRun()
        runner.fail_on = "--add-service=ssh"
        code, runner, _out, err = run_helper({"ops": [
            {"op": "service", "zone": "public", "name": "ssh", "add": True},
            {"op": "service", "zone": "public", "name": "http", "add": True}]}, runner)
        self.assertEqual(code, 1)
        self.assertIn("INVALID_SERVICE", err)
        self.assertFalse(any("--add-service=http" in " ".join(c) for c in runner.calls))
        self.assertFalse(any("--reload" in c for c in runner.calls))

    def test_already_there_is_not_a_failure(self):
        class Already(support.FakeRun):
            def __call__(self, argv):
                if "--add-service=ssh" in argv:
                    self.calls.append(argv)
                    return 11, "", "Warning: ALREADY_ENABLED: ssh"
                return super().__call__(argv)
        code, _runner, _out, _err = run_helper({"ops": [
            {"op": "service", "zone": "public", "name": "ssh", "add": True}]}, Already())
        self.assertEqual(code, 0)

    def test_firewall_off_refuses_zone_changes(self):
        off = support.FakeRun(running=False)
        code, runner, _out, err = run_helper({"ops": [
            {"op": "default-zone", "zone": "public"}]}, off)
        self.assertEqual(code, 3)
        self.assertEqual(mutating(runner), [])
        self.assertFalse(any('--reload' in c for c in runner.calls))

    def test_turn_off_and_on(self):
        code, runner, _out, _err = run_helper({"ops": [{"op": "power", "on": False}]})
        self.assertEqual(code, 0)
        self.assertEqual(mutating(runner), [["systemctl", "disable", "--now", "firewalld.service"]])


if __name__ == '__main__':
    unittest.main()
